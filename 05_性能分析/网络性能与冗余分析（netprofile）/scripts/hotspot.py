#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hotspot.py — netprofile 套件【热点分析】子技能。

两段式 (解决"全量 JSON 太大不能全读"):
  ① 概览(默认): 读全量 raw JSON, 提炼出热点小数据 → 写本技能 json/ 下的小 JSON + 打印整体全景文本。
                先看清全貌、按严重度列出热点清单。【只列热点, 不深入、不碰源码、不给改法】
  ② 深挖(--range A B): 回全量 JSON, 取该帧区间的【逐帧详细构成】(每帧发了哪些 Actor/Property/RPC)。

严重度标准 (权威定义见 reference/hotspot_standard.md), 纯流量:
  P0 严重(流量饱和/数量风暴=会卡死掉线) / P1 关注(高于常态/多人易转P0) / P2 降压杠杆(Pareto,改哪最省)。
  脚本只出客观数据, agent 据标准判级。效率类(CPU/相关性浪费)归冗余分析 redundancy, 不在热点。

用法:
  python hotspot.py <export.json>              # 概览(提炼小JSON+全景文本)
  python hotspot.py <export.json> --range A B  # 深挖某帧区间的逐帧详情
  其它: --top 8 / --rate 7000 / --tick 30
"""

import argparse
import json
import os
import sys

# 客观度量常量。判级阈值【不在这里】——分级是主观分析, 由 agent 读聚合数据按 reference/hotspot_standard.md 做。
# 本脚本只产出客观事实(各秒/各帧字节、各实体 bits/CPU/空跑次数、类别占比)与纯算术比值(几倍预算)。
DEFAULT_TICK_HZ = 30          # R: 复制 tick (NetServerMaxTickRate)
TOTAL_BANDWIDTH = 32000       # TotalNetBandwidth: 在所有连接间分摊 (BaseGame.ini)
MIN_DYNAMIC = 4000            # MinDynamicBandwidth: 人多时每连接地板
DEFAULT_RATE = 7000           # MaxDynamicBandwidth: 单连接预算上限; 用于算"×预算"比值供 agent 判级
RELIABLE_BUFFER = 512         # reliable 缓冲容量【每 ActorChannel】, 溢出→Connection->Close() (NetConnection.h:57 + DataChannel.cpp:1094-1121)
RPC_REPEAT_FLOOR = 4          # 记录门槛: 同种 RPC 单帧重复 ≥ 此值才登记(降噪, 非严重度阈值)
CHAN_BUNCH_FLOOR = 8          # 记录门槛: 单通道单帧 bunch 数 ≥ 此值才登记


def per_conn_budget(n_conn, rate_max):
    """单连接动态带宽预算 = clamp(TotalNetBandwidth / N, Min, Max)。
    N=连接数。1人→clamp(32000,4000,7000)=7000; 4人→clamp(8000,..)=7000; 8人→4000。"""
    n = max(1, n_conn)
    return int(max(MIN_DYNAMIC, min(rate_max, TOTAL_BANDWIDTH / n)))

FRAME, SOCK, BUNCH, RPC, ACTOR, PROP = 0, 1, 2, 3, 4, 5
ACK, WPH, EXPB, MBM, BCB, ECB, WPHND = 9, 10, 11, 12, 13, 14, 15


def fmt_bytes(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return "%.2f %s" % (n, u)
        n /= 1024.0
    return "%.2f TB" % n


def sparkline(values, width=60):
    blocks = " ▁▂▃▄▅▆▇█"
    if not values:
        return ""
    n = len(values)
    buckets = list(values) if n <= width else [max(values[i * n // width:(i + 1) * n // width] or [0]) for i in range(width)]
    ordered = sorted(buckets)
    p95 = ordered[int(0.95 * (len(ordered) - 1))] or (max(buckets) or 1)
    return "".join(blocks[int(round(min(1.0, v / p95) * 8))] for v in buckets)


def aggregate(raw, frame_range=None):
    """从无损 events 聚合热点所需视图 (本子技能口径)。"""
    names = raw["names"]
    def nm(i):
        return names[i] if 0 <= i < len(names) else "?"
    lo, hi = frame_range if frame_range else (None, None)
    def inwin(f):
        return frame_range is None or (lo <= f <= hi)

    frames, actors, props, rpcs = {}, {}, {}, {}
    bits = {"pid": 0, "bun": 0, "ack": 0, "pad": 0}        # SocketSendTo 包级分项
    # 流量去向(bunch 载荷按内容类别拆, 压缩前逻辑量; 让非属性大头=NetGUID导出/句柄等不再隐形):
    cats = {"prop": 0, "rpc": 0, "export": 0, "handle": 0, "block": 0, "mbm": 0}
    bun_pay = 0  # SendBunch 载荷总量(= cats 各类之和 + 未tokenize 的部分)
    # 归属模型 (源码 DataChannel.cpp:3202 + GUI 精确对账): TrackReplicateActor 在该 actor 的内容【之后】发,
    # 所以属性值(ReplicateProperty)+属性头(WritePropertyHeader)先累积到 pending, 遇 ReplicateActor 归给它。
    pending = 0

    def ao(name):
        return actors.setdefault(name, {"count": 0, "time_ms": 0.0, "bits": 0, "empty": 0})

    # 数量风暴(撑爆 per-channel reliable 缓冲 → 断线; 也是业务bug信号): 按帧统计
    # 同种 RPC 单帧重复次数 + 单通道(conn,ch)单帧 bunch 数, 帧边界 flush 进 bursts。
    rpc_bursts, chan_bursts = [], []          # (count, frame, key) / (count, frame, conn, ch)
    cur_rpc, cur_chan, cur_f = {}, {}, -1
    def flush_counts():
        if cur_f < 0:                            # 跳过首个 FrameMarker 之前的事件(f=-1), 不产生"帧-1"幽灵突发
            cur_rpc.clear(); cur_chan.clear(); return
        for k, n in cur_rpc.items():
            if n >= RPC_REPEAT_FLOOR:
                rpc_bursts.append((n, cur_f, k))
        for (cc, ch), n in cur_chan.items():
            if n >= CHAN_BUNCH_FLOOR:
                chan_bursts.append((n, cur_f, cc, ch))
        cur_rpc.clear(); cur_chan.clear()

    for e in raw["events"]:
        t = e["t"]
        if t == FRAME:
            flush_counts(); cur_f = e["f"]
            pending = 0
            if inwin(e["f"]):
                # conn_bytes: 按连接(c)拆, 用于多连接各自判饱和
                frames[e["f"]] = {"index": e["f"], "time": e["time"], "bytes_sent": 0, "packets": 0,
                                  "replicate_count": 0, "bunches": 0, "conn_bytes": {}}
            continue
        f = e.get("f", -1)
        if not inwin(f):
            continue
        if t == SOCK:
            fr = frames.get(f)
            if fr:
                fr["bytes_sent"] += e["bytes"]; fr["packets"] += 1
                c = e.get("c", -1); fr["conn_bytes"][c] = fr["conn_bytes"].get(c, 0) + e["bytes"]
            bits["pid"] += e["pid"]; bits["bun"] += e["bun"]; bits["ack"] += e["ack"]; bits["pad"] += e["pad"]
        elif t == BUNCH:
            bun_pay += e["pay"]
            fr = frames.get(f)
            if fr:
                fr["bunches"] += 1
            ck = (e.get("c", -1), e.get("ch", -1)); cur_chan[ck] = cur_chan.get(ck, 0) + 1
        elif t == ACTOR:
            a = ao(nm(e["actor"])); a["count"] += 1; a["time_ms"] += e["ms"]
            a["bits"] += pending
            if pending == 0:
                a["empty"] += 1  # 被考虑复制但没发任何属性内容 = 相关性/调度浪费
            pending = 0
            fr = frames.get(f)
            if fr:
                fr["replicate_count"] += 1
        elif t == PROP:
            p = nm(e["prop"]); props[p] = props.get(p, 0) + e["bits"]
            pending += e["bits"]; cats["prop"] += e["bits"]
        elif t == WPH:
            pending += e["bits"]; cats["prop"] += e["bits"]
        elif t == RPC:
            k = "%s::%s" % (nm(e["actor"]), nm(e["func"]))
            nb = e["hdr"] + e["par"] + e["foot"]
            rpcs[k] = rpcs.get(k, 0) + nb; cats["rpc"] += nb
            cur_rpc[k] = cur_rpc.get(k, 0) + 1
        elif t == EXPB:
            cats["export"] += e["bits"]
        elif t == WPHND:
            cats["handle"] += e["bits"]
        elif t == BCB or t == ECB:                          # 内容块 开始/结束 都计入框架口径(ECB 实际罕见)
            cats["block"] += e["bits"]
        elif t == MBM:
            cats["mbm"] += e["bits"]

    flush_counts()                                          # 末帧
    flist = [frames[k] for k in sorted(frames)]
    total = sum(fr["bytes_sent"] for fr in flist)
    dur = (flist[-1]["time"] - flist[0]["time"]) if flist else 0.0
    cats["untok"] = max(0, bun_pay - sum(cats.values()))  # bunch 载荷里未被任何 token 细分的部分
    return {"frames": flist, "actors": actors, "props": props, "rpcs": rpcs, "bits": bits,
            "cats": cats, "bun_pay": bun_pay, "total_bytes": total, "duration": dur,
            "rpc_bursts": sorted(rpc_bursts, reverse=True)[:50],
            "chan_bursts": sorted(chan_bursts, reverse=True)[:50]}


def frame_detail(raw, lo, hi):
    """深挖: 回全量 events, 取 [lo,hi] 窗口的【完整构成】(含 NetGUID导出/句柄/内容块等非属性类) + 逐帧字节。
    输出保持紧凑(窗口聚合 + 逐帧字节), 给 agent 看真实构成。"""
    names = raw["names"]
    def nm(i):
        return names[i] if 0 <= i < len(names) else "?"
    inw = lambda f: lo <= f <= hi
    fr = {}                       # frame -> [bytes, packets, repActorCount, propSyncCount, rpcCount]
    props, rpcs, actors = {}, {}, {}
    cats = {"prop": 0, "rpc": 0, "export": 0, "handle": 0, "block": 0, "mbm": 0}
    bun_pay = 0; ack_bits = 0; pending = 0; prop_n = 0; rpc_n = 0
    for e in raw["events"]:
        t = e["t"]
        if t == FRAME:
            pending = 0
            if inw(e["f"]):
                fr[e["f"]] = [0, 0, 0, 0, 0]
            continue
        f = e.get("f", -1)
        if not inw(f):
            continue
        if t == SOCK:
            d = fr.get(f)
            if d:
                d[0] += e["bytes"]; d[1] += 1
        elif t == BUNCH:
            bun_pay += e["pay"]
        elif t == ACTOR:
            cls = nm(e["actor"]); actors[cls] = actors.get(cls, 0) + pending; pending = 0
            d = fr.get(f)
            if d:
                d[2] += 1
        elif t == PROP:
            pn = nm(e["prop"]); props[pn] = props.get(pn, 0) + e["bits"]; pending += e["bits"]; cats["prop"] += e["bits"]
            prop_n += 1; d = fr.get(f)
            if d:
                d[3] += 1
        elif t == WPH:
            pending += e["bits"]; cats["prop"] += e["bits"]
        elif t == RPC:
            k = "%s::%s" % (nm(e["actor"]), nm(e["func"])); nb = e["hdr"] + e["par"] + e["foot"]
            rpcs[k] = rpcs.get(k, 0) + nb; cats["rpc"] += nb
            rpc_n += 1; d = fr.get(f)
            if d:
                d[4] += 1
        elif t == EXPB:
            cats["export"] += e["bits"]
        elif t == WPHND:
            cats["handle"] += e["bits"]
        elif t == BCB or t == ECB:
            cats["block"] += e["bits"]
        elif t == MBM:
            cats["mbm"] += e["bits"]
        elif t == ACK:
            ack_bits += e["bits"]
    cats["untok"] = max(0, bun_pay - sum(cats.values()))
    frames = [(k, fr[k][0], fr[k][1], fr[k][2], fr[k][3], fr[k][4]) for k in sorted(fr)]
    return {"frames": frames, "props": props, "rpcs": rpcs, "actors": actors,
            "cats": cats, "bun_pay": bun_pay, "ack_bits": ack_bits, "prop_n": prop_n, "rpc_n": rpc_n,
            "total_bytes": sum(x[1] for x in frames), "total_packets": sum(x[2] for x in frames)}


def json_out_path(raw):
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stem = os.path.splitext(raw["meta"]["source"])[0]
    cap_dir = os.path.join(skill_dir, "json", stem)  # 同 capture 文件夹
    os.makedirs(cap_dir, exist_ok=True)
    return os.path.join(cap_dir, "hotspot.json")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="网络热点分析 (两段式: 概览 / --range 深挖)")
    ap.add_argument("input", help="export 产出的全量 .json")
    ap.add_argument("--range", dest="frange", nargs=2, type=int, metavar=("START", "END"), help="深挖该帧区间逐帧详情")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--tick", type=int, default=DEFAULT_TICK_HZ)
    ap.add_argument("--rate", type=int, default=DEFAULT_RATE)
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
    h = raw["header"]
    out = []
    w = out.append

    # ───── 深挖模式 (定帧/定窗回全量取完整构成, 紧凑) ─────
    if args.frange:
        lo, hi = min(args.frange), max(args.frange)
        d = frame_detail(raw, lo, hi)
        N = args.top
        w("═══════════════════════════════════════════════════════════════")
        w("  热点深挖 · 帧 %d–%d (回全量取完整构成)  |  %s" % (lo, hi, raw["meta"]["source"]))
        w("═══════════════════════════════════════════════════════════════")
        if not d["frames"]:
            w("  该区间无帧。"); sys.stdout.write("\n".join(out) + "\n"); return
        ct = d["cats"]; ctot = max(d["bun_pay"], sum(ct.values())) or 1   # 同概览: max 防 token位>载荷位时占比>100%
        attr = ct["prop"] + ct["rpc"]
        w("  窗口触发: 属性同步 %d 次 | RPC %d 次 | actor 复制 %d 次 | 发送 %s(线上闸门)" % (
            d["prop_n"], d["rpc_n"], sum(x[3] for x in d["frames"]), fmt_bytes(d["total_bytes"])))
        w("  业务可优化层: 属性 %s + RPC %s = %.0f%% (其余 %.0f%% 引擎结构/spawn, 业务层不计)" % (
            fmt_bytes(ct["prop"] / 8.0), fmt_bytes(ct["rpc"] / 8.0), 100.0 * attr / ctot, 100.0 * (ctot - attr) / ctot))
        w("  ── 这一窗到底发了什么(落到源码定义的 属性/RPC/actor) ──")
        tp = sorted(d["props"].items(), key=lambda kv: -kv[1])[:N]
        tr = sorted(d["rpcs"].items(), key=lambda kv: -kv[1])[:N]
        ta = sorted(d["actors"].items(), key=lambda kv: -kv[1])[:N]
        if tp:
            w("  Top 属性(→DOREPLIFETIME): " + " | ".join("%s %s" % (k, fmt_bytes(v / 8.0)) for k, v in tp))
        if tr:
            w("  Top RPC(→UFUNCTION)     : " + " | ".join("%s %s" % (k, fmt_bytes(v / 8.0)) for k, v in tr))
        if ta:
            w("  Top Actor类(→复制设置)   : " + " | ".join("%s %s" % (k, fmt_bytes(v / 8.0)) for k, v in ta))
        # 逐帧: 看尖刺落在哪帧 + 那帧触发了多少属性/RPC
        nz = [(i, b, pn, rn) for (i, b, p, r, pn, rn) in d["frames"] if b > 0]
        w("  逐帧(仅发送非0帧, 共%d/%d): %s" % (
            len(nz), len(d["frames"]), "  ".join("帧%d=%s(%d属性/%dRPC)" % (i, fmt_bytes(b), pn, rn)
                                                 for i, b, pn, rn in sorted(nz, key=lambda x: -x[1])[:N])))
        w("═══════════════════════════════════════════════════════════════")
        w("  → 落到 属性/RPC/actor 推理根因; 未分类高=复制框架/初始spawn居多(看该窗 ReplicateActor 在 spawn/激活哪些 actor); 要业务场景语义(这波在干嘛)才用 battle:ailogverify 按时间贯穿。")
        sys.stdout.write("\n".join(out) + "\n")
        return

    # ───── 概览模式: 只产出【客观聚合数据】, 不判级、不下结论 (判级/排序/根因是 agent 的事) ─────
    g = aggregate(raw)
    frames = g["frames"]
    if g["total_bytes"] == 0:                       # 空采样: 优雅降级, 不打一屏 0 噪声
        w("═══════════════════════════════════════════════════════════════")
        w("  网络热点 · %s" % raw["meta"]["source"])
        w("═══════════════════════════════════════════════════════════════")
        w("  本次采样无发送流量 (%d 帧 / %.1fs, %s)。" % (len(frames), g["duration"], h.get("url", "?")))
        w("  多半录在菜单/加载/非战斗场景, 没有可分析的热点。请在实际战斗中开 netprofile 重录。")
        sys.stdout.write("\n".join(out) + "\n")
        return
    fc = max(len(frames), 1)
    tick = max(1, args.tick)
    N = args.top
    bs = [fr["bytes_sent"] for fr in frames]
    # 逻辑载荷分母取 max(bunch载荷, 各类之和): cats(按token)与 bun_pay(按SendBunch)是独立累加器,
    # 极端帧 token位 > 载荷位时不至于把占比算成 >100% (untok 已 max(0,..) 夹过)。
    logical = max(g["bun_pay"], sum(g["cats"].values())) or 1

    # ── 多连接: 每连接各自判饱和。── 先按"实际出现过的连接"算并发数(连接表是累积地址、含重连/非客户端,
    # 用它当分母会虚低预算→假性P0); 故 N = 真正发过流量的连接数(cbins 的连接数)。
    conns = raw.get("connections", [])
    addr = lambda c: conns[c] if 0 <= c < len(conns) else "?"
    t0 = frames[0]["time"]
    cbins = {}                                                        # conn -> {sec: bytes}
    for fr in frames:
        sec = int(fr["time"] - t0)
        for c, b in fr["conn_bytes"].items():
            d = cbins.setdefault(c, {}); d[sec] = d.get(sec, 0) + b
    n_conn = max(1, len(cbins))                                       # 发过流量的连接数(非地址表长度)
    B = per_conn_budget(n_conn, args.rate)
    per_conn, cbase = [], {}                                          # 每连接压力小结 + 基线
    for c in sorted(cbins):
        b = cbins[c]
        nzc = sorted(v for v in b.values() if v > 0)
        m = len(nzc)
        cbase[c] = (nzc[(m - 1) // 2] + nzc[m // 2]) / 2.0 if m else 0   # 真中位数(偶数取两中位均值)
        per_conn.append({"conn": c, "addr": addr(c), "secs_total": len(b),
                         "secs_over": sum(1 for v in b.values() if v >= B),
                         "peak": max(b.values()) if b else 0, "base": cbase[c]})
    per_conn.sort(key=lambda pc: -pc["peak"])
    top_secs = sorted(((c, s, v) for c, b in cbins.items() for s, v in b.items()), key=lambda x: -x[2])[:N]
    top_frames = sorted(frames, key=lambda fr: -fr["bytes_sent"])[:N]  # 单帧尖峰(总量, 仅定位)
    rpc_bursts = g["rpc_bursts"]                                       # 同种 RPC 单帧重复 (业务bug信号 + 撑缓冲)
    chan_bursts = g["chan_bursts"]                                     # 单通道单帧 bunch 数 (per-channel reliable 压力)
    actors_s = sorted(((k, v["bits"]) for k, v in g["actors"].items()), key=lambda kv: -kv[1])
    props_s = sorted(g["props"].items(), key=lambda kv: -kv[1])
    rpcs_s = sorted(g["rpcs"].items(), key=lambda kv: -kv[1])
    a_tot = sum(v for _, v in actors_s) or 1                          # 各维度内总量(占比按类别内算, 专注业务层)
    p_tot = sum(v for _, v in props_s) or 1
    r_tot = sum(v for _, v in rpcs_s) or 1
    # 复制CPU / 相关性浪费(空跑的属性比对白花CPU) 不在此分析——属"该不该发/比"的效率问题, 归冗余分析 redundancy。

    # 提炼小 JSON (纯客观度量 + 算术比值; 给 agent 按标准判级, 也供回查/共享)
    compact = {
        "source": raw["meta"]["source"], "integrity": raw.get("integrity"),
        "connections": n_conn, "budget_per_conn_bps": B, "tick": tick,
        "summary": {"frame_count": len(frames), "duration_s": round(g["duration"], 3),
                    "total_bytes": g["total_bytes"], "avg_bytes_per_frame": round(g["total_bytes"] / fc, 2),
                    "bits": g["bits"], "bun_pay_bits": g["bun_pay"],
                    "cats_bytes": {k: round(v / 8.0, 1) for k, v in g["cats"].items()},
                    "cats_pct_logical": {k: round(100.0 * v / logical, 1) for k, v in g["cats"].items()}},
        "per_connection": [{"conn": pc["conn"], "addr": pc["addr"], "secs_total": pc["secs_total"],
                            "secs_over_budget": pc["secs_over"],
                            "pct_over": round(100.0 * pc["secs_over"] / pc["secs_total"], 1) if pc["secs_total"] else 0.0,
                            "peak_sec_bytes": pc["peak"], "peak_x_budget": round(pc["peak"] / B, 2),
                            "median_sec_bytes": pc["base"]} for pc in per_conn],
        "top_seconds": [{"conn": c, "sec": s, "bytes": v, "x_budget": round(v / B, 2),
                         "x_baseline": round(v / cbase[c], 2) if cbase.get(c) else None} for c, s, v in top_secs],
        "spike_frames": [{"frame": fr["index"], "bytes": fr["bytes_sent"], "bunches": fr.get("bunches", 0)} for fr in top_frames],
        "count_storm": {
            "reliable_buffer": RELIABLE_BUFFER,
            "rpc_repeat_top": [{"count": n, "frame": fr, "rpc": k} for n, fr, k in rpc_bursts[:N]],
            "chan_bunch_top": [{"count": n, "frame": fr, "conn": cc, "channel": ch} for n, fr, cc, ch in chan_bursts[:N]]},
        "business_layer": {"prop_bytes": round(g["cats"]["prop"] / 8.0, 1), "rpc_bytes": round(g["cats"]["rpc"] / 8.0, 1),
                           "pct_of_logical": round(100.0 * (g["cats"]["prop"] + g["cats"]["rpc"]) / logical, 1)},
        "top_actors": [{"name": k, "bytes": round(v / 8.0, 1), "pct_in_dim": round(100.0 * v / a_tot, 1)} for k, v in actors_s[:N]],
        "top_props": [{"name": k, "bytes": round(v / 8.0, 1), "pct_in_dim": round(100.0 * v / p_tot, 1)} for k, v in props_s[:N]],
        "top_rpcs": [{"name": k, "bytes": round(v / 8.0, 1), "pct_in_dim": round(100.0 * v / r_tot, 1)} for k, v in rpcs_s[:N]],
        "frame_bytes": [fr["bytes_sent"] for fr in frames],
    }
    cpath = json_out_path(raw)
    with open(cpath, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

    # ── 客观聚合数据 (stdout 直接进 agent 上下文; agent 据此 + reference/hotspot_standard.md 判 P0–P2) ──
    w("═══════════════════════════════════════════════════════════════")
    w("  网络热点分析 · 客观聚合数据 (非结论; 由 agent 按 hotspot_standard.md 判级排序)")
    w("  含义: 热点=网络流量【压力】——哪些时段/actor/属性/RPC 发得多、压不压得住带宽预算(P0/P1/P2);与冗余分析(该不该这么发)互补。")
    w("═══════════════════════════════════════════════════════════════")
    w("  文件: %s | %s | %s" % (raw["meta"]["source"], h.get("game", "?"), h.get("url", "?")))
    integ = {"truncated": "⚠尾部截断(不影响)", "clean": "✓正常", "unknown": "?未知"}.get(raw.get("integrity"), "?")
    w("  采样: %d 帧 / %.1fs (~%.1f fps) | 完整性 %s" % (len(frames), g["duration"], len(frames) / g["duration"] if g["duration"] > 0 else 0.0, integ))
    w("  发送: %s 总 / %s 每帧(所有连接合计) | tick %dHz" % (fmt_bytes(g["total_bytes"]), fmt_bytes(g["total_bytes"] / fc), tick))
    w("  连接数 %d | 单连接预算 B=%d B/s = clamp(%d/%d, %d, %d) —— 饱和【按连接各自判】, 不拿总量比单连接预算" % (
        n_conn, B, TOTAL_BANDWIDTH, n_conn, MIN_DYNAMIC, args.rate))
    w("  时间线(总量): %s" % sparkline(bs))

    # ① 全程压力 (终极目标=降总流量压力): 每个连接各自顶超预算几秒 / 峰值 / 常态
    w("  ── 全程压力概况 · 每连接 (判 P0流量饱和: 该连接某秒 ≥ B) ──")
    for pc in per_conn:
        w("     连接%d [%s]: 超预算 %d/%d秒(%.0f%%) | 峰值 %s/s(×%.1f预算) | 常态 %s/s" % (
            pc["conn"], pc["addr"], pc["secs_over"], pc["secs_total"],
            100.0 * pc["secs_over"] / pc["secs_total"] if pc["secs_total"] else 0.0,
            fmt_bytes(pc["peak"]), pc["peak"] / B, fmt_bytes(pc["base"])))
    w("  ── 秒级速率 Top · 跨连接 (每条标连接; ≥B→P0饱和 / ≥5×该连接基线但<B→P1关注) ──")
    for c, s, v in top_secs:
        bc = cbase.get(c, 0)
        w("     连接%d 第%4ds: %s/s  (×%.1f预算%s)" % (c, s, fmt_bytes(v), v / B, (" / ×%.1f基线" % (v / bc)) if bc else ""))

    # ② 数量风暴 (判 P0; 撑爆 per-channel reliable 缓冲 512 → Connection->Close() 断线。与字节体积无关)
    w("  ── 数量风暴 (判 P0; 撑爆 per-channel reliable 缓冲 %d → 断线 DataChannel.cpp:1094) ──" % RELIABLE_BUFFER)
    if rpc_bursts:
        w("     同种 RPC 单帧重复 Top (落 UFUNCTION; ≥约16次极可能业务bug: 一操作应一RPC, 短时狂刷同种RPC=调用点设计问题):")
        for n, fr, k in rpc_bursts[:5]:
            w("        帧%d: %s ×%d" % (fr, k, n))
    if chan_bursts:
        w("     单通道单帧 bunch 数 Top (中间层信号: 1 channel=1 actor, 越近 %d 越危; ch 是通道索引, 深挖定位是哪个 actor):" % RELIABLE_BUFFER)
        for n, fr, cc, ch in chan_bursts[:5]:
            w("        连接%d 通道%d 帧%d: %d 个 bunch" % (cc, ch, fr, n))
    if not chan_bursts and not rpc_bursts:
        w("     (无: 无同种 RPC 单帧重复 ≥%d 且单通道 bunch <%d)" % (RPC_REPEAT_FLOOR, CHAN_BUNCH_FLOOR))

    # ③ 降压杠杆 (判 P2; 只看业务可优化层 = 属性/RPC/actor。引擎结构/spawn 不进分析, 知道即可)
    ct = g["cats"]
    attr = ct["prop"] + ct["rpc"]
    w("  ── 业务可优化层: 属性 %s + RPC %s = 占逻辑载荷 %.0f%% (其余 %.0f%% 引擎结构/spawn, 业务层动不了、不计) ──" % (
        fmt_bytes(ct["prop"] / 8.0), fmt_bytes(ct["rpc"] / 8.0), 100.0 * attr / logical, 100.0 * (logical - attr) / logical))
    def show(title, items, tot, lab):
        w("  %s: %s" % (title, " | ".join("%s %.0f%% %s" % (lab(k), 100.0 * v / tot, fmt_bytes(v / 8.0)) for k, v in items[:N]) or "(无)"))
    w("  ── 降压杠杆 Top (占比=各自类别内占比; 判 P2 ≥15%=重点) ──")
    show("Actor类(→复制频率/Dormancy/裁剪)", actors_s, a_tot, lambda k: k)
    show("Property(→DOREPLIFETIME/COND/push)", props_s, p_tot, lambda k: k)
    show("RPC(→UFUNCTION 合批/降频)", rpcs_s, r_tot, lambda k: k)

    # ④ 单帧尖峰: 仅定位用, 不单独定级 (压力已并入①窗口; 是否可避免=冗余分析的事)
    w("  ── 单帧尖峰 (仅供定位 GUI/--range, 非严重度: 突发的压力已计入窗口, 是否冗余看 redundancy) ──")
    w("     " + " | ".join("帧%d=%s(%dbunch)" % (fr["index"], fmt_bytes(fr["bytes_sent"]), fr.get("bunches", 0)) for fr in top_frames[:5]))

    w("═══════════════════════════════════════════════════════════════")
    w("  提炼小JSON: %s" % cpath)
    w("  → agent: 按 reference/hotspot_standard.md 判 P0(流量饱和/数量风暴) / P1(关注) / P2(降压杠杆)。深挖用 `--range A B`。")
    w("    效率类(复制CPU / 相关性浪费=空跑的比对白花CPU)不在热点, 顺带看用 `/netprofile:redundancy`(相关性浪费)。单帧尖峰若疑似可避免 → 同冗余分析。")
    w("  → 上面 Top 榜只是【起点】, 不是分析范围: 逐项尽量全覆盖(只略过明显极低的), 每项走 SKILL「★逐项闭环调查」。")
    w("    产出写进 AnalysisReport/<原nprof名>/: 先各 hotspot-<项>.md, 后主 hotspot.md(总览+判级表+导航)。见 SKILL「★MD 分析报告产出规范」。")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
