# UnrealInsights 导出协议

## 启动协议

traceloader 使用：

```text
-OpenTraceFile=<trace>
-ExportConfig=<event-config>          # 仅存在 Timing Events 输出时
-ABSLOG=<log>
-ExecOnAnalysisCompleteCmd=<cmd1;cmd2;...>
-AutoQuit
-NoUI
```

同一配置的命令用分号连接，只启动一次 UnrealInsights。

| 输出目标 | 命令 |
|---|---|
| Frame JSONL | `TimingInsights.ExportFramesToJSON` |
| Frame CSV | `TimingInsights.ExportFramesToCSV` |
| Metadata CSV | `TimingInsights.ExportMetadataToCSV` |
| Timing Events JSONL | `TimingInsights.ExportTimingEventsToJSON` |
| Timing Events CSV | `TimingInsights.ExportTimingEventsToCSV` |

## Frame 数据

Frame JSONL 一行一帧：

```json
{"frameType":"Game","frameIndex":120,"start":10.0,"end":10.0167,"duration":0.0167}
```

CSV 列为：

```text
FrameType,FrameIndex,Start,End,Duration
```

- `frameType` 为 `Game` 或 `Rendering`。
- `start`、`end`、`duration` 单位为秒。
- 两类帧是独立时间序列，FrameIndex 不要求对应。
- 未闭合的无限尾帧不会导出。

## Timing Events 数据

JSONL 一行是一棵导出事件树。同一真实 Game Frame 内可能有多棵 depth-0 事件树，因此不得用行号或根 Timer 名称推算帧。

## Metadata CSV

Metadata CSV 只保留带 Metadata 的 Timing Event，常用于读取 package。当前引擎存在已知格式问题：
表头写成 6 列，而数据行实际至少有 7 列。读取时跳过表头，按位置解析
`ThreadId, Name, Start, End, Duration, Depth`，再把第 7 列及后续列合并为 Metadata。

需要完整 Metadata 时使用独立的 metadata-only 配置且不传 `export_config`。带过滤的 Timing
Events 与 Metadata 共用一次调用时，当前引擎会把同一事件过滤应用到 Metadata。

## ExportConfig

常用字段：

| 字段 | 类型 | 单位/语义 |
|---|---|---|
| `StartTime` / `EndTime` | Number | 秒，必须成对出现 |
| `MinDepth` / `MaxDepth` | Integer | 事件深度 |
| `MinDuration` / `MaxDuration` | Number | 事件耗时，秒 |
| `WhiteTracks` / `BlackTracks` | String[] | 轨道包含匹配 |
| `WhiteEvents` / `BlackEvents` | String[] | 事件精确匹配 |
| `WhiteKeywords` / `BlackKeywords` | String[] | 事件名包含匹配 |
| `MinGameFrameDuration` / `MaxGameFrameDuration` | Number | 事件开始时间所属 Game Frame 的耗时，秒 |
| `MinRenderingFrameDuration` / `MaxRenderingFrameDuration` | Number | 事件开始时间所属 Rendering Frame 的耗时，秒 |

Game 与 Rendering 条件同时存在时取交集。纯 Frame 导出不读取 ExportConfig。

## 分卷与 artifact

主文件使用请求路径，后续卷命名为 `_part2`、`_part3`。traceloader 返回每个请求目标的主路径和有序 `parts`，并验证：

- 主文件存在且非空；
- JSONL 至少一条合法记录；
- CSV 有表头和数据行；
- Metadata CSV 至少有一行 7 列数据，时间、耗时和深度可解析，Metadata 非空；
- Frame 文件至少出现 Game 或 Rendering。
