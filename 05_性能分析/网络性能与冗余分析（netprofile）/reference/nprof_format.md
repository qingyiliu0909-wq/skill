# .nprof 二进制格式规格（nprof_core.py 的权威依据）

从引擎写入端逐字段逆出并核对。引擎升级若改序列化，先更新本文件，再改 `scripts/nprof_core.py`。

## 来源
- 写入端/格式定义：`7UE/Engine/Source/Runtime/Engine/Private/NetworkProfiler.cpp`
- 原语：`FArchive::SerializeIntPacked`(Core/Private/Serialization/Archive.cpp:1128)、`FString::SerializeAsANSICharArray`(Core/Private/Containers/String.cpp:681)
- 编译开关：`USE_NETWORK_PROFILER = !(UE_BUILD_SHIPPING || UE_BUILD_TEST)`

## 整体
`[Header][Token]...[NPTYPE_EndOfStreamMarker]`，全文件**小端**，线性 token 流、顺序依赖不可跳读。
名表/地址表**内联流式**：字符串首次出现时流里先插 `NameReference(17)`/`ConnectionReference(18)`，之后用 packed index 回指 → 单次线性扫描边读边建表。

## 原语
- **SerializeIntPacked（变长无符号）**：每字节低 1 位是 more 标志，高 7 位是数据，LSB chunk 在前。解码 `val=0,sh=0; b=读字节; val|=(b>>1)<<sh; sh+=7; 直到 !(b&1)`。
- **SerializeAsANSICharArray（字符串）**：`int32 Length` + `Length` 个单字节 ANSI（无 null 结尾）。
- **bitarray**：`packed NumBits` + `ceil(NumBits/32)` 个 `packed uint32`。

## Header
`uint32 Magic(==0x1DBF348C)` · `uint32 Version` · ANSI `Tag` · ANSI `GameName` · ANSI `URL`。
版本：13 LargeRPCFix（SendRPC bit 字段 uint16→packed）、14 PushModelTracking（新增 token 19/20）。

## Token 表（首字节=类型）
| # | 名称 | 字段 |
|---|---|---|
|0|FrameMarker|`float` RelativeTime|
|1|SocketSendTo|`packed` 名idx, `u16` BytesSent, `u16` PacketIdBits, `u16` BunchBits, `u16` AckBits, `u16` PaddingBits|
|2|SendBunch|`u16` ChannelIndex, `packed` 类型名idx, `u16` HeaderBits, `u16` PayloadBits|
|3|SendRPC|`packed` Actor名idx, `packed` Func名idx, 然后 3 个 bit 字段：v≥13 为 `packed`×3，v<13 为 `u16`×3|
|4|ReplicateActor|`u8` NetFlags, `packed` 名idx, `float` TimeInMS|
|5|ReplicateProperty|`packed` 名idx, `u16` NumBits|
|6|EndOfStreamMarker|（无）遇到即结束|
|7|Event|`packed` Name idx, `packed` Desc idx|
|8|RawSocketData|`u16` Bytes + Bytes 原始字节（仅 NETWORK_PROFILER_TRACK_RAW_NETWORK_DATA=1，默认 0）|
|9|SendAck|`u16` NumBits|
|10|WritePropertyHeader|`packed` 名idx, `u16` NumBits|
|11|ExportBunch|`u16` NumBits|
|12|MustBeMappedGuids|`u16` NumGuids, `u16` NumBits|
|13|BeginContentBlock|`packed` 名idx, `u16` NumBits|
|14|EndContentBlock|`packed` 名idx, `u16` NumBits|
|15|WritePropertyHandle|`u16` NumBits|
|16|ConnectionChanged|`packed` 地址表idx|
|17|NameReference|ANSI 字符串 → 追加名表|
|18|ConnectionReference|ANSI 字符串 → 追加地址表|
|19|PropertyComparison|`packed` 对象名idx, `float` TimeInMS, bitarray Compared, bitarray Changed, 尾随(`packed` NumProps, 若>0 跟 NumProps 个 `packed` idx)。仅 comparison tracking 开|
|20|ReplicatePropertiesMetadata|`packed` 对象名idx, `u8` Flags, bitarray Inactive。仅 comparison tracking 开|

## 已消除的歧义
`SendBunch` 在 cpp 有两套写法：`TrackSendBunch`（1×u16，**无调用方/死代码**）vs `FlushOutgoingBunches`（2×u16 Header+Payload，**引擎唯一路径**）→ **永远按 2×u16 解析**。

## 归属逻辑（关键，曾写反，已按引擎源码 + GUI 对账校正）
**`ReplicateActor` token 在该 actor 的内容【之后】才发**（引擎 `DataChannel.cpp:3202`，TrackReplicateActor 在序列化属性之后调用）。所以流是 `[PROP p1][PROP p2][ACTOR A][PROP p3][ACTOR B]…`，**A 拥有 p1+p2，B 拥有 p3**。
→ 归属模型 = **pending 累积、遇 marker 结算**：property/header bits 先累进 pending，遇到一个 `ReplicateActor` 就把 pending 结算给【这一个】actor 类，然后清零。**不是**"ReplicateActor 开启作用域、其后 bits 归当前 actor"（那是反的，会把每个 actor 的属性算到下一个头上）。
- 帧边界(`FrameMarker`)清空 pending；`FrameMarker` 同时划分帧并把 SocketSendTo 字节归入当前帧。
- 所有消费者(hotspot.aggregate / frame_detail / redundancy.aggregate / prop_drill)都按此 pending 模型；GUI per-actor 带宽对账精确到 0.1KB。

## 排查
magic 不匹配=非 .nprof/截断；未知 token=引擎新增类型(按最新 cpp 更新)；尾部截断=DS 未干净结束(优雅处理，integrity=truncated)。
