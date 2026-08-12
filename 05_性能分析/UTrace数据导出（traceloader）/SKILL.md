---
name: traceloader
description: 通过 UnrealInsights 将 UTrace 导出为真实 FrameProvider 帧数据或 Timing Events，并验证输出 artifact。
---

# traceloader

## 能力

- 导出 Game/Rendering FrameProvider JSONL 或 CSV。
- 导出 Timing Events JSONL 或 CSV。
- 导出带 Metadata 的 Timing Events CSV，用于 package 等元数据分析。
- 在一次 Analysis Session 中组合多个输出。
- 分析真实帧分布或 Timing Events 事件树。
- 串行批量导出子系统事件。

## 唯一输入

Agent 只向导出入口传入一个 JSON 配置文件路径。配置可位于任意目录；技能不感知 `.worker` 或调用方的目录规则。

```powershell
python scripts/export_trace.py "D:\anywhere\task.traceloader.json"
```

配置必须自包含：

```json
{
  "unreal_insights_path": "D:/XGame/unrealengine/Engine/Binaries/Win64/UnrealInsights.exe",
  "trace_file_path": "D:/traces/sample.utrace",
  "log_path": "D:/output/sample/export.log",
  "exports": {
    "frames": {
      "json_path": "D:/output/sample/frames.json",
      "csv_path": null
    },
    "timing_events": {
      "json_path": "D:/output/sample/events.json",
      "csv_path": null
    },
    "metadata": {
      "csv_path": "D:/output/sample/metadata.csv"
    }
  },
  "export_config": {
    "StartTime": 10.0,
    "EndTime": 12.0,
    "MinGameFrameDuration": 0.033,
    "WhiteTracks": ["GameThread"]
  }
}
```

`exports` 至少有一个非空目标。只有 Frame 或 Metadata 导出时可省略 `export_config`。
Metadata 只支持 CSV。需要完整 Metadata 时必须单独调用且不传 `export_config`；不要和带过滤的
Timing Events 放在同一调用中，因为当前引擎会让两者共享事件过滤配置。

## 默认流程

1. 先用 frames-only 配置导出真实 Game/Rendering 帧。
2. 用 `analyze_trace.py --type frames` 计算分位数和慢帧区间。
3. 根据帧结果选择时间窗口、轨道和帧耗时条件。
4. 再导出 Timing Events 并用 `--type events` 分析事件树。
5. 需要子系统数据时调用 `batch_export_subsystems.py`，保持串行执行。

资源加载专项使用两次串行调用：先导出 Frames 与带最小耗时约束的 Loading Events，再单独
导出完整 Metadata CSV。

## 强制约束

- 不得直接调用或拼装 `UnrealInsights.exe` 命令。
- 不得自行解析 `.utrace`。
- 一次配置中的多个导出目标必须由一次 UnrealInsights 进程完成。
- 成功必须同时满足进程成功和全部已请求 artifact 的内容门禁。
- 事件 JSONL 的一行是一棵事件树，不代表一个真实帧。
- Game 与 Rendering 是独立 FrameProvider 序列，不共享 FrameIndex。

## 入口

```powershell
python scripts/export_trace.py <config-path>
python scripts/analyze_trace.py <frames.json> --type frames
python scripts/analyze_trace.py <events.json> --type events
python scripts/batch_export_subsystems.py --help
```

## 按需阅读

- 配置、命令、schema 和 artifact：`unrealinsights.md`
- 配置审查与数据量控制：`rules/basic_export_rules.md`
- 事件过滤字段选择：`rules/event_filter_rules.md`
- 宏观分析和下钻方法：由调用方性能工作流链接对应专项知识。
