---
name: "t3d-exporter"
description: "Exports Unreal Engine T3D blueprint files to JSON format using three analysis scripts (widgets, blueprint, animation). Invoke when user wants to analyze or export T3D files to JSON."
---

# T3D to JSON Exporter

将 T3D 文件转换为结构化 JSON。

## 配置项

所有路径从 `{SKILLS_ROOT}/CONFIG.md` 读取：

| CONFIG.md 变量 | 说明 |
|----------------|------|
| `{T3D_EXPORT_DIR}` | T3D 源文件所在目录 |
| `{T3D_ANALYZE_DIR}` | JSON 分析结果输出目录 |
| `{SKILLS_ROOT}` | Skills 根目录（脚本位于 `{SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/`） |

## 输出目录

`{T3D_ANALYZE_DIR}/<FILENAME>/`

## 三个分析脚本

| 脚本 | 输出文件 | 功能 |
|------|----------|------|
| `analyze_t3d_widgets.py` | `_widgets.json` | 控件层级、属性、文本 |
| `analyze_t3d_logic.py` | `_logic.json` | 变量、函数、事件、执行链 |
| `analyze_t3d_animation.py` | `_animations.json` | 动画名称、事件触发时间 |

## 执行命令

```powershell
# 创建目录
New-Item -ItemType Directory -Force -Path "{T3D_ANALYZE_DIR}/<NAME>"

# 执行三个脚本
python {SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/analyze_t3d_widgets.py "{T3D_EXPORT_DIR}/<NAME>.t3d" -o "{T3D_ANALYZE_DIR}/<NAME>/<NAME>_widgets.json"
python {SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/analyze_t3d_logic.py "{T3D_EXPORT_DIR}/<NAME>.t3d" -o "{T3D_ANALYZE_DIR}/<NAME>/<NAME>_logic.json"
python {SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/analyze_t3d_animation.py "{T3D_EXPORT_DIR}/<NAME>.t3d" -o "{T3D_ANALYZE_DIR}/<NAME>/<NAME>_animations.json"
```

## JSON 结构概览

### _widgets.json
```json
{
  "total_widgets": 72,
  "widget_tree": [{"name": "...", "widget_class": "...", "is_variable": true, "children": [...]}]
}
```

### _logic.json
```json
{
  "blueprint": {
    "parent_class": "...",
    "variables": [{"name": "...", "type": "..."}],
    "functions": [{"name": "...", "is_event": false, "execution_chain": [...]}]
  }
}
```

### _animations.json
```json
{
  "total_animations": 10,
  "animations": [{"name": "In", "events": [{"event_name": "...", "trigger_time": 0.0}]}]
}
```
