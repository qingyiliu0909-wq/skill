---
name: "export-umap-json"
description: "使用 ExportUmapInfo Commandlet 将 UE 关卡 (.umap) 导出为 JSON 格式。触发场景：用户说'导出 XXX 关卡为JSON'、'分析 XXX 地图结构'、'export XXX umap to JSON'、'获取 XXX 地图信息'、'导出移动端 XXX 关卡'。自动将 Design 子关卡的 Actor 数据嵌入主关卡 JSON 的 WorldCompositionTiles 中，过滤掉 _Design_XXXX 格式的嵌套子关卡。若主关卡未开启 WorldComposition 则直接报错。支持 PC 端和移动端关卡路径自动搜索。"
---

# Export Umap to JSON

将 UE4 关卡（`.umap`）的结构信息导出为 JSON 文件，包含 Actor 列表和 WorldComposition 子关卡信息。

## 导出内容

单个 JSON 文件（主关卡）包含：
- `MapName` / `MapPath` — 地图名称和完整路径
- `Actors` — 主关卡 Actor 数组（Name, Class, Label, Location）
- `WorldCompositionTiles` — 子关卡列表，每个 tile 包含：
  - `PackageName`, `Position`, `AbsolutePosition`, `Bounds`, `Layer`, `ParentTilePackageName`, `ZOrder`, `RealStreamingDistance`, `LODList`, `LODPackageNames`
  - `Actors` — **仅 Design 子关卡有此字段**，包含该子关卡的所有 Actor

> **注意**：Design 子关卡的 Actor 数据直接嵌入到对应 tile 的 `Actors` 字段中，不再生成独立的 JSON 文件。

## 触发方式

- "导出 Chapter01 关卡为 JSON"
- "分析 Chapter01 地图"
- "获取 Chapter01 的地图信息"
- "export Chapter01 umap to JSON"
- "导出移动端 Chapter01 关卡为 JSON"
- "checkwclevel Chapter01 phone"

## 输入参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `关卡名/路径` | 关卡名称或完整路径 | 必填 |
| `isMobile` | 是否为移动端关卡 | `false` |

**移动端标识检测**：用户消息中包含以下任一关键词时，`isMobile = true`：
- "移动端"、"phone"、"mobile"、"手机端"、"Maps_Phone"
- 触发词为 `checkwclevel` 且参数包含 `phone`

## 导出路径

固定输出到项目目录的 `Saved/.umap-json/` 下：
```
{EM_ROOT}/Saved/.umap-json/
```

## 前置检查

**若主关卡未开启 WorldComposition**，Commandlet 会直接报错并停止导出：
```
Error: WorldComposition is not enabled or has no tiles for: <UmapPath>
```

## 配置项

所有路径从 `.skill/CONFIG.md` 读取：

| CONFIG.md 变量 | 说明 | 默认值 |
|----------------|------|--------|
| `{UE4_EDITOR_CMD}` | UE4Editor-Cmd.exe 路径 | 必填 |
| `{UPROJECT_PATH}` | 项目 .uproject 文件路径 | 必填 |
| `{EM_ROOT}` | 项目根目录 | 必填 |

> 首次使用前需确认 CONFIG.md 存在。如不存在，询问用户 `UE4_EDITOR_CMD` 和 `UPROJECT_PATH` 路径，并创建 CONFIG.md。

## 执行流程

### Step 1: 解析输入

#### 1.1 检测移动端标志

从用户消息中检测移动端关键词，确定 `isMobile` 值：
- 包含 "移动端"/"phone"/"mobile"/"手机端"/"Maps_Phone" → `isMobile = true`
- 否则 → `isMobile = false`

#### 1.2 确定搜索根目录

| isMobile | 搜索根目录（文件系统） | 对应 /Game 前缀 |
|----------|----------------------|----------------|
| `false`（默认） | `{EM_ROOT}/Content/Maps/Levels/` | `/Game/Maps/Levels/` |
| `true` | `{EM_ROOT}/Content/Maps_Phone/Levels/` | `/Game/Maps_Phone/Levels/` |

#### 1.3 搜索关卡文件

**若输入以 `/Game/` 开头**：直接使用输入路径，无需搜索。

**若输入不以 `/Game/` 开头**：视为关卡名，在确定的搜索根目录及其子目录下递归搜索匹配的 `.umap` 文件。

搜索命令示例：
```powershell
# 非移动端
Get-ChildItem -Path "{EM_ROOT}/Content/Maps/Levels" -Recurse -Filter "*<关卡名>*.umap"

# 移动端
Get-ChildItem -Path "{EM_ROOT}/Content/Maps_Phone/Levels" -Recurse -Filter "*<关卡名>*.umap"
```

**搜索结果处理**：
- 未找到 → 报错并提示用户检查关卡名或切换移动端/PC端
- 找到 1 个 → 直接使用
- 找到多个 → 列出所有匹配项，**使用 AskUserQuestion 让用户选择**

**路径转换**：将文件系统路径转换为 `/Game/...` 格式作为 Commandlet 输入：
- 去掉 `{EM_ROOT}/Content/` 前缀
- 将路径分隔符统一为 `/`
- 去掉 `.umap` 后缀

例如：
- `{EM_ROOT}/Content/Maps/Levels/Chapter01/Chapter01_Main/Chapter01.umap` → `/Game/Maps/Levels/Chapter01/Chapter01_Main/Chapter01`
- `{EM_ROOT}/Content/Maps_Phone/Levels/Chapter01/Chapter01_Main/Chapter01.umap` → `/Game/Maps_Phone/Levels/Chapter01/Chapter01_Main/Chapter01`

### Step 2: 计算输出目录

```
OutputDir = {EM_ROOT}/Saved/.umap-json
```

如目录不存在，自动创建。

### Step 3: 执行导出命令

```bash
"{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=ExportUmapInfo "<UmapPath>" -OutputDir="<OutputDir>" -stdout -unattended -NoShaderCompile -nullrhi
```

### Step 4: 等待导出完成

> ⚠️ **UE4Editor-Cmd 执行耗时较长**（30秒~数分钟），终端可能提前返回。

**校验流程**：
1. 检查主关卡 JSON 是否存在：`{OutputDir}/<MapName>_info.json`
2. 文件不存在 → 等待 10 秒后重试，最多 12 次（共约 2 分钟）
3. 文件存在 → 检查文件大小是否稳定
   - 大小变化 → 等待 5 秒后重试
   - 大小稳定 → 导出完成
4. 超时仍不存在 → 报告导出失败

### Step 5: 报告结果

只生成 **一个** 主关卡 JSON 文件：

```
✅ 导出成功！
  文件: {EM_ROOT}/Saved/.umap-json/Chapter01_info.json
  平台: PC端（isMobile=false）
  内容:
    - 主关卡 Actors: <N> 个
    - WorldCompositionTiles: <N> 个
    - 其中嵌入 Actors 的 Design 子关卡: <N> 个
```

## 过滤规则

Commandlet 内部已实现的过滤逻辑：
- ✅ 名称包含 `"Design"` 的子关卡 → **嵌入 Actors 到 tile**
- ❌ 名称包含 `"_Design_"` 的子关卡（如 `Chapter01_Design_0101`）→ **跳过**
- ❌ 非 Design 子关卡 → **只导出 tile 元数据，不嵌入 Actors**

## JSON 结构示例

```json
{
  "MapName": "Chapter01",
  "MapPath": "/Game/Maps/Levels/Chapter01/Chapter01_Main/Chapter01.Chapter01",
  "Actors": [
    { "Name": "EMWorldSettings", "Class": "EMWorldSettings", "Label": "...", "Location": { "X": 0, "Y": 0, "Z": 0 } }
  ],
  "WorldCompositionTiles": [
    {
      "PackageName": "/Game/.../Chapter01_Art_Breakable",
      "Position": { "X": 0, "Y": 0, "Z": 0 },
      "Bounds": { "Min": {...}, "Max": {...} },
      "Layer": { "Name": "Noload", "StreamingDistance": 15000 },
      "...": "..."
      // 无 Actors 字段（非 Design 子关卡）
    },
    {
      "PackageName": "/Game/.../Chapter01_Flow_Design",
      "Position": { "X": 0, "Y": 0, "Z": 0 },
      "Bounds": { "Min": {...}, "Max": {...} },
      "Layer": { "Name": "AlwaysLoad", "StreamingDistance": 2147483647 },
      "...": "...",
      "Actors": [
        { "Name": "BP_GridFrame_Flow", "Class": "BP_GridFrame_C", "Label": "...", "Location": {...} }
      ]
    }
  ]
}
```

## 相关文件

- Commandlet 实现: `Source/EMEditor/Private/Commandlet/ExportUmapInfoCommandlet.cpp`
- Commandlet 头文件: `Source/EMEditor/Public/Commandlet/ExportUmapInfoCommandlet.h`
