---
name: "ue-blueprint-analyzer"
description: "一站式 UE 蓝图分析工具，自动完成「导出 T3D → 转 JSON → 查询数据」全流程。触发场景：(1) 用户说「分析 XXX 蓝图」「查看 XXX 蓝图数据」「XXX 蓝图有哪些动画/控件/变量」(2) AI 需要获取蓝图数据来实现交互逻辑时"
---

# UE Blueprint Analyzer

一站式蓝图分析工具，自动检测数据是否存在，按需执行完整流程。

## 工作流程

```
用户请求 → 检查 JSON 是否存在 → 
  ├─ 存在 → 直接读取返回
  └─ 不存在 → 导出 T3D → 转 JSON → 返回数据
```

## 执行步骤

### Step 1: 解析蓝图名称

从用户消息提取蓝图名称：
- "分析 WBP_XXX" → `WBP_XXX`
- "WBP_XXX 有哪些动画" → `WBP_XXX`

### Step 2: 检查数据是否存在

检查 `D:/AnalyzeT3D/<BlueprintName>/` 是否有：
- `<BlueprintName>_widgets.json`
- `<BlueprintName>_logic.json`
- `<BlueprintName>_animations.json`

**判断：** 三个文件都存在 → 跳过导出，直接进入 Step 4

### Step 3: 执行导出和转换

#### 3.0 检查配置文件（必须）

> 🔴 **在导出 T3D 之前，必须确认 CONFIG.md 存在且包含必要路径配置。**

检查 `{SKILLS_ROOT}/CONFIG.md` 是否存在：

**如果不存在**，使用 AskUserQuestion 工具询问用户：

```
问题 1: UE4Editor-Cmd.exe 路径
- 提示用户输入完整路径，如: C:/Program Files/Epic Games/UE_4.27/Engine/Binaries/Win64/UE4Editor-Cmd.exe

问题 2: .uproject 文件路径
- 提示用户输入项目文件路径
- 可自动检测当前工作目录下的 .uproject 文件作为默认值推荐
```

收集用户输入后，使用 Write 工具创建 `{SKILLS_ROOT}/CONFIG.md`：

```markdown
# UE Blueprint Analyzer 配置

## 路径配置

UE4_EDITOR_CMD: <用户提供的UE4Editor-Cmd路径>
UPROJECT_PATH: <用户提供的.uproject路径>
T3D_EXPORT_DIR: D:\BlueprintToT3D
T3D_ANALYZE_DIR: D:\AnalyzeT3D
```

配置保存后继续执行 3.1。

#### 3.1 导出 T3D

从 `CONFIG.md` 读取以下路径变量：
- `{UE4_EDITOR_CMD}` — UE4Editor 命令行工具
- `{UPROJECT_PATH}` — 项目 .uproject 文件
- `{T3D_EXPORT_DIR}` — T3D 导出目录

执行命令：
```bash
"{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=ExportAssets "<BlueprintName>" -OutputDir="{T3D_EXPORT_DIR}"
```

> ⚠️ **T3D 导出耗时较长**：`UE4Editor-Cmd` 执行 ExportAssets 需要加载 UE 项目资源，通常耗时 **30 秒 ~ 数分钟**。终端工具可能在命令完成前就提前返回（Premature Return），此时**绝不能直接进入 3.2**。

#### 3.2 等待 T3D 导出完成（强制校验）

> 🔴 **在执行任何 JSON 转换之前，必须确认 T3D 文件已完整生成。**

**校验流程**：

1. **检查 T3D 文件是否存在**：检查 `{T3D_EXPORT_DIR}/<BlueprintName>.t3d` 是否存在。
2. **文件不存在 → 等待重试**：
   - 执行等待：`python -c "import time; time.sleep(15)"`
   - 再次检查文件是否存在
   - 重复上述过程，最多重试 **8 次**（共约 2 分钟）
3. **文件存在 → 检查文件大小稳定性**：
   - 记录当前文件大小
   - 等待 5 秒：`python -c "import time; time.sleep(5)"`
   - 再次检查文件大小
   - 如果大小发生变化（文件仍在写入），继续等待 5 秒后重试
   - 如果大小不再变化 → 文件写入完成，进入 3.3
4. **超过最大重试次数仍不存在 → 判定导出失败**，向用户报告错误

> ⚠️ **严禁在文件不存在或大小仍在变化时执行 JSON 转换脚本**，否则会读取到不完整的 T3D 文件，导致解析结果错误或脚本报错。

#### 3.3 转换为 JSON

确认 T3D 文件完整后，执行以下转换脚本（位于 `{SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/` 目录下）：

```powershell
# 创建输出目录
New-Item -ItemType Directory -Force -Path "{T3D_ANALYZE_DIR}/<BlueprintName>"

# 导出 widgets
python {SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/analyze_t3d_widgets.py "{T3D_EXPORT_DIR}/<BlueprintName>.t3d" -o "{T3D_ANALYZE_DIR}/<BlueprintName>/<BlueprintName>_widgets.json"

# 导出 logic
python {SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/analyze_t3d_logic.py "{T3D_EXPORT_DIR}/<BlueprintName>.t3d" -o "{T3D_ANALYZE_DIR}/<BlueprintName>/<BlueprintName>_logic.json"

# 导出 animations
python {SKILLS_ROOT}/工具类/蓝图分析/t3d-exporter/analyze_t3d_animation.py "{T3D_EXPORT_DIR}/<BlueprintName>.t3d" -o "{T3D_ANALYZE_DIR}/<BlueprintName>/<BlueprintName>_animations.json"
```

### Step 4: 返回数据

| 用户问 | 读取文件 |
|--------|----------|
| 有哪些动画 | `_animations.json` |
| 有哪些控件 | `_widgets.json` |
| 有哪些变量 | `_logic.json` |
| 有哪些函数 | `_logic.json` |

## 依赖 Skills

- `export-assets-t3d` - UE 资产导出为 T3D
- `t3d-exporter` - T3D 转换为 JSON
- `t3d-json-reader` - JSON 数据查询指南

## 配置

所有路径配置统一存放在 `{SKILLS_ROOT}/CONFIG.md` 中，包括：
- `{UE4_EDITOR_CMD}` — UE4Editor-Cmd.exe 路径
- `{UPROJECT_PATH}` — .uproject 文件路径
- `{T3D_EXPORT_DIR}` — T3D 导出目录（默认 `D:\BlueprintToT3D`）
- `{T3D_ANALYZE_DIR}` — JSON 分析结果目录（默认 `D:\AnalyzeT3D`）

如需修改配置，直接编辑 `CONFIG.md` 中对应的路径变量即可，所有依赖该配置的 skill 自动生效。
