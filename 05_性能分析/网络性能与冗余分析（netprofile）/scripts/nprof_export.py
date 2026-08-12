#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nprof_export.py — netprofile 套件【导出】子技能核心 (唯一触碰 .nprof 处)。

把 .nprof 无损 1:1 翻译成结构化 JSON。默认落本 skill 的 json/<原nprof名>/export.json
(相对 __file__, 兼容 .claude/.trae 等); -o 可指定别处。
**不聚合、不裁剪**: header + 名表 + 连接表 + 全部 token 事件, 一条不丢。
聚合/解读由下游子技能 (hotspot/redundancy/...) 各取所需 —— 任何二进制数据都能从这里拿到。

用法:
  python nprof_export.py <file.nprof>          # → <skill>/json/<原nprof名>/export.json
  python nprof_export.py <file.nprof> -o x.json # 自定义输出路径
聚焦/帧区间不在导出层做 (导出永远全量); 由消费子技能对全量 JSON 自行过滤。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nprof_core import parse, TruncatedStream, TOKEN_NAMES  # noqa: E402


def main():
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="无损导出 .nprof → json/<原nprof名>/export.json (netprofile 套件中间件)")
    ap.add_argument("input", help=".nprof 文件路径")
    ap.add_argument("-o", "--output", help="输出 JSON 路径 (默认 <skill>/json/<原nprof名>/export.json)")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.stderr.write("[错误] 找不到文件: %s\n" % args.input)
        sys.exit(2)

    with open(args.input, "rb") as f:
        data = f.read()

    try:
        result = parse(data)
    except ValueError as e:
        sys.stderr.write("[错误] %s\n" % e)
        sys.exit(3)

    out = {
        "meta": {
            "source": os.path.basename(args.input),
            "source_path": args.input,
            "schema": "netprofile-raw/1",
            "note": "二进制 .nprof 的无损 1:1 翻译; 事件按序、名字用名表索引。聚合是消费者的事。",
            "token_types": TOKEN_NAMES,           # 事件 t 码 → 名称
            "event_count": len(result["events"]),
            "field_legend": {
                "f": "帧号(FrameMarker序号,-1=首帧前)", "c": "连接号(连接表索引,-1=未知)",
                "name/actor/func/prop/obj": "名表 names[] 的索引", "conn": "连接表索引",
                "bytes": "字节", "bits/hdr/par/foot/pay/pid/bun/ack/pad": "比特数",
                "ms": "毫秒", "time": "相对秒", "init/owner/sentAll": "布尔",
                "cmpSet/chgSet/inactiveSet": "位图中置位的位下标",
            },
        },
        "header": result["header"],
        "integrity": result["integrity"],   # clean / truncated / unknown
        "names": result["names"],            # 索引→名字
        "connections": result["connections"],  # 索引→地址
        "events": result["events"],          # 全部 token, 按序, 无损
    }
    if result["integrity"] == "truncated":
        sys.stderr.write("[提示] 文件尾部不完整(DS 未干净结束), 已保留全部完整 token。\n")

    if args.output:
        out_path = args.output
    else:
        # 落到本 skill 的 json/<原nprof名>/export.json (相对 __file__, 兼容 .claude/.trae 等); 一次 capture 一个文件夹
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stem = os.path.splitext(os.path.basename(args.input))[0]
        cap_dir = os.path.join(skill_dir, "json", stem)
        os.makedirs(cap_dir, exist_ok=True)
        out_path = os.path.join(cap_dir, "export.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))  # 紧凑: 事件量大

    sys.stdout.write(out_path + "\n")  # stdout = 产物路径 (供 bat / 上游拿到落盘位置)
    sys.stderr.write("[导出完成] %d 事件 / %d 名字 → %s\n" % (
        len(result["events"]), len(result["names"]), out_path))


if __name__ == "__main__":
    main()
