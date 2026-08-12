---
name: "t3d-json-reader"
description: "Quick reference for AI to locate specific blueprint data in T3D exported JSON files. Invoke when user asks about widgets, variables, functions, animations, or when implementing interaction logic that needs blueprint names."
---

# T3D JSON Quick Reference

快速查询 JSON 数据的参考指南。

## 配置项

路径从 `{SKILLS_ROOT}/CONFIG.md` 读取：

| CONFIG.md 变量 | 说明 |
|----------------|------|
| `{T3D_ANALYZE_DIR}` | JSON 分析结果目录 |

## 文件位置

`{T3D_ANALYZE_DIR}/<BLUEPRINT_NAME>/`

## 快速查询表

| 需求 | 文件 | 字段路径 |
|------|------|----------|
| 动画列表 | `_animations.json` | `animations[].name` |
| 动画事件 | `_animations.json` | `animations[].events[].event_name` |
| 控件列表 | `_widgets.json` | `widget_tree[].name` |
| 控件类型 | `_widgets.json` | `widget_tree[].widget_class` |
| 控件层级 | `_widgets.json` | `widget_tree[].children` |
| 是否变量 | `_widgets.json` | `widget_tree[].is_variable` |
| 引用的WBP | `_widgets.json` | `widget_tree[].widget_class` (WBP_开头) |
| ListView Entry类 | `_widgets.json` | `widget_tree[].entry_widget_class` (仅ListView类控件) |
| 变量列表 | `_logic.json` | `blueprint.variables[].name` |
| 变量类型 | `_logic.json` | `blueprint.variables[].type` |
| 函数列表 | `_logic.json` | `blueprint.functions[].name` |
| 是否事件 | `_logic.json` | `blueprint.functions[].is_event` |
| 执行链路 | `_logic.json` | `blueprint.functions[].execution_chain` |
| 父类 | `_logic.json` | `blueprint.parent_class` |

## 决策流程

1. **动画相关** → `_animations.json`
2. **控件/UI相关** → `_widgets.json`
3. **函数/变量相关** → `_logic.json`
