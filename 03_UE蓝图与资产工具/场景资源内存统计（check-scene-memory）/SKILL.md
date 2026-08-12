---
name: check-scene-memory
description: "统计 WorldComposition 子关卡中 StaticMesh/Texture/Material 内存占用（GetResourceSizeBytes 口径，子关卡内去重），以及 LOD0 三角形×实例数与资源内存×实例数的 StaticMesh Top5。Use when user asks 检查场景内存, 场景内存, 内存检查, scene memory, or mesh/texture/material memory size for a level."
---

# 场景内存检查（GetResourceSizeBytes 口径 / 子关卡 StaticMesh / 贴图 / 材质 + 面数 + 内存加权 Top5）

**本 Skill 被调用时，应按顺序自动执行下列步骤：用工具完成验证与命令执行，不要只贴脚本让用户自行运行。**

## 口径说明（必读）

- 本 Skill 的"内存"统一指 **`UObject::GetResourceSizeBytes(EResourceSizeMode::Exclusive)`**，反映资源加载到内存后的常驻占用近似（含 CPU/GPU 资源），**不是磁盘字节**。
- 与 UE Editor "Size Map" / "Asset Audit" 里的 Memory 列同口径。
- UE5/UE4 Python 默认未暴露 `GetResourceSizeBytes`，本 Skill 依赖项目自带的 C++ wrapper：`UPythonExtensionFunctionLibrary::GetObjectResourceSizeBytes(UObject*, bool bExclusive)`，定义在 `Source/EMEditor/Public/Common/PythonExtensionFunctionLibrary.h`。
- `Exclusive` 模式下 Material 自身内存只算 master/instance 自身（不含其引用贴图），避免与 Texture 项重复计入；Texture 的内存即贴图 RHI / bulk data 占用。

## 目录结构

```
.skill/美术场景类/场景检查类/check-scene-memory/
├── SKILL.md                       # 本文件
├── SceneMemoryCheck.py            # UE Python 脚本（UE4Editor-Cmd / UnrealEditor-Cmd 执行）
└── ConvertMemoryJsonToTable.ps1   # 把结果 JSON 转成 Markdown 表格
```

## 触发词

当用户提到以下任一意图时使用本 Skill：

- 检查场景内存、场景资源内存、关卡内存、子关卡内存
- StaticMesh / 贴图 / 材质 内存、VRAM 占用、运行时内存
- 场景中面数最多、三角形最多的模型、Top mesh
- 哪个 mesh 在场景中占用内存最多（实例×内存）

## 输出含义（必读）

| 指标 | 含义 |
|------|------|
| **StaticMeshMemoryBytes** | 该子关卡内出现的 **不同** StaticMesh 资源 `GetResourceSizeBytes(Exclusive)` 合计（每个网格资源只计一次）。 |
| **TextureMemoryBytes** / **MaterialMemoryBytes** | 以关卡内引用的 StaticMesh 包为根，用 AssetRegistry 做依赖 BFS 得到的闭包中，归类为 Texture* / Material* / MaterialInstance* 等资源的 `GetResourceSizeBytes(Exclusive)` 合计（子关卡内去重）。 |
| **IncludeEngineRefs** | 默认 `0`：只统计 `/Game/` 下包；引擎共享贴图（多在 `/Engine/`）**不计入**，材质若只引用引擎贴图则贴图合计可能偏小。设为 `1` 时同时统计 `/Engine/` 依赖。 |
| **Top5MeshesByLOD0TrianglesWeighted** | 按 **StaticMesh 资源** 聚合：该子关卡所有 `StaticMeshComponent`（含 ISM/HISM）上 **LOD0 三角形数 × 实例数** 之和，取前 5 名（用于定位面数大头）。 |
| **Top5MeshesByMemoryWeighted** | 按 **StaticMesh 资源** 聚合：**单个 mesh 内存 × 实例数** 之和，取前 5 名（用于定位运行时常驻内存大头）。 |
| **TotalMemoryBytes** / **TotalMemoryHuman** | 单个子关卡内 `StaticMeshMemoryBytes + TextureMemoryBytes + MaterialMemoryBytes` 的合计与人类可读格式。 |
| **TopSubLevels.ByTotalMemoryBytes** | **子关卡** 按 `TotalMemoryBytes` 倒序 Top5。条目包含 `LevelName` 及三类资源内存（字节与人类可读）。 |
| **TopSubLevels.ByStaticMeshMemoryBytes** | 子关卡按 `StaticMeshMemoryBytes` 倒序 Top5。 |
| **TopSubLevels.ByTextureMemoryBytes** | 子关卡按 `TextureMemoryBytes` 倒序 Top5。 |
| **TopSubLevels.ByMaterialMemoryBytes** | 子关卡按 `MaterialMemoryBytes` 倒序 Top5。 |
| **TopAssets.ByStaticMeshMemoryBytes** | **全主关卡去重**后按内存字节倒序 Top5 **单个** StaticMesh。条目含 `AssetName`/`PackageName`/`DiskPath`（仅作为定位用的 .uasset 路径）/`MemoryBytes`/`MemoryHuman`。 |
| **TopAssets.ByTextureMemoryBytes** | 同上，Texture 单资源 Top5。 |
| **TopAssets.ByMaterialMemoryBytes** | 同上，Material / MaterialInstance 单资源 Top5。 |
| **UniqueGrandTotals** | 整个主关卡范围真实去重的三类内存合计。 |
| **SumOfPerLevel** | 各子关卡内 `StaticMeshMemoryBytes / TextureMemoryBytes / MaterialMemoryBytes` 的简单相加；**跨子关卡复用的资源会重复计入**。 |
| **LoadFailedPackages** | 加载失败的资源包名（前 50 个），其内存按 0 计入；`LoadFailedPackageCount` 为总数。 |

三角形通过 `unreal.ProceduralMeshLibrary.get_section_from_static_mesh` 读取 LOD0 各 Section；需工程启用 **Procedural Mesh** 相关模块（多数 UE 模板默认包含）。

## 平台模式（与 check-scene-full 一致）

| 用户表述 | `-Platform` | 搜索主关卡 `.umap` 的目录 |
|---------|------------|---------------------------|
| 未指定 / 全部 | `all` | `Content/Maps/Levels` + `Content/Maps_Phone/Levels` |
| 电脑 / PC | `pc` | 仅 `Content/Maps/Levels` |
| 手机 / 移动端 | `phone` | 仅 `Content/Maps_Phone/Levels` |

若用户已说明平台，则不再询问。

## 第零步：自动探测 UE 引擎与项目根路径（强制执行，不得跳过）

后续所有 Shell 命令都需要 3 个具体文件路径：

- `UEEditorCmd` —— `UnrealEditor-Cmd.exe` 或 `UE4Editor-Cmd.exe` 的绝对路径
- `UProjectPath` —— 当前项目的 `.uproject` 绝对路径
- `SceneMemoryCheckScript` —— 本 Skill 同目录下 `SceneMemoryCheck.py` 的绝对路径

本步骤的任务是**先尝试自动探测，只有在全部手段都失败时才 AskQuestion 让用户补齐**，绝对不能直接写死 `E:\UE7\...` / `E:\Trunk\EM.uproject`。

### 0.1 探测项目根路径 `ProjectRoot`

按顺序尝试，第一个命中就停下：

1. Cursor 当前工作区根目录（系统上下文里 `Workspace Path` 字段就是），用 Glob 在该目录下找 `*.uproject`，若唯一则 `ProjectRoot` = 该目录，`UProjectPath` = 该文件。
2. 若工作区根下没有 `.uproject`，用 Glob `**/*.uproject` 向下搜一层级（深度 ≤ 3），只认唯一结果。
3. 若找到多个 `.uproject`，**不要猜**，直接进入 0.3 让用户选。

### 0.2 探测 UE 引擎根路径 `EngineRoot`

按顺序尝试，第一个能定位到真实存在的 `Engine\Binaries\Win64\*Editor-Cmd.exe` 就停下：

1. **读 `{ProjectRoot}\.vscode\tasks.json`**：用 Grep/Read 抓 `"command"` 字段里形如 `...\Engine\Build\BatchFiles\Build.bat` 或 `...\Engine\Binaries\Win64\UE4Editor.exe` / `UnrealEditor.exe` 的值，去掉 `\Engine\...` 尾部即 `EngineRoot`。
2. **读 `{ProjectRoot}\CLAUDE.md` / `AGENTS.md`**：同样用 Grep 抓 `Build.bat` / `Editor-Cmd.exe` 的绝对路径再截断。
3. **读 `{ProjectRoot}\*.uproject`**（JSON）里的 `EngineAssociation`：
   - 若值形如 `"5.3"` / `"4.27"`，查注册表键 `HKLM:\SOFTWARE\EpicGames\Unreal Engine\<版本>\InstalledDirectory`（用 `powershell -Command "Get-ItemProperty -Path 'HKLM:\SOFTWARE\EpicGames\Unreal Engine\5.3' -Name InstalledDirectory"`）。
   - 若值是 `{GUID}` 形式，查 `HKCU:\Software\Epic Games\Unreal Engine\Builds` 下该 GUID 对应的字符串值。
4. **环境变量**：`$env:UE_INSTALL_LOCATION`、`$env:UnrealEngineDir`。
5. **常见安装位置扫描**（用 PowerShell `Test-Path` / `Get-ChildItem`）：
   - `C:\Program Files\Epic Games\UE_*`
   - `C:\UE*`、`D:\UE*`、`E:\UE*`、`F:\UE*`（如 `E:\UE7`、`D:\UE_5.3`）
   命中多个时取修改时间最新的一个。
6. **符号链接线索**：若项目根有 `compile_commands.json` 符号链接，读取其 target，形如 `.../UE7/compile_commands.json`，向上一级就是 `EngineRoot`。

命中后用 `Test-Path` 验证 `{EngineRoot}\Engine\Binaries\Win64\UnrealEditor-Cmd.exe` 与 `UE4Editor-Cmd.exe`，**优先 UE5 的 `UnrealEditor-Cmd.exe`，否则回落到 `UE4Editor-Cmd.exe`**，结果赋给 `UEEditorCmd`。

### 0.3 探测失败时向用户询问

只要 `ProjectRoot` 或 `EngineRoot` 任何一个没有探测到（或探测到的路径验证不存在），用 AskQuestion / 直接追问，让用户提供**根路径**（不要让用户手填具体 exe / uproject 路径）：

- 询问项目根目录（示例：`E:\Trunk`）
- 询问 UE 引擎根目录（示例：`E:\UE7`，即包含 `Engine` 文件夹的上一级）

拿到根路径后，仍由 Agent 按下列规则定位具体文件，**禁止直接相信用户手填的可执行路径**：

- `UProjectPath` = `{ProjectRoot}` 下唯一的 `*.uproject`（多个则再问用户选哪个）
- `UEEditorCmd` = `{EngineRoot}\Engine\Binaries\Win64\UnrealEditor-Cmd.exe`，不存在则回落到 `UE4Editor-Cmd.exe`，都不存在则报错并再次询问

### 0.4 Skill 自身脚本路径

`SceneMemoryCheckScript` = 本 `SKILL.md` 同目录下的 `SceneMemoryCheck.py`。当 Agent 在其它项目中调用本 Skill 时，也应按 SKILL.md 的实际绝对路径推导，而不是写死 `E:\Trunk\.skill\...`。

### 0.5 把探测结果固化为本次会话变量

最后向用户简要汇报探测结果（一行摘要即可），随后的所有 Shell 命令都必须用这组变量拼接，不允许再出现硬编码绝对路径。

## 第一步：检查 C++ wrapper 是否已就绪

本 Skill 依赖项目自带的 C++ wrapper：`UPythonExtensionFunctionLibrary::GetObjectResourceSizeBytes`。

1. **静态检查**：用 Grep 在 `{ProjectRoot}\Source\EMEditor\Public\Common\PythonExtensionFunctionLibrary.h` 中确认存在 `GetObjectResourceSizeBytes`。若不存在：
   - 提示用户：本项目尚未集成内存口径所需的 C++ wrapper，无法执行内存检查。可让用户在 `UPythonExtensionFunctionLibrary` 类中添加：

     ```cpp
     UFUNCTION(BlueprintCallable, Category = "EM|Memory")
     static int64 GetObjectResourceSizeBytes(UObject* Object, bool bExclusive = true);
     ```

     并在 `.cpp` 中实现：

     ```cpp
     int64 UPythonExtensionFunctionLibrary::GetObjectResourceSizeBytes(UObject* Object, bool bExclusive)
     {
         if (!Object) return 0;
         const EResourceSizeMode::Type Mode =
             bExclusive ? EResourceSizeMode::Exclusive : EResourceSizeMode::EstimatedTotal;
         return Object->GetResourceSizeBytes(Mode);
     }
     ```
   - 然后停止本次执行。

2. **动态检查（推荐）**：可选地让 Agent 跑一次最小 Python 命令，确认 wrapper 已被 Python 反射到（避免源码改了但没重新编译的情况）：

   ```powershell
   & "{UEEditorCmd}" "{UProjectPath}" -ExecutePythonScript="import unreal; print('HAS_WRAPPER=' + str(hasattr(unreal.PythonExtensionFunctionLibrary, 'get_object_resource_size_bytes')))" -unattended -NoSound
   ```

   日志中若没看到 `HAS_WRAPPER=True`，说明源码已加但 EMEditor 模块尚未重新编译。让用户先执行一次：

   ```powershell
   & "{EngineRoot}\Engine\Build\BatchFiles\Build.bat" EMEditor Win64 Development "{UProjectPath}" -WaitMutex
   ```

## 第二步：主场景名与平台

用 AskQuestion（或用户已在对话中写明）确认：

1. 主 Persistent 关卡名（无 `.umap` 后缀），例如 `Chapter01_IcelakeCity`
2. 平台：`all` / `pc` / `phone`

## 第三步：验证主关卡存在

用 PowerShell 在 `{ProjectRoot}\Content\Maps\Levels` 或 `{ProjectRoot}\Content\Maps_Phone\Levels`（按平台模式表）下递归查找 `{MainLevelName}.umap`。找不到则停止并说明失败。路径一律基于第零步探测到的 `ProjectRoot`，不得硬编码盘符。

## 第四步：执行内存统计

用 Shell 调用 UE 命令行。**重要：内存口径会把所有 Mesh / Texture / Material 真正加载到内存以读取 `GetResourceSizeBytes`，耗时与峰值内存比磁盘版高 3-10 倍**，几百个子关卡可能数十分钟到 1 小时以上，建议在工作机而不是 CI 上跑，**等待时间需给足**。

**重要：不要加 `-NullRHI`**。`-NullRHI` 会跳过贴图的 PlatformData / RHI 初始化，导致所有 `Texture` 的 `GetResourceSizeBytes` 与 `CalcTextureMemorySizeEnum` 全部返回 0，统计完全失真。Mesh / Material 不受影响，但 Texture 会被全部记 0。

命令必须用第零步得到的 `UEEditorCmd` / `UProjectPath` / `SceneMemoryCheckScript` 变量拼接，**绝对不允许写死 `E:\UE7\...` 或 `E:\Trunk\EM.uproject`**：

```powershell
& "{UEEditorCmd}" "{UProjectPath}" -ExecutePythonScript="{SceneMemoryCheckScript}" -MainLevel={MainLevelName} -Platform={Platform} -unattended -NoSound
```

示例（`ProjectRoot=E:\Trunk`、`EngineRoot=E:\UE7`、使用 UE4）：

```powershell
& "E:\UE7\Engine\Binaries\Win64\UE4Editor-Cmd.exe" "E:\Trunk\EM.uproject" -ExecutePythonScript="E:\Trunk\.skill\美术场景类\场景检查类\check-scene-memory\SceneMemoryCheck.py" -MainLevel=Chapter01_IcelakeCity -Platform=all -unattended -NoSound
```

可选参数：

- `-OutputPath={ProjectRoot}/SceneMemoryCheckResult.json`（不写则默认项目根目录 `SceneMemoryCheckResult.json`）
- `-IncludeEngineRefs=1`（需要把 `/Engine/` 依赖算进贴图/材质内存时再开）

## 第五步：读取结果并汇报

读取生成的结果文件（默认 `{ProjectRoot}\SceneMemoryCheckResult.json`；若使用了 `-OutputPath` 则读对应路径），向用户说明：

1. **GrandTotals**：`UniqueGrandTotals`（主关卡范围真实去重合计）与 `SumOfPerLevel`（各子关卡相加、可能重复计入），都给出三类资源人类可读内存。
2. **Top5 子关卡排名**（基于 `TopSubLevels`）：
   - 按 **总内存**（`ByTotalMemoryBytes`）列出 Top5 子关卡，每条带 `LevelName` 及 `TotalMemoryHuman` + 三类资源人类可读内存；
   - 再分别输出按 **StaticMesh**（`ByStaticMeshMemoryBytes`）、**Texture**（`ByTextureMemoryBytes`）、**Material**（`ByMaterialMemoryBytes`）的 Top5 子关卡；
   - 同时提醒：这些排名用的是子关卡内部去重后的内存字节，跨子关卡复用的资源会重复计入，仅用于定位大头。
3. **Top5 单个资源**（基于 `TopAssets`，**全主关卡真实去重**，与 `UniqueGrandTotals` 同口径）：
   - 分别列出单个 **StaticMesh / Texture / Material** 各自内存占用 Top5，每条带 `AssetName`、`PackageName`（长包名）、`MemoryHuman`；如篇幅允许，再附 `DiskPath` 用于定位文件；
   - 明确这和第 2 步的子关卡排名口径不同：同一资源被多个子关卡引用只计一次。
4. **按子关卡细节**：每个 `Levels[]` 条目的 `StaticMeshMemoryHuman / TextureMemoryHuman / MaterialMemoryHuman / TotalMemoryHuman` 与 `UniqueStaticMeshCount / TexturePackageCount / MaterialPackageCount`。
5. **Top5 面数模型**：每个子关卡的 `Top5MeshesByLOD0TrianglesWeighted`（包名、加权三角形数、该网格自身内存大小）。
6. **Top5 内存加权模型**：每个子关卡的 `Top5MeshesByMemoryWeighted`（包名、内存×实例数加权字节、该网格自身内存）—— 用于定位"运行时常驻内存大头"，与三角形 Top5 视角互补。
7. 若 `LoadFailedPackageCount > 0`，列出前几个失败包名提示用户排查（可能是 redirector / 资产被删 / 路径异常）。
8. 若某子关卡有 `Error` 字段，单独列出原因。

可选：调用同目录的 `ConvertMemoryJsonToTable.ps1 -JsonPath {OutputPath}` 生成 Markdown 表格版本，便于贴到周报或 PR。

## 修改与扩展

- 调整统计规则（如改 `Exclusive` → `EstimatedTotal`、Nanite 分支等）只改 `SceneMemoryCheck.py` 即可。
- **新增 / 修改 C++ wrapper（`UPythonExtensionFunctionLibrary::GetObjectResourceSizeBytes` 等）后必须重新编译 EMEditor**，否则 Python 反射不到新接口。
- 表格输出格式调整改 `ConvertMemoryJsonToTable.ps1`。

## 与 check-scene-full 的关系

- **子关卡范围、命名过滤、`_LOD1` 跳过、WorldComposition / 文件系统回退** 与 `check-scene-full/SceneFullCheck.py` 保持一致。
- 本 Skill **不**执行 LevelBounds、移动性等其它场景规范检查；仅面向内存与面数统计。
