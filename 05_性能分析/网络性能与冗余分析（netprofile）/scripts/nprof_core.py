#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nprof_core.py — UE NetworkProfiler .nprof 二进制【无损解析】核心 (零依赖)。

职责: 把 .nprof 一比一翻译成结构化数据 (header + 名表 + 连接表 + 按序全部 token 事件)，
**不做任何聚合、不丢任何信息**。聚合/解读是下游子技能 (hotspot/redundancy/...) 的事。
=> 任何未来子技能想消费二进制里的任何数据, 都能从这份无损数据里拿到。

格式权威依据 (从引擎写入端逐字段逆出并核对):
  7UE/Engine/Source/Runtime/Engine/Private/NetworkProfiler.cpp
  原语: FArchive::SerializeIntPacked (Archive.cpp:1128) / FString::SerializeAsANSICharArray (String.cpp:681)
完整格式规格见 reference/nprof_format.md。

要点:
  - 全文件小端字节序。名表/连接表内联流式 (NameReference/ConnectionReference 的出现顺序=索引)。
  - 每个事件带: 所属帧号 f、当前连接号 c (由 ConnectionChanged 维护)。名字字段一律存名表索引。
  - 尾部截断 (DS 未干净结束) 优雅处理: 已解析的完整 token 全部保留, integrity 标 truncated。
"""

import struct

NETWORK_PROFILER_MAGIC = 0x1DBF348C

# ENetworkProfilingPayloadType (NetworkProfiler.cpp:70) —— 事件里的 "t" 就是这些码
NPTYPE_FrameMarker = 0
NPTYPE_SocketSendTo = 1
NPTYPE_SendBunch = 2
NPTYPE_SendRPC = 3
NPTYPE_ReplicateActor = 4
NPTYPE_ReplicateProperty = 5
NPTYPE_EndOfStreamMarker = 6
NPTYPE_Event = 7
NPTYPE_RawSocketData = 8
NPTYPE_SendAck = 9
NPTYPE_WritePropertyHeader = 10
NPTYPE_ExportBunch = 11
NPTYPE_MustBeMappedGuids = 12
NPTYPE_BeginContentBlock = 13
NPTYPE_EndContentBlock = 14
NPTYPE_WritePropertyHandle = 15
NPTYPE_ConnectionChanged = 16
NPTYPE_NameReference = 17
NPTYPE_ConnectionReference = 18
NPTYPE_PropertyComparison = 19
NPTYPE_ReplicatePropertiesMetadata = 20

# 事件类型码 → 名称 (供下游/人理解; 写入 JSON 的 meta.token_types)
TOKEN_NAMES = {
    0: "FrameMarker", 1: "SocketSendTo", 2: "SendBunch", 3: "SendRPC", 4: "ReplicateActor",
    5: "ReplicateProperty", 7: "Event", 8: "RawSocketData", 9: "SendAck", 10: "WritePropertyHeader",
    11: "ExportBunch", 12: "MustBeMappedGuids", 13: "BeginContentBlock", 14: "EndContentBlock",
    15: "WritePropertyHandle", 16: "ConnectionChanged", 19: "PropertyComparison",
    20: "ReplicatePropertiesMetadata",
}

VER_LargeRPCFix = 13  # SendRPC bit 字段从 uint16 改为 packed
VER_PushModelTracking = 14


class TruncatedStream(Exception):
    """缓冲不足以读完当前 token —— 文件尾部被截断 (会话未干净结束)。视为优雅结束。"""


class Reader:
    """对 .nprof 字节缓冲的游标读取器, 实现引擎序列化原语的解码。"""

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.size = len(data)

    def eof(self):
        return self.pos >= self.size

    def _need(self, n):
        if self.pos + n > self.size:
            raise TruncatedStream("需要 %d 字节 @ offset %d, 仅剩 %d" % (n, self.pos, self.size - self.pos))

    def u8(self):
        self._need(1)
        b = self.data[self.pos]
        self.pos += 1
        return b

    def u16(self):
        self._need(2)
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def u32(self):
        self._need(4)
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def i32(self):
        self._need(4)
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32(self):
        self._need(4)
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def packed(self):
        """FArchive::SerializeIntPacked: 每字节低位是 more 标志, 高 7 位是数据, LSB chunk 在前。"""
        value = 0
        shift = 0
        while True:
            b = self.u8()
            value |= (b >> 1) << shift
            shift += 7
            if not (b & 1):
                break
        return value

    def ansi_str(self):
        """FString::SerializeAsANSICharArray: int32 Length + Length 个单字节 ANSI 字符 (无 null 结尾)。"""
        length = self.i32()
        if length <= 0:
            return ""
        raw = self.data[self.pos:self.pos + length]
        self.pos += length
        return raw.decode("latin-1", errors="replace")

    def bitarray(self):
        """ProfilerSerializeBitArray: packed NumBits + ceil(NumBits/32) 个 packed uint32 dword。
        无损返回 (num_bits, [置位的位下标...])。"""
        num_bits = self.packed()
        num_dwords = (num_bits + 31) >> 5
        set_bits = []
        for i in range(num_dwords):
            dword = self.packed() & 0xFFFFFFFF
            base = i * 32
            while dword:
                low = dword & -dword
                set_bits.append(base + low.bit_length() - 1)
                dword ^= low
        return num_bits, set_bits


def parse(data):
    """单次线性扫描 .nprof, 无损产出。返回 dict:
       {header, integrity, names[], connections[], events[]}  —— 不聚合、不丢信息。
    每个 event 含 t(类型码)、f(帧号, -1=首帧前)、c(连接号, -1=未知) + 该 token 的全部字段。"""
    r = Reader(data)
    names = []
    connections = []
    events = []

    magic = r.u32()
    if magic != NETWORK_PROFILER_MAGIC:
        raise ValueError("magic 不匹配: 0x%08X (期望 0x%08X). 非 .nprof 或字节序异常。" % (magic, NETWORK_PROFILER_MAGIC))
    version = r.u32()
    header = {"magic": magic, "version": version,
              "tag": r.ansi_str(), "game": r.ansi_str(), "url": r.ansi_str()}

    frame = -1   # 当前帧号 (FrameMarker 递增)
    conn = -1    # 当前连接号 (ConnectionChanged 维护)
    integrity = "unknown"
    ev = events.append

    while not r.eof():
        try:
            t = r.u8()
            if t == NPTYPE_FrameMarker:
                time = r.f32()
                frame += 1
                ev({"t": t, "f": frame, "time": time})

            elif t == NPTYPE_SocketSendTo:
                ev({"t": t, "f": frame, "c": conn, "name": r.packed(),
                    "bytes": r.u16(), "pid": r.u16(), "bun": r.u16(), "ack": r.u16(), "pad": r.u16()})

            elif t == NPTYPE_SendBunch:
                ev({"t": t, "f": frame, "c": conn, "ch": r.u16(), "name": r.packed(),
                    "hdr": r.u16(), "pay": r.u16()})

            elif t == NPTYPE_SendRPC:
                actor = r.packed()
                func = r.packed()
                if version >= VER_LargeRPCFix:
                    hdr, par, foot = r.packed(), r.packed(), r.packed()
                else:
                    hdr, par, foot = r.u16(), r.u16(), r.u16()
                ev({"t": t, "f": frame, "c": conn, "actor": actor, "func": func,
                    "hdr": hdr, "par": par, "foot": foot})

            elif t == NPTYPE_ReplicateActor:
                flags = r.u8()
                ev({"t": t, "f": frame, "c": conn, "actor": r.packed(), "ms": r.f32(),
                    "init": bool(flags & 0x2), "owner": bool(flags & 0x4)})

            elif t == NPTYPE_ReplicateProperty:
                ev({"t": t, "f": frame, "c": conn, "prop": r.packed(), "bits": r.u16()})

            elif t == NPTYPE_EndOfStreamMarker:
                integrity = "clean"
                break

            elif t == NPTYPE_Event:
                ev({"t": t, "f": frame, "c": conn, "name": r.packed(), "desc": r.packed()})

            elif t == NPTYPE_RawSocketData:
                n = r.u16()
                r._need(n)
                ev({"t": t, "f": frame, "bytes": n})  # 原始负载默认关闭; 此处只记长度
                r.pos += n

            elif t == NPTYPE_SendAck:
                ev({"t": t, "f": frame, "c": conn, "bits": r.u16()})

            elif t == NPTYPE_WritePropertyHeader:
                ev({"t": t, "f": frame, "c": conn, "prop": r.packed(), "bits": r.u16()})

            elif t == NPTYPE_ExportBunch:
                ev({"t": t, "f": frame, "c": conn, "bits": r.u16()})

            elif t == NPTYPE_MustBeMappedGuids:
                ev({"t": t, "f": frame, "c": conn, "guids": r.u16(), "bits": r.u16()})

            elif t == NPTYPE_BeginContentBlock or t == NPTYPE_EndContentBlock:
                ev({"t": t, "f": frame, "c": conn, "obj": r.packed(), "bits": r.u16()})

            elif t == NPTYPE_WritePropertyHandle:
                ev({"t": t, "f": frame, "c": conn, "bits": r.u16()})

            elif t == NPTYPE_ConnectionChanged:
                conn = r.packed()
                ev({"t": t, "f": frame, "conn": conn})

            elif t == NPTYPE_NameReference:
                names.append(r.ansi_str())  # 顺序=索引, 即名表 (无损)

            elif t == NPTYPE_ConnectionReference:
                connections.append(r.ansi_str())  # 顺序=索引, 即连接表 (无损)

            elif t == NPTYPE_PropertyComparison:
                obj = r.packed()
                ms = r.f32()
                cmp_bits, cmp_set = r.bitarray()
                chg_bits, chg_set = r.bitarray()
                num_props = r.packed()
                prop_names = [r.packed() for _ in range(num_props)]
                ev({"t": t, "f": frame, "c": conn, "obj": obj, "ms": ms,
                    "cmpBits": cmp_bits, "cmpSet": cmp_set, "chgBits": chg_bits, "chgSet": chg_set,
                    "propNames": prop_names})

            elif t == NPTYPE_ReplicatePropertiesMetadata:
                obj = r.packed()
                flags = r.u8()
                ina_bits, ina_set = r.bitarray()
                ev({"t": t, "f": frame, "c": conn, "obj": obj,
                    "sentAll": bool(flags & 0x1), "inactiveBits": ina_bits, "inactiveSet": ina_set})

            else:
                raise ValueError("未知 token 类型 %d @ offset %d (流不可跳过, 解析中止)。" % (t, r.pos - 1))
        except TruncatedStream:
            integrity = "truncated"
            break

    return {"header": header, "integrity": integrity,
            "names": names, "connections": connections, "events": events}
