# 基础导出规则

## Frame 优先

宏观扫描只请求 `exports.frames`。FrameProvider 数据不需要事件轨道、深度或关键字过滤，也不生成 ExportConfig。

## Timing Events 数据量控制

事件导出必须具备至少一种明确约束：

- `StartTime` 与 `EndTime` 时间窗口；
- 深度或事件耗时范围；
- Game/Rendering 帧耗时范围；
- 明确的事件或关键字白名单。

不了解事件分布时，优先缩小时间范围并使用 `WhiteTracks`。不要在宏观阶段用 GameThread 事件代替 FrameProvider。

## Metadata 完整性

- Metadata 只支持 `exports.metadata.csv_path`。
- 完整 Metadata 必须使用不含 `export_config` 的独立调用。
- 不要把完整 Metadata 与带 Loading、耗时、深度或轨道过滤的 Timing Events 合并调用。
- Metadata CSV 使用专用位置校验，不能依赖异常表头构造字典。

## 帧过滤规则

- 四个帧耗时字段均以秒为单位，必须非负。
- 同类型最小值不得大于最大值。
- Game 条件判断事件开始时间所属的 Game Frame。
- Rendering 条件判断事件开始时间所属的 Rendering Frame。
- 两类条件同时存在时，事件必须同时满足。

## 调用与输出

- 所有目标合并到一次 Analysis Session。
- 只有 Timing Events 输出才写 ExportConfig。
- 进程返回码为 0 不等于成功；所有请求 artifact 都必须通过结构和内容验证。
