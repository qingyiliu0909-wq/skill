---
name: "export-assets-t3d"
description: "Exports Unreal Engine assets to T3D format using ExportAssets Commandlet. Invoke when user wants to export blueprint or other assets to T3D files with configurable paths and persistent settings. Also invoke when user says '导出 XXX 为T3D' or 'export XXX YYY to T3D'."
---

# Export Assets to T3D

将 UE 资产导出为 T3D 格式文件。

## 触发方式

- "导出 WBP_XXX 为T3D"
- "导出 WBP_A,WBP_B,WBP_C 为T3D"
- "export WBP_XXX to T3D"

## 配置项

所有路径从 `{SKILLS_ROOT}/CONFIG.md` 读取：

| CONFIG.md 变量 | 说明 | 默认值 |
|----------------|------|--------|
| `{UE4_EDITOR_CMD}` | UE4Editor-Cmd.exe 路径 | 无（必填） |
| `{UPROJECT_PATH}` | 项目 .uproject 文件路径 | 无（必填） |
| `{T3D_EXPORT_DIR}` | T3D 导出输出目录 | `D:\BlueprintToT3D` |

## 执行流程

### Step 1: 解析蓝图名称

从用户消息提取蓝图名称：
- "导出 WBP_XXX 为T3D" → `WBP_XXX`
- "导出 WBP_A,WBP_B,WBP_C 为T3D" → `WBP_A`, `WBP_B`, `WBP_C`
- "export WBP_XXX to T3D" → `WBP_XXX`

### Step 2: 检查配置文件

检查 `{SKILLS_ROOT}/CONFIG.md` 是否存在：

**如果不存在**，使用 AskUserQuestion 工具询问用户：

```
问题 1: UE4Editor-Cmd.exe 路径
- 提示用户输入完整路径，如: `C:/Program Files/Epic Games/UE_4.27/Engine/Binaries/Win64/UE4Editor-Cmd.exe`

问题 2: .uproject 文件路径
- 提示用户输入项目文件路径，如: `E:/PAN01-SVN/demo/EM/EM.uproject`
- 可自动检测当前工作目录下的 .uproject 文件作为参考
```

收集用户输入后，使用 Write 工具创建 `{SKILLS_ROOT}/CONFIG.md`：

```markdown
# UE Blueprint Analyzer 配置

## 路径配置

UE4_EDITOR_CMD: <用户提供的路径>
UPROJECT_PATH: <用户提供的路径>
T3D_EXPORT_DIR: D:\BlueprintToT3D
T3D_ANALYZE_DIR: D:\AnalyzeT3D
```

> ⚠️ **注意**: 首次配置需要用户交互，配置保存后后续使用无需再次询问。

### Step 3: 执行导出命令

从 CONFIG.md 读取路径变量，执行：

```bash
"{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=ExportAssets "<Asset1>,<Asset2>" -OutputDir="{T3D_EXPORT_DIR}"
```

> ⚠️ **T3D 导出耗时较长**：UE4Editor-Cmd 需要加载项目资源，通常耗时 30秒~数分钟。终端可能提前返回，需等待 T3D 文件完整生成。

### Step 4: 等待导出完成

检查 `{T3D_EXPORT_DIR}/<BlueprintName>.t3d` 是否存在且文件大小稳定：
- 文件不存在 → 等待 15 秒后重试，最多 8 次
- 文件大小变化 → 等待 5 秒后重试
- 文件稳定 → 导出成功

### Step 5: 报告结果

告知用户导出成功及 T3D 文件路径。

## 相关文件

- Commandlet 实现: `Source/EMEditor/Private/Commandlet/ExportAssetsCommandlet.cpp`
