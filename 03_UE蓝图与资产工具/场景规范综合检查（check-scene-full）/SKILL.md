---
name: check-scene-full
description: "综合场景检查：LevelBounds、模型移动性、合批、反射球、跨关卡模型、贴花、SimpleRuntimeActor、图层分配、LevelProxy。Use when user asks to check scene, 检查场景, or 场景检查。"
---

# 综合场景检查工具

**重要：本 Skill 被调用时，必须自动按顺序执行以下所有步骤，不要只展示代码或等待用户确认，而是直接用工具完成每一步操作。**

## Skill 目录结构

```
.skill/美术场景类/场景检查类/check-scene-full/
├── SKILL.md                  # 本文件
├── SceneFullCheck.py         # Python 检查脚本（支持命令行自动执行）
└── ConvertJsonToTable.ps1    # JSON → Markdown 表格转换脚本
```

## 平台模式判断

根据用户的表述自动判断检查平台：

| 用户表述 | 平台参数 | 搜索范围 | 检查项 |
|---------|---------|---------|--------|
| "检查场景" / 未指定平台 | **必须询问用户**（PC / 手机 / 全部） | 由用户选择 | 由用户选择的平台决定 |
| "检查电脑/PC场景" | `-Platform=pc` | 仅 Maps | 仅通用项（1,4,5,8,9） |
| "检查手机/移动端场景" | `-Platform=phone` | 仅 Maps_Phone | 全部9项 |
| "检查全部/all" | `-Platform=all` | Maps + Maps_Phone | 全部9项（Maps_Phone专属项仅对Maps_Phone关卡生效） |

## 检查项指定

当用户指定了具体检查项时，只执行对应的检查（平台规则依旧生效）。用户表述与检查项的对应关系：

| 用户表述关键词 | 检查项参数 | 说明 |
|--------------|-----------|------|
| LevelBounds / 关卡边界 / 边界 | `LevelBounds` | 检查 LevelBounds Transform |
| 移动性 / 静态 / Mobility | `Mobility` | 检查模型移动性是否为静态 |
| 合批 / 组合批 / 聚类合批 / HISM / ISM | `Batching` | 检查打组合批/聚类合批 |
| 反射球 / ReflectionCapture | `ReflectionSphere` | 输出反射球名称 |
| 跨关卡 / 跨Level / 过大模型 | `CrossLevel` | 检查模型是否跨3个以上关卡 |
| 贴花 / Decal | `Decal` | 检查场景贴花 |
| SimpleRuntime / ASimpleRuntime | `SimpleRuntimeActor` | 检查 SimpleRuntimeTextureActor |
| 图层 / Layer | `Layer` | 检查图层分配 |
| LevelProxy / 关卡代理 | `LevelProxy` | 检查 LevelProxy 及引用 |

**示例**：
- "检查场景的LevelBounds" → `-CheckItems=LevelBounds`
- "检查手机端场景的移动性和贴花" → `-Platform=phone -CheckItems=Mobility,Decal`
- "检查场景"（未指定具体项）→ 不传 `-CheckItems`，执行全部9项

---

## 第一步：解析用户输入，确定主场景名和平台

**关键规则：先尝试从用户原始指令中提取参数，缺什么才问什么，不要重复询问。**

按以下顺序解析：

1. **主场景名提取**：从指令中查找形如 `Xxx_Main` / `ChapterXX_Xxx` 的标识符（如 `Haiboliya_Chezhan_Main`、`Chapter01_IcelakeCity`、`Huaxu_Haojing_Main`）。若用户用引号、@ 或路径形式给出，也直接采用。
2. **平台提取**：
   - 含"手机/移动/phone/Maps_Phone" → `phone`
   - 含"电脑/PC/Maps（不含 _Phone）" → `pc`
   - 含"全部/all" → `all`
   - **未提及平台** → 置空，进入询问流程（不要默认 all）
3. **检查项提取**：参考"检查项指定"小节的关键词表，匹配到则填入 `-CheckItems`，否则不传。

**仅在缺失关键参数时**用 AskQuestion 工具询问：
- 缺主场景名 → 问主场景名
- 缺平台（用户没明确说 pc/phone/all）→ **必须问平台**（PC / 手机 / 全部）

> 不要把 3 个问题（场景名/平台/检查项）一起问。检查项默认就是全部 9 项，不需要问。

---

## 第二步：验证主场景文件存在

根据平台模式选择搜索目录：

| 平台 | 搜索目录 |
|------|---------|
| all | `E:\Trunk\Content\Maps\Levels\` 和 `E:\Trunk\Content\Maps_Phone\Levels\` |
| pc | 仅 `E:\Trunk\Content\Maps\Levels\` |
| phone | 仅 `E:\Trunk\Content\Maps_Phone\Levels\` |

用 Shell 工具执行（**注意：仅传 `-Path` 一个目录时使用以下命令；多个目录用逗号分隔**）：

```powershell
Get-ChildItem -Path "E:\Trunk\Content\Maps_Phone\Levels" -Filter "{MainLevelName}.umap" -Recurse -ErrorAction SilentlyContinue | Select-Object FullName
```

### 兜底逻辑（**重要，实战中必须执行**）

如果上述命令**没有返回任何 FullName**（输出仅有空行或表头），不要立刻报错，先扩大到整个 Content 目录确认：

```powershell
Get-ChildItem -Path "E:\Trunk\Content" -Filter "{MainLevelName}.umap" -Recurse -ErrorAction SilentlyContinue | Select-Object FullName
```

根据兜底结果判定：

| 兜底结果 | 处理 |
|---------|------|
| 整个 Content 都找不到 | **立即停止**，告知用户场景不存在 |
| 找到了，但都不在指定平台目录 | **立即停止**，提示用户该场景不属于指定平台 |
| 找到了，至少有一个在指定平台目录 | 继续执行第三步 |

> 实战经验：`Get-ChildItem -Recurse` 在某些深层路径或 `.umap` 文件不在标准命名空间下时可能返回为空，扩大范围后能找到说明确实存在。

---

## 第三步：执行检查（UE4Editor-Cmd 调 Python）

用 Shell 工具运行：

```powershell
& "E:\UE7\Engine\Binaries\Win64\UE4Editor-Cmd.exe" "E:\Trunk\EM.uproject" -ExecutePythonScript="E:\Trunk\.skill\美术场景类\场景检查类\check-scene-full\SceneFullCheck.py" -MainLevel={MainLevelName} -Platform={Platform} -CheckItems={CheckItems} -unattended -NullRHI -NoSound
```

参数填充：
- `{Platform}`：`all` / `pc` / `phone`
- `{CheckItems}`：逗号分隔（如 `LevelBounds,Mobility`）；**全部检查时直接省略 `-CheckItems` 整个参数**，不要传空字符串
- `{MainLevelName}`：主场景名（不带 `.umap` 后缀）

### Shell 调用参数（必须设置）

- `block_until_ms`: **1800000**（30 分钟，足够兜底）
- 实测耗时参考：~250 子关卡 ≈ 1.5 分钟，~500 子关卡 ≈ 3~5 分钟。命令很可能比 30 分钟早很多就退出。

### 命令完成后的双重验证（**两个都必须做**）

#### 验证 1：结果文件存在且大小 > 0

```powershell
cmd /c "dir E:\Trunk\SceneFullCheck*"
```

> **不要用 `Get-ChildItem -Filter "SceneFullCheck*"` 验证**：实战中该命令在 PowerShell 5 下会返回空（即使文件存在），原因疑似与名称匹配规则相关。`cmd /c dir` 始终可靠。

应至少看到 `SceneFullCheckResult.json`，文件大小 > 1KB。

#### 验证 2：日志中出现"运行完成"标记

读取最新日志（`E:\Trunk\Saved\Logs\EM.log`），用 Grep 搜索：

```
模式：Scene full check found
```

应找到类似这一行：
```
LogPython: Error: Scene full check found 1851 error(s), 4 warning(s), 248 info out of 246 level(s) checked. Results written to: ../../../../Trunk/SceneFullCheckResult.json
```

> 注意：这条日志虽然 UE 用 `LogPython: Error:` 前缀输出，但**不是真正的报错**，是脚本主动用 `LogPython.error()` 打印汇总以便高亮显示。

如果只看到 `Intermediate results saved at [X/Y]` 而没有最终汇总行，说明被打断了（如内存溢出、用户中止），**JSON 中的数据不完整，必须重新执行第三步**。

---

## 第四步：转换为 Markdown 表格

```powershell
powershell -ExecutionPolicy Bypass -File "E:\Trunk\.skill\美术场景类\场景检查类\check-scene-full\ConvertJsonToTable.ps1" -JsonPath "E:\Trunk\SceneFullCheckResult.json"
```

成功输出：`Table written to: E:\Trunk\SceneFullCheckResult.md`

> `.md` 文件用于人工查阅与归档，**LLM 不要直接 Read 它**（实战中可达 400~500KB+，会爆上下文）。

---

## 第五步：用 PowerShell 解析 JSON 汇总（**核心步骤**）

**关键规则：必须用 PowerShell 解析 `SceneFullCheckResult.json` 进行分组聚合，禁止 Read `.md` 文件。**

### JSON 结构（已固定，请直接按此使用）

顶层字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `TotalChecked` | int | 实际检查的子关卡数 |
| `TotalErrors` | int | Error 总数 |
| `TotalWarnings` | int | Warning 总数 |
| `TotalInfo` | int | Info 总数 |
| `CheckTime` | string | 检查时间 `YYYY-MM-DD HH:mm:ss` |
| `Results` | array | 所有检查结果数组 |

每条 `Results` 元素字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `LevelName` | string | 关卡名（不含 .umap 后缀） |
| `CheckType` | string | 见下方枚举 |
| `RuleType` | string | 中文规则类型描述 |
| `ActorName` | string | Actor 名称（无则为空字符串） |
| `Description` | string | 详细描述（中文） |
| `Severity` | string | `Error` / `Warning` / `Info` |
| `LayerInfo` | object | 仅 `Layer` 类型有效 |

`CheckType` 枚举值：`LevelBounds` / `Mobility` / `Batching` / `ReflectionSphere` / `CrossLevel` / `Decal` / `SimpleRuntimeActor` / `Layer` / `LevelProxy`

### 编码强制要求（**忽略会乱码**）

每次启动 PowerShell 命令时**必须**先：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

读 JSON **必须**用 `-Raw -Encoding UTF8`：

```powershell
$json = Get-Content "E:\Trunk\SceneFullCheckResult.json" -Raw -Encoding UTF8 | ConvertFrom-Json
```

### 必跑：标准汇总脚本

复制以下脚本作为一个 Shell 命令执行：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$json = Get-Content "E:\Trunk\SceneFullCheckResult.json" -Raw -Encoding UTF8 | ConvertFrom-Json

"=== Summary ==="
"CheckTime    : $($json.CheckTime)"
"TotalChecked : $($json.TotalChecked)"
"Errors       : $($json.TotalErrors)"
"Warnings     : $($json.TotalWarnings)"
"Info         : $($json.TotalInfo)"
""
"=== Error 按 CheckType / RuleType 聚合 ==="
$json.Results | Where-Object Severity -eq 'Error' | Group-Object CheckType, RuleType | Sort-Object Count -Descending | ForEach-Object { "{0,6} | {1}" -f $_.Count, $_.Name }
""
"=== Error Top 20 关卡 ==="
$json.Results | Where-Object Severity -eq 'Error' | Group-Object LevelName | Sort-Object Count -Descending | Select-Object -First 20 | ForEach-Object { "{0,5} | {1}" -f $_.Count, $_.Name }
""
"=== Warning 全部列出 ==="
$json.Results | Where-Object Severity -eq 'Warning' | ForEach-Object { "{0} | {1} | {2} | {3} | {4}" -f $_.LevelName, $_.CheckType, $_.RuleType, $_.ActorName, $_.Description }
""
"=== Info 按 CheckType / RuleType 聚合 ==="
$json.Results | Where-Object Severity -eq 'Info' | Group-Object CheckType, RuleType | Sort-Object Count -Descending | ForEach-Object { "{0,6} | {1}" -f $_.Count, $_.Name }
""
"=== ReflectionSphere 详情 ==="
$json.Results | Where-Object {$_.CheckType -eq 'ReflectionSphere'} | ForEach-Object { "{0} | {1}" -f $_.LevelName, $_.Description }
```

### 按需追加：细化某个 CheckType

针对 Error 数最多的 1~2 个 CheckType 再细分（参考下方按需脚本片段，用同一 PowerShell 命令组合执行）：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$json = Get-Content "E:\Trunk\SceneFullCheckResult.json" -Raw -Encoding UTF8 | ConvertFrom-Json

"=== Decal Error Top 10 关卡 ==="
$json.Results | Where-Object {$_.Severity -eq 'Error' -and $_.CheckType -eq 'Decal'} | Group-Object LevelName | Sort-Object Count -Descending | Select-Object -First 10 | ForEach-Object { "{0,4} | {1}" -f $_.Count, $_.Name }
""
"=== Batching Error 按 RuleType + LevelName Top 15 ==="
$json.Results | Where-Object {$_.Severity -eq 'Error' -and $_.CheckType -eq 'Batching'} | Group-Object RuleType, LevelName | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { "{0,4} | {1}" -f $_.Count, $_.Name }
""
"=== Batching Error Top Actor ==="
$json.Results | Where-Object {$_.Severity -eq 'Error' -and $_.CheckType -eq 'Batching'} | Group-Object ActorName | Sort-Object Count -Descending | Select-Object -First 20 | ForEach-Object { "{0,4} | {1}" -f $_.Count, $_.Name }
""
"=== LevelBounds Error 全部列出 ==="
$json.Results | Where-Object {$_.Severity -eq 'Error' -and $_.CheckType -eq 'LevelBounds'} | ForEach-Object { "{0,-65} | {1} | {2}" -f $_.LevelName, $_.RuleType, $_.Description }
```

---

## 第六步：输出报告（**固定格式，必须遵循**）

按以下结构组织最终回复给用户。**禁止省略章节，禁止逐条列 Error**。

```
## 场景检查报告：{MainLevelName}（{Platform}）

- 检查时间：{CheckTime}
- 检查子关卡数：{TotalChecked}
- Error：{N}  |  Warning：{M}  |  Info：{K}
- 结果文件：E:\Trunk\SceneFullCheckResult.json / .md

### 一、Error（必须修复）— {N} 条

按规则类型聚合（表格：数量 / CheckType / RuleType / 简要说明）

#### 1. {第一大类 CheckType}（{n1} 条）
- Top 5~10 关卡列表

#### 2. {第二大类 CheckType}（{n2} 条）
- Top 5~10 关卡列表
- （如有必要）涉及的 Actor 类型 Top 列表

（其余 CheckType 简略列出）

### 二、Warning（建议关注）— {M} 条

| 关卡 | 检查项 | 描述 |
（全部列出，Warning 通常 ≤ 10 条）

### 三、Info（参考）— {K} 条

按类型聚合 + ReflectionSphere 详情

### 四、通过项（无问题）

列出 0 错误的检查项（如 Mobility、CrossLevel、SimpleRuntimeActor、LevelProxy）

### 五、修复建议

按 Error 数量从高到低给出 3~5 条修复建议，并标记任何异常关卡名（如 ID 数字串错乱、命名不规范）。
```

### 报告硬性规则

- **禁止** 用 Read 工具读取 `SceneFullCheckResult.md` 全文
- **禁止** 在报告中逐条列出超过 10 条同类 Error
- **必须** 完整列出所有 Warning（通常数量少）
- **必须** 列出"通过项"小节，让用户知道哪些检查项无问题
- **必须** 给出修复建议章节
- **建议** 标记任何看起来异常的关卡名（如出现 `_10737418241073741824` 这类异常长数字串）

---

## 检查项说明

| # | 检查项 | 通用项/手机专属 | 说明 |
|---|--------|---------------|------|
| 1 | LevelBounds Transform | 通用 | 检查 Position、Scale、bAutoUpdateBounds 是否符合规范（同 check-levelbounds） |
| 2 | 模型移动性 | 手机专属 | StaticMeshActor 的 Mobility 应为 Static |
| 3 | 打组合批/聚类合批 | 手机专属 | 检查 Actor 是否包含 HierarchicalInstancedStaticMeshComponent（组合批）或 InstancedStaticMeshComponent（聚类合批） |
| 4 | 反射球名称 | 通用 | 输出所有 SphereReflectionCapture/ReflectionCapture 的名称 |
| 5 | 跨关卡模型 | 通用 | 检查 StaticMeshActor 是否因过大与关卡边界 3 个或以上面交叉 |
| 6 | 场景贴花 | 手机专属 | 检查是否存在 DecalActor |
| 7 | SimpleRuntimeActor | 手机专属 | 检查是否存在 SimpleRuntimeTextureActor |
| 8 | 图层分配 | 通用 | 输出每个关卡的图层分配情况 |
| 9 | LevelProxy | 通用 | 检查关卡是否存在 LevelProxy，以及其引用是否有效 |

**手机专属检查项**只在 Maps_Phone 路径下的关卡中执行，即使在 all 模式下，Maps 路径的关卡也不会执行这些检查。

## Severity 规则

| Severity | 条件 | 含义 |
|----------|------|------|
| **Error** | 关卡名称中包含数字（如 `_0102BigObjs`） | 必须修复的异常 |
| **Warning** | 关卡名称中不包含数字（如 `_DividedFoliage_TypH`） | 建议关注的警告 |
| **Info** | 信息类结果（如反射球列表、图层分配） | 仅供参考 |

## LevelBounds 检查规则（同 check-levelbounds）

| 规则 | 异常条件 |
|------|---------|
| Position异常 | X、Y、Z 绝对值均 < 100 |
| Scale异常 | Scale 与关卡名称关键字不匹配 |
| bAutoUpdateBounds异常 | 特定关卡该属性为 true |
| 缺少LevelBounds | 关卡中无 LevelBounds Actor |

### Scale 与关卡名称对应表

| 关卡名称关键字 | 期望 Scale |
|---------------|-----------|
| DividedFoliageOther | (25600, 25600, Z>1000) |
| Big / Huge / Mou / DividedFoliage | (12800, 12800, Z>1000) |
| Small | (6400, 6400, Z>1000) |

## 修改检查规则

修改 `.skill/美术场景类/场景检查类/check-scene-full/SceneFullCheck.py` 后重新执行即可，无需编译。

---

## 注意事项 / 常见坑

- 只检查 WorldComposition 的子关卡 Tiles（含 `_Art_`/`_Design_`/`_Task_`/`DividedEffect`/`DividedFoliage`），不检查 Persistent Level
- 跳过名称中包含 `_LOD1` 的子关卡
- 每 50 个关卡进行一次增量保存和垃圾回收，防止内存溢出
- JSON 默认输出到项目根目录 `SceneFullCheckResult.json`，同时生成 Markdown 表格 `SceneFullCheckResult.md`
- **当用户指定的检查项在当前平台下全部不可执行时（如PC模式下只指定了手机专属项），脚本不会执行任何检查，并输出错误提示告知用户**

### LLM 易踩坑提醒

| 坑 | 正确做法 |
|----|---------|
| `Get-ChildItem -Filter "SceneFullCheck*"` 无输出 | 改用 `cmd /c "dir E:\Trunk\SceneFullCheck*"` |
| PowerShell 输出中文乱码 | 命令开头加 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` |
| `ConvertFrom-Json` 中文乱码 | 加 `-Raw -Encoding UTF8` 读 JSON |
| 把 `SceneFullCheckResult.md` Read 进上下文 | 禁止；只读 JSON 并用 PowerShell 聚合 |
| 命令早早 exit 后以为失败 | 检查 JSON 文件 + 日志中 `Scene full check found` 行确认 |
| 命令日志只到 `[X/Y]` 没有最终行 | 视为未完成，重新执行第三步 |
| 把 `LogPython: Error:` 误认为脚本报错 | 该前缀只是高亮显示，最终汇总行用此前缀输出 |
| 把假 0,0,0 警告也算成 Error | Warning 单独列出，不要并入 Error 修复清单 |
