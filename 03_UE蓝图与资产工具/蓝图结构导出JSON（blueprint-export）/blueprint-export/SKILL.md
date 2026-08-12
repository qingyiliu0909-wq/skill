---
name: blueprint-export
description: UE 蓝图导出工具，将蓝图资产导出为结构化 JSON 文件（含变量、组件、图表、节点、连接关系）。触发场景：用户要求导出蓝图、分析蓝图逻辑结构、查看蓝图节点/变量/事件时。
---

# Blueprint Export - 蓝图导出工具

## 使用方式

执行前先从 `{SKILLS_ROOT}/CONFIG.md` 读取路径变量。

```bash
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport -Path="/Game/Path/To/Blueprint" [-Output="D:/output/"] [-Indent=true]
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `-Path` | ✅ | 蓝图路径，如 `/Game/Blueprints/BP_MyCharacter` |
| `-Output` | ❌ | 输出目录，默认 `{EM_ROOT}\Saved\BlueprintExport` |
| `-Indent` | ❌ | 是否美化 JSON，默认 `true` |

## 导出内容

JSON 文件包含：
- **蓝图基础信息**：路径、名称、父类、类型（Widget/Animation/Interface 等）、描述
- **变量列表**：名称、类型、默认值、属性标志
- **组件列表**：名称、类型、属性值
- **图表信息**：EventGraph、Function、Macro
- **节点与引脚**：类型、标题、连接关系
- **事件列表**：蓝图中的事件和自定义事件名称
- **注释**：图表中的 Comment 节点

## 输出位置

默认输出到：`{EM_ROOT}\Saved\BlueprintExport\<蓝图名>.json`

## 示例

```bash
# 导出单个蓝图
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport -Path="/Game/BluePrints/Combat/PassiveEffect/DesignerBP/Mod/BP_Char_1311"

# 指定输出目录，不美化
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport -Path="/Game/UI/WBP_Main" -Output="D:/Export/" -Indent=false
```

## 注意事项

- 使用 `UE4Editor-Cmd.exe` 而不是 `UE4Editor.exe`（命令行模式，无窗口）
- PowerShell 中需要用 `& "路径"` 语法调用带空格的路径

---

## 分析导出的 JSON 文件

### JSON 结构

```json
{
  "version": "1.0",
  "exportTime": "导出时间",
  "blueprint": {
    "path": "蓝图路径",
    "name": "蓝图名称",
    "parentClass": "父类名",
    "blueprintType": "Normal/Widget/Animation/Interface/...",
    "description": "蓝图描述",
    "variables": [...],
    "components": [...],
    "graphs": [{
      "name": "EventGraph",
      "type": "EventGraph/Function",
      "nodes": [...],
      "connections": [...]
    }],
    "events": [...],
    "comments": [...]
  }
}
```

### 分析技巧

#### 1. 找执行流入口

入口节点类型：
- `K2Node_Event` - 标准事件（BeginPlay、Tick 等）
- `K2Node_ComponentBoundEvent` - 组件绑定事件（如 Damage 事件）
- `K2Node_CustomEvent` - 自定义事件

从这些节点的 `then` 引脚开始追踪执行流。

#### 2. 追踪节点连接

在 `connections` 数组中：
- `fromNodeGuid` / `toNodeGuid` 对应节点的 `guid`
- `fromPin` / `toPin` 是引脚名称

追踪方法：从入口节点的 `then` 引脚出发，按 `fromNodeGuid` 找连接，再用 `toNodeGuid` 定位下一节点。

#### 3. 常见节点类型

| 节点类型 | 说明 |
|----------|------|
| `K2Node_CallFunction` | 函数调用，标题是函数名 |
| `K2Node_VariableGet` | 读取变量 |
| `K2Node_VariableSet` | 设置变量 |
| `K2Node_IfThenElse` | 分支判断 |
| `K2Node_Branch` | 分支（同 IfThenElse） |
| `K2Node_Self` | 自引用 |
| `K2Node_DynamicCast` | 类型转换 |

#### 4. 分析函数调用参数

在 `K2Node_CallFunction` 节点的 `pins.inputs` 中：
- 参数的 `defaultValue` 是硬编码值
- 参数的 `connectedTo` 是从其他节点获取的值

#### 5. 识别蓝图模式

**被动效果模式**（如 BP_Char_1311）：
- 父类：`BP_PassiveEffectBase_C`
- 常用变量：`PassiveOwner`（拥有者）
- 常用函数：`Add Buff To Target`（添加 Buff）
- 触发方式：`BeginPlay` 初始化 + 事件触发（如 Damage 事件）

**UI 模式**：
- 父类：`UserWidget` 或自定义 Widget 基类
- 常用：`BindWidget`、动画、事件分发器

### 分析输出格式

分析导出文件时，按以下结构组织信息：

1. **基本信息**：名称、父类、类型、描述
2. **变量列表**：名称、类型、属性
3. **执行流**：从入口到出口的完整流程（用箭头图表示）
4. **关键函数调用**：函数名、参数来源
5. **节点统计**：各类节点数量
6. **总结**：蓝图的核心功能
