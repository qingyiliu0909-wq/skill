#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
redundancy.py — netprofile 套件【冗余分析】子技能 (启发式)。

定位修正(重要): 绝大多数流量不是"白发", 而是**同步设计可优化**——发是该发, 但发送模式能改:
  · RPC 合批: 对多个对象逐个调用同种 RPC(几帧内高频, 参数多半重复) → 合并成批量/多播
  · 降频/push-model: 某属性/RPC 高频同步 → 降频 / 客户端推导 / COND_* / push-model(值少变时)
  · 相关性浪费: actor 被考虑却空跑(真'白发', 通常少见) → Dormancy/裁剪
全落到源码定义的【属性 / RPC / actor】, 不报 bunch/帧头/包等传输层。

两段式: ① 概览(默认) 提炼每属性/RPC 时序 → 打印优化候选; ② 深挖(--prop NAME) 取某属性发送画像坐实。

⚠ 根本限制: .nprof 只记"发了什么", 不记"是否需要发/值变没变"。只给【候选+理由】, 需确证
(交叉源码看 COND / UFUNCTION 调用点 / 或 battle:ailogverify 测值变没变)。

用法: python redundancy.py <export.json> [--top 10] | python redundancy.py <export.json> --prop AimCameraLocation
"""

import argparse
import json
import os
import sys

FRAME, BUNCH, RPC, PROP, COMPARISON, ACTOR, WPH = 0, 2, 3, 5, 19, 4, 10

MIN_COUNT = 50                 # 列入候选的最小调用/同步次数(降噪)
RPC_BATCH_CPF = 2.0            # RPC 均次/帧 ≥ 此值 = 帧内多次, 疑"逐对象调用"→合批候选
PROP_FREQ_PRESENCE = 0.50      # 属性出现率 ≥ 此值 = 几乎每帧发 → 降频/COND 候选


def fmt_bytes(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return "%.2f %s" % (n, u)
        n /= 1024.0
    return "%.2f TB" % n


def _slot():
    return {"count": 0, "total_bits": 0, "min": None, "max": 0, "first": -1, "last": -1, "present": 0, "_lf": -2}


def _bump(d, key, bits, f):
    e = d.get(key)
    if e is None:
        e = d[key] = _slot()
    e["count"] += 1
    e["total_bits"] += bits
    e["max"] = max(e["max"], bits)
    e["min"] = bits if e["min"] is None else min(e["min"], bits)
    if e["first"] < 0:
        e["first"] = f
    e["last"] = f
    if e["_lf"] != f:
        e["present"] += 1
        e["_lf"] = f


def aggregate(raw):
    names = raw["names"]
    def nm(i):
        return names[i] if 0 <= i < len(names) else "?"
    props, rpcs = {}, {}
    frame_count = 0
    has_comparison = False
    # Waste(相关性浪费): 某 actor 被 ReplicateActor 考虑了, 但没发任何属性内容(pending==0)。
    # 归属同 hotspot: 属性值+头累积到 pending, 遇 ReplicateActor 结算。reps=被考虑次数, empty=空跑次数。
    # ms=该 actor 复制总 CPU(ReplicateActor token 自带): 空跑多→属性比对白花的 CPU 多, 是 push-model 的优化靶子。
    waste = {}  # actorClass -> {"reps":, "empty":, "bits":, "ms":}
    pending = 0
    for e in raw["events"]:
        t = e["t"]
        if t == FRAME:
            frame_count += 1; pending = 0
        elif t == PROP:
            _bump(props, nm(e["prop"]), e["bits"], e.get("f", -1)); pending += e["bits"]
        elif t == WPH:
            pending += e["bits"]
        elif t == ACTOR:
            a = waste.setdefault(nm(e["actor"]), {"reps": 0, "empty": 0, "bits": 0, "ms": 0.0})
            a["reps"] += 1; a["bits"] += pending; a["ms"] += e.get("ms", 0.0)
            if pending == 0:
                a["empty"] += 1
            pending = 0
        elif t == RPC:
            _bump(rpcs, "%s::%s" % (nm(e["actor"]), nm(e["func"])), e["hdr"] + e["par"] + e["foot"], e.get("f", -1))
        elif t == COMPARISON:
            has_comparison = True

    def derive(d):
        out = {}
        for k, e in d.items():
            n = e["count"]
            span = (e["last"] - e["first"] + 1) if e["first"] >= 0 else 0
            out[k] = {"count": n, "total_bits": e["total_bits"],
                      "mean_bits": (e["total_bits"] / n) if n else 0.0,
                      "const_size": (e["min"] == e["max"]),
                      "present": e["present"],
                      "calls_per_frame": (n / e["present"]) if e["present"] else 0.0,  # 均次/帧: 高=帧内多次(疑逐对象)
                      "presence_ratio": (e["present"] / frame_count) if frame_count else 0.0,
                      "density_in_span": (e["present"] / span) if span else 0.0}
        return out
    return {"props": derive(props), "rpcs": derive(rpcs),
            "frame_count": frame_count, "has_comparison": has_comparison, "waste": waste}


def prop_drill(raw, target):
    """深挖: 回全量, 取目标属性的发送画像 —— 哪些 Actor 在发、逐帧、体积分布。"""
    names = raw["names"]
    def nm(i):
        return names[i] if 0 <= i < len(names) else "?"
    by_actor = {}
    by_size = {}
    frames = []
    total_bits = 0
    # 归属同 aggregate(GUI 已验证): 属性在前、ReplicateActor 在后(DataChannel.cpp:3202)。
    # 故 target 属性先累进 pend, 遇下一个 ReplicateActor 结算给【那个】actor。不可用"上一个actor"(会错位一档)。
    pend = 0
    for e in raw["events"]:
        t = e["t"]
        if t == FRAME:
            pend = 0
            continue
        if t == PROP and nm(e["prop"]) == target:
            pend += 1
            by_size[e["bits"]] = by_size.get(e["bits"], 0) + 1
            frames.append(e.get("f", -1))
            total_bits += e["bits"]
        elif t == ACTOR and pend:
            a = nm(e["actor"]); by_actor[a] = by_actor.get(a, 0) + pend; pend = 0
    return {"total_count": len(frames), "total_bits": total_bits, "by_actor": by_actor,
            "by_size": by_size, "frames": frames}


def json_out_path(raw):
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stem = os.path.splitext(raw["meta"]["source"])[0]
    cap_dir = os.path.join(skill_dir, "json", stem)  # 同 capture 文件夹
    os.makedirs(cap_dir, exist_ok=True)
    return os.path.join(cap_dir, "redundancy.json")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="网络冗余分析 (两段式: 概览 / --prop 深挖)")
    ap.add_argument("input", help="export 产出的全量 .json")
    ap.add_argument("--prop", help="深挖某属性的发送画像")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.stderr.write("[错误] 找不到全量 JSON: %s。先用 netprofile-export 导出。\n" % args.input)
        sys.exit(2)
    try:
        with open(args.input, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        sys.stderr.write("[错误] 输入不是 export.json(像是 .nprof 二进制或损坏文件)。\n"
                         "  本脚本要的是 export 产出的 JSON。先跑 nprof_export.py <.nprof>, 再把它末行打印的 export.json 路径传进来。\n")
        sys.exit(2)
    out = []
    w = out.append

    # ───── 深挖模式 ─────
    if args.prop:
        d = prop_drill(raw, args.prop)
        w("═══════════════════════════════════════════════════════════════")
        w("  冗余深挖 · 属性 %s 发送画像 (回全量取)  |  %s" % (args.prop, raw["meta"]["source"]))
        w("═══════════════════════════════════════════════════════════════")
        if d["total_count"] == 0:
            w("  未找到该属性的复制记录 (名字是否准确?)。")
        else:
            w("  共发送 %d 次, 合计 %s" % (d["total_count"], fmt_bytes(d["total_bits"] / 8.0)))
            w("  按 Actor 归属:")
            for a, c in sorted(d["by_actor"].items(), key=lambda kv: -kv[1])[:args.top]:
                w("     %-32s %d 次" % (str(a)[:32], c))
            w("  体积分布 (bit→次数): " + ", ".join("%d位×%d" % (b, c) for b, c in sorted(d["by_size"].items())))
            fs = d["frames"]
            if len(fs) >= 2:
                gaps = [fs[i + 1] - fs[i] for i in range(len(fs) - 1) if fs[i + 1] >= fs[i]]
                avg_gap = sum(gaps) / len(gaps) if gaps else 0
                w("  发送跨度: 帧 %d → %d, 平均间隔 %.1f 帧/次 (间隔越稳越像周期发)" % (fs[0], fs[-1], avg_gap))
        w("═══════════════════════════════════════════════════════════════")
        w("  坐实: 体积恒定+间隔稳=周期发→查源码能否降频/客户端推导; 仍存疑用 battle:ailogverify 测【值变 vs 发送】。")
        sys.stdout.write("\n".join(out) + "\n")
        return

    # ───── 概览模式 ─────
    g = aggregate(raw)
    props, rpcs = g["props"], g["rpcs"]
    N = args.top

    # ① RPC 合批候选: 均次/帧 ≥ 阈值 = 帧内多次调用, 疑"对多个对象逐个调RPC"→ 合并(参数多半重复)。按 均次/帧 排。
    rpc_batch = sorted([(k, v) for k, v in rpcs.items() if v["calls_per_frame"] >= RPC_BATCH_CPF and v["count"] >= 10],
                       key=lambda kv: -kv[1]["calls_per_frame"])
    # ② 高频同步候选(降频/push): 属性+RPC, 按带宽排, count≥阈值。属性看出现率高→降频/COND;恒定+值少变→push。
    prop_freq = sorted([(k, v) for k, v in props.items() if v["count"] >= MIN_COUNT],
                       key=lambda kv: -kv[1]["total_bits"])
    rpc_freq = sorted([(k, v) for k, v in rpcs.items() if v["count"] >= MIN_COUNT and v["calls_per_frame"] < RPC_BATCH_CPF],
                      key=lambda kv: -kv[1]["total_bits"])
    # ③ 相关性浪费(真'白发', 少见): actor 被考虑却大多空跑。
    waste = sorted([(k, v) for k, v in g["waste"].items() if v["reps"] >= MIN_COUNT and v["empty"] > 0],
                   key=lambda kv: -kv[1]["empty"])

    # 提炼小 JSON
    def packp(lst):
        return [{"name": k, "bytes": round(v["total_bits"] / 8.0, 1), "count": v["count"],
                 "calls_per_frame": round(v["calls_per_frame"], 2), "presence_ratio": round(v["presence_ratio"], 3),
                 "const_size": v["const_size"], "mean_bits": round(v["mean_bits"], 1)} for k, v in lst[:N]]
    compact = {"source": raw["meta"]["source"], "has_comparison": g["has_comparison"], "frame_count": g["frame_count"],
               "rpc_batch_candidates": packp(rpc_batch), "prop_freq_candidates": packp(prop_freq),
               "rpc_freq_candidates": packp(rpc_freq),
               "waste": [{"actor": k, "reps": v["reps"], "empty": v["empty"],
                          "waste_pct": round(100.0 * v["empty"] / v["reps"], 1), "cpu_ms": round(v["ms"], 1)} for k, v in waste[:N]]}
    cpath = json_out_path(raw)
    with open(cpath, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

    w("═══════════════════════════════════════════════════════════════")
    w("  网络冗余分析 · 候选 (启发式, 需确证)")
    w("  含义: 冗余 ≠ 字面'白发'; 找【同步设计上可优化的发送模式】——逐对象RPC合批 / 高频降频 / 值少变push-model / 相关性浪费。与热点分析(看'流量压力')互补:这里看'该不该这么发'。")
    w("═══════════════════════════════════════════════════════════════")
    w("  文件: %s | %d 帧" % (raw["meta"]["source"], g["frame_count"]))
    if not g["has_comparison"]:
        w("  ⚠ 未开 comparison tracking: 无 compared/changed 硬证据, '值变没变'判不准, 以下为嫌疑候选。")
    w("")
    w("  ───────────── ① RPC 合批候选 (均次/帧≥%.0f = 帧内多次, 疑【逐对象调用】→合并成批量/多播) ─────────────" % RPC_BATCH_CPF)
    w("  → 落 UFUNCTION 调用点: 是否在循环里对多个对象逐个调? 参数多半重复 → 一次数组/多播 RPC 搞定。")
    if not rpc_batch:
        w("  (无帧内多次调用的 RPC)")
    for k, v in rpc_batch[:N]:
        w("     [RPC] %-40s 调用%d次/活跃%d帧 = 均%.1f次/帧 | %s%s" % (
            k[:40], v["count"], v["present"], v["calls_per_frame"], fmt_bytes(v["total_bits"] / 8.0),
            " | 恒定%dbit(参数齐整,更像可合批)" % v["mean_bits"] if v["const_size"] else ""))
    w("  ───────────── ② 高频同步候选 · 属性/RPC (降频 / 客户端推导 / COND_* / push-model) ─────────────")
    w("  → 属性查 DOREPLIFETIME(出现率高→降频/COND_SkipOwner等; 恒定且值少变→push-model MARK_PROPERTY_DIRTY); RPC 查 UFUNCTION(降频).")
    if not prop_freq:
        w("  (无高频属性)")
    for k, v in prop_freq[:N]:
        # 用 density_in_span(活跃区间内的密度)打"几乎每帧"标, 不用 presence_ratio(总帧数分母会漏掉技能窗/spawn潮等短时高密)
        tag = " ◀活跃期几乎每帧发" if v["density_in_span"] >= PROP_FREQ_PRESENCE else (" 恒定%dbit" % v["mean_bits"] if v["const_size"] else "")
        w("     [属性] %-40s 同步%d次/出现率%.0f%% | %s%s" % (
            k[:40], v["count"], 100 * v["presence_ratio"], fmt_bytes(v["total_bits"] / 8.0), tag))
    for k, v in rpc_freq[:N]:
        w("     [RPC]  %-40s 调用%d次/均%.1f次每帧 | %s (周期高频→降频)" % (
            k[:40], v["count"], v["calls_per_frame"], fmt_bytes(v["total_bits"] / 8.0)))
    w("  ───────────── ③ 相关性浪费 · actor (真'白发', 通常少见; 低优先) ─────────────")
    w("  含义: 被考虑复制却空跑(属性比对没变化→没发, 白花比对 CPU)。候选 push-model(免比对)/Dormancy/降频。")
    if not waste:
        w("  (无明显浪费)")
    for k, v in waste[:N]:
        w("     [actor] %-38s 被考虑%d次, 空跑%d次(浪费%.0f%%), 复制CPU%.0fms" % (
            k[:38], v["reps"], v["empty"], 100.0 * v["empty"] / v["reps"], v["ms"]))
    w("═══════════════════════════════════════════════════════════════")
    w("  提炼小JSON: %s" % cpath)
    w("  深挖: `redundancy.py <全量json> --prop <候选名>` 看发送画像(哪些actor在发/节拍); 再交叉源码 UFUNCTION/DOREPLIFETIME 坐实。")
    w("  → 上面候选只是【起点信号】, 不是分析范围: 别只看这几个高的, 所选模块内不明显极低的都走 SKILL「★逐项闭环调查」(中等冗余最易漏)。")
    w("    产出写进 AnalysisReport/<原nprof名>/: 先各 redundancy-<项>.md, 后主 redundancy.md(总览+全量结论表+导航)。见 SKILL「★MD 分析报告产出规范」。")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
