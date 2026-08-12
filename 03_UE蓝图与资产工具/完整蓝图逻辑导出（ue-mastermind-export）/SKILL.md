---
name: "ue-mastermind-export"
description: "使用 UnrealMastermind 插件的 Commandlet 导出蓝图原始信息（变量、事件图、函数执行流、控件层级、动画等），输出为纯文本文件。适用于需要蓝图完整逻辑分析的场景，是 ue-blueprint-analyzer（T3D 方案）的替代/补充方案。"
---

# UE Mastermind Export

> **路径配置**：本文件中所有 `{UE4_EDITOR_CMD}`、`{UPROJECT_PATH}`、`{MASTERMIND_EXPORT_DIR}` 等占位符请从 `CONFIG.md`（skills 根目录）读取实际路径。

使用 EM 项目内置的 UnrealMastermind 插件 Commandlet，以 `ExportRawOnly` 模式导出蓝图的结构化纯文本信息。

## 与 ue-blueprint-analyzer（T3D 方案）的区别

| 对比项 | T3D 方案 | Mastermind 方案（本 skill） |
|--------|----------|---------------------------|
| 导出方式 | ExportAssets → T3D → Python 解析为 JSON | UnrealAIBp Commandlet 直接导出纯文本 |
| 输出格式 | 结构化 JSON（widgets/logic/animations 三个文件） | 单个 `.txt` 纯文本（包含所有信息） |
| 信息丰富度 | 控件属性详细（slot、anchor 等） | 逻辑流更完整（执行链追踪、变量使用追踪） |
| 适用场景 | 需要精确查询控件属性、动画 track | 需要理解蓝图整体逻辑、事件流、函数调用链 |
| 依赖 | Python 脚本 + T3D 解析器 | UnrealMastermind 插件（已内置） |

**建议**：两种方案互补使用。需要控件层级细节时用 T3D 方案，需要理解蓝图逻辑流时用本方案。

## 导出内容

UnrealMastermind 的 `ExtractBlueprintInfo` 会提取以下信息：

1. **基本信息** — 蓝图名称、父类
2. **变量** — 名称、类型、在哪些 Graph 中被 Read/Write
3. **事件图（Event Graphs）** — 事件节点 + 执行流追踪（含输入参数值）
4. **函数（Functions）** — 参数列表 + 执行流追踪
5. **组件（Components）** — 名称、类型、关键属性
6. **UI 控件层级**（仅 Widget Blueprint）— 控件名、类型、可见性、Anchor/ZOrder
7. **UI 动画**（仅 Widget Blueprint）— 动画名称列表
8. **文档注释** — Blueprint 中的 Comment 节点

## 工作流程

```
用户请求分析蓝图 → 检查导出文件是否存在 → 不存在则执行 Commandlet → 返回文本数据
```

## 执行步骤

### Step 1: 解析蓝图名称

从用户消息中提取蓝图名称（支持逗号分隔的多个蓝图）：
- "分析 WBP_Battle_HUD 的逻辑" → `WBP_Battle_HUD`
- "导出 WBP_Shop_A,WBP_Shop_B 的蓝图信息" → `WBP_Shop_A,WBP_Shop_B`

### Step 2: 检查数据是否存在

检查 `{MASTERMIND_EXPORT_DIR}/<BlueprintName>.txt` 是否存在。

**判断逻辑**：
- 文件存在 → 跳过导出，直接进入 Step 4
- 文件不存在 → 执行 Step 3

### Step 3: 执行 Commandlet 导出

#### 3.1 执行命令

```bash
"{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=UnrealAIBp -ExportRawOnly -BpFileNames="<BlueprintName>" -RawOutDir="{MASTERMIND_EXPORT_DIR}"
```

多个蓝图时用逗号分隔：
```bash
-BpFileNames="WBP_Shop_A,WBP_Shop_B"
```

> ⚠️ **Commandlet 耗时较长**：`UE4Editor-Cmd` 需要加载 UE 项目资源，通常耗时 **30 秒 ~ 数分钟**。终端工具可能在命令完成前就提前返回（Premature Return），此时**绝不能直接读取输出文件**。

#### 3.2 等待导出完成（强制校验）

> 🔴 **在读取输出文件之前，必须确认文件已完整生成。**

**校验流程**：

1. **检查文件是否存在**：检查 `{MASTERMIND_EXPORT_DIR}/<BlueprintName>.txt` 是否存在。
2. **文件不存在 → 等待重试**：
   - 执行等待：`python -c "import time; time.sleep(15)"`
   - 再次检查文件是否存在
   - 重复上述过程，最多重试 **8 次**（共约 2 分钟）
3. **文件存在 → 检查文件大小稳定性**：
   - 记录当前文件大小
   - 等待 5 秒：`python -c "import time; time.sleep(5)"`
   - 再次检查文件大小
   - 如果大小发生变化（文件仍在写入），继续等待 5 秒后重试
   - 如果大小不再变化 → 文件写入完成，进入 Step 4
4. **超过最大重试次数仍不存在 → 判定导出失败**，向用户报告错误

> ⚠️ **严禁在文件不存在或大小仍在变化时读取输出文件**，否则会读到不完整的数据。

### Step 4: 读取并返回数据

使用 Read 工具读取 `{MASTERMIND_EXPORT_DIR}/<BlueprintName>.txt`，根据用户问题提取相关段落：

| 用户问 | 查找文本段 |
|--------|-----------|
| 有哪些变量 | `Variable Usages:` 段落 |
| 有哪些事件 | `Event Graphs:` 段落 |
| 有哪些函数 | `Functions:` 段落 |
| 有哪些控件 | `UI Widget Hierarchy:` 段落 |
| 有哪些动画 | `UI Animations:` 段落 |
| 有哪些组件 | `Components:` 段落 |
| 执行逻辑/调用链 | 事件或函数段落中的 `→` 执行流 |
| 变量在哪里使用 | `Variable Usages:` 中的 Read/Write 信息 |

## 配置

在 `{SKILLS_ROOT}/CONFIG.md` 中需要以下路径变量：

| 变量 | 说明 |
|------|------|
| `{UE4_EDITOR_CMD}` | UE4Editor-Cmd.exe 路径 |
| `{UPROJECT_PATH}` | .uproject 文件路径 |
| `{MASTERMIND_EXPORT_DIR}` | Mastermind 导出文件输出目录 |

## 示例

### 示例 1: 首次导出

**用户**: 用 mastermind 分析 WBP_Shop_BuySinglePart 蓝图

**助手**:
1. 检查 `{MASTERMIND_EXPORT_DIR}/WBP_Shop_BuySinglePart.txt` → 不存在
2. 执行 Commandlet...
3. 等待文件生成 → 15s 后检查 → 文件存在且大小稳定
4. 读取文件，返回概览

### 示例 2: 数据已存在

**用户**: WBP_Shop_BuySinglePart 有哪些函数？

**助手**:
1. 检查 `{MASTERMIND_EXPORT_DIR}/WBP_Shop_BuySinglePart.txt` → 存在
2. 读取文件中 `Functions:` 段落
3. 返回函数列表

### 示例 3: 批量导出

**用户**: 导出 WBP_Shop_A,WBP_Shop_B,WBP_Shop_C 的蓝图信息

**助手**:
1. 执行一次 Commandlet，`-BpFileNames="WBP_Shop_A,WBP_Shop_B,WBP_Shop_C"`
2. 等待所有文件生成
3. 逐个读取并返回概览

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 导出文件等待超时 | UE4Editor-Cmd 耗时超过 2 分钟或失败 | 检查进程是否仍在运行，或蓝图名称是否正确 |
| 文件内容为 "Invalid Blueprint" | 蓝图加载失败 | 确认蓝图名称拼写正确且项目中存在 |
| 找不到蓝图 | AssetRegistry 中无匹配 | 确认蓝图名称（不含路径前缀和 `_C` 后缀） |
| 插件未启用 | UnrealMastermind 未在项目中启用 | 检查 .uproject 或编辑器中是否启用了该插件 |
