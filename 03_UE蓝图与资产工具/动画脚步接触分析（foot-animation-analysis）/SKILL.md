---
name: foot-animation-analysis
description: '当用户要求分析动画资产的脚步接地情况、导出 ik_foot_l 和 ik_foot_r 轨道到 json、生成脚步接触图与 alpha 文件、把 alpha 曲线回写到动画，或按后缀批量分析 Player、Monster、Npc 动画时使用。关键词：脚步分析、落地离地、动画脚步、ik_foot_l、ik_foot_r、Alpha曲线、动画曲线、AnimFootAnanlyze、foot contact、foot alpha、Walk_Loop、批量脚步分析、Player、Monster、Npc。'
user-invocable: true
argument-hint: '可提供一个或多个动画资产路径、一个动画短名，或类似 suffix=Walk_Loop family=Player 的后缀批量请求'
---

# 脚步动画分析

当用户希望分析一个动画资产中脚部何时落地、何时离地，生成逐帧 alpha 数据，或将 alpha 曲线回写到动画资产时，使用本技能。

本技能也覆盖按后缀批量分析的场景，例如分析 `Player`、`Monster` 或 `Npc` 下所有后缀为 `Walk_Loop` 的动画。

本技能必须保持自包含。不要依赖仓库记忆、机器本地历史，或写死的本地工程路径。

## 本技能覆盖内容

- `Source/EMEditor/Private/Commandlet/AnimFootAnanlyzeCommandlet.cpp` 中的 `UAnimFootAnanlyzeCommandlet`
- `UEditorCommonFunctionLibrary::ExportBoneAnimation`
- `UEditorCommonFunctionLibrary::AddFloatCurveToAnimation`
- `Source/EM/.github/skills/foot-animation-analysis/plot_foot_contact_intervals.py`
- `Misc/AnimFootAnalyzer.bat`
- 使用说明文档 [README](./README.md)
- 内建指令：`资产名称与后缀解析`
- `/Game/Asset/...` 下动画资产路径规范化
- 共享命名规则文档 [Character Animation Naming Rules](../animation-asset-suffix-finder/references/char-animation-naming-rules.md)

## 何时使用

当用户提出下列任一类请求时使用本技能：

- “分析这个动画的左右脚什么时候落地、什么时候离地”
- “把动画里的 `ik_foot_l` 和 `ik_foot_r` 导成 json”
- “根据脚步数据生成每帧 alpha”
- “把脚步 alpha 写回动画曲线”
- “做一个一键批处理，跑完 commandlet 就完成脚步分析和曲线写入”
- “分析 Player 下所有 Walk_Loop 的脚步”
- “把 Monster 里符合某个后缀的动画全跑一遍脚步分析”
- “按后缀收集 NPC 动画并批量做脚步分析”

## 标准流程

1. 解析动画资产路径。
2. 导出 `ik_foot_l` 与 `ik_foot_r` 轨道数据到 json。
3. 用 Python 脚本分析 json，生成脚步接触图和逐帧 alpha txt。
4. 解析生成的 alpha txt，并把浮点曲线写回动画资产。
5. 尽量通过一次 commandlet 运行完成整个链路。

## 内建指令：资产名称与后缀解析

对于脚步分析请求，应把后缀解析与资产收集视为本技能内部的一部分，而不是要求额外跳转到其他技能。

当用户提供以下任一输入时，应使用该内建指令：

- 一个动画短名
- 一个后缀，例如 `Walk_Loop`
- 一个族群范围，例如 `Player`、`Monster` 或 `Npc`
- 一个“先批量收集所有匹配资产，再做脚步分析”的请求

处理步骤：

1. 读取共享命名规则 [Character Animation Naming Rules](../animation-asset-suffix-finder/references/char-animation-naming-rules.md)。
2. 将 `Walk_loop` 这类后缀变体规范化为 `Walk_Loop`。
3. 判断族群范围：`Player`、`Monster`、`Npc` 或全部。
4. 在对应族群根目录下解析匹配的 `.uasset` 文件。
5. 如果族群范围是 `Player`，则排除 `Q:\Pan01\demo\EM\Content\Asset\Char\Player\Common\` 下的匹配项。
6. 把文件系统路径转换成 `/Game/Asset/.../AnimName.AnimName` 形式的 Unreal 资产路径。
7. 在执行 `Misc/AnimFootAnalyzer.bat` 之前，先通过 Python 完成完整匹配集的收集、去重和稳定排序，并以该结果准备批处理输入。
8. 如果需要命令行输入，只有在完整收集完成后，才允许用 `;` 拼接资产路径。

族群根目录：

- Player: `Q:\Pan01\demo\EM\Content\Asset\Char\Player\*\Animation\Sequence\*.uasset`
- Monster: `Q:\Pan01\demo\EM\Content\Asset\Char\Monster\*\Animation\Sequence\*.uasset`
- Npc: `Q:\Pan01\demo\EM\Content\Asset\Char\Npc\*\Animation\Sequence\*.uasset`

在脚步分析场景中，该内建指令会替代单独调用 `animation-asset-suffix-finder` 的需求。

## 后缀批量流程

当用户给的是 `Walk_Loop` 这类后缀，而不是显式资产路径时：

1. 使用内建的 `资产名称与后缀解析` 指令，并结合 [Character Animation Naming Rules](../animation-asset-suffix-finder/references/char-animation-naming-rules.md)。
2. 将用户输入的后缀变体（如 `Walk_loop`）先规范成标准形式 `Walk_Loop`。
3. 判断请求范围是 `Player`、`Monster`、`Npc`，还是它们的组合。
4. 在对应族群根目录下搜索后缀匹配的资产。
5. 如果请求范围包含 `Player`，则从收集结果中排除 `Player/Common` 子树。
6. 将所有匹配项转换为 Unreal 资产路径。
7. 在任何批处理执行前，先通过 Python 完整收集、去重、稳定排序，并写出或暂存该批处理输入结果。
8. 对完整收集结果只调用一次 `Misc/AnimFootAnalyzer.bat`，或只调用一次 `UAnimFootAnanlyzeCommandlet`。
9. 当用户只提供后缀或其他批量查询时，绝不允许按资产串行调用 `Misc/AnimFootAnalyzer.bat`。
10. 所有匹配资产必须在同一轮批处理里完成分析。

如果用户只说“分析角色脚步 Walk_Loop”而没有指定族群，则需要追问是 `Player`、`Monster`、`Npc` 还是全部。

## 路径规则

- 标准动画资产路径格式为 `/Game/Asset/.../AnimName.AnimName`。
- 如果用户只给出动画短名，先在 `/Game/Asset/` 下进行规范化或搜索匹配路径。
- 不要假设一个短名一定唯一。如果存在多个匹配项，应报告候选项，或要求用户明确指定。
- 对于后缀类请求，资产收集必须在执行 `Misc/AnimFootAnalyzer.bat` 之前完成；该收集步骤应通过 Python 完成。
- 如果请求族群是 `Player`，则在后缀收集时默认排除 `Player/Common`，除非用户明确要求包含该子树。
- 批处理输入可以支持多个资产路径，并用 `;` 分隔，但前提是完整资产列表已经收集完成。
- 对于后缀批量模式，应先由 Python 或 subagent 完成资产收集、去重、稳定排序，并把结果写入 `Saved/TempFootCollection.txt`；随后 `Misc/AnimFootAnalyzer.bat` 只消费该 `.txt` 文件并转发给 `UAnimFootAnanlyzeCommandlet`。
- 对于显式资产路径模式，`Misc/AnimFootAnalyzer.bat` 仍可在本地兜底写入 `Saved/TempFootCollection.txt`，以兼容原有单资产或多资产调用方式。
- `TempFootCollection.txt` 是临时执行文件；无论它由 subagent、Python 还是 batch 准备，batch 在 `UE4Editor-Cmd.exe` 返回后都会再次尽力删除当前 `COLLECTION_FILE`，commandlet 也会在结束时执行同样的清理。
- 对于后缀批量模式，收集结果必须在执行批处理前先规范化为 `/Game/Asset/.../AnimName.AnimName`，并且绝不允许回退到逐资产串行调用 batch 的方式。
- 如果技能目录下缺少 `Config.md`，需要先向用户确认 `Project_Root`，再创建 `Config.md`，然后继续执行流程。
- 不要假设 `Project_Root` 一定是 `Q:\Pan01\demo\EM` 或其他机器本地固定路径。

后缀收集族群根目录：

- Player: `Q:\Pan01\demo\EM\Content\Asset\Char\Player\*\Animation\Sequence\*.uasset`
- Monster: `Q:\Pan01\demo\EM\Content\Asset\Char\Monster\*\Animation\Sequence\*.uasset`
- Npc: `Q:\Pan01\demo\EM\Content\Asset\Char\Npc\*\Animation\Sequence\*.uasset`

Player 后缀收集排除规则：

- 默认忽略 `Q:\Pan01\demo\EM\Content\Asset\Char\Player\Common\**`
- 只有当用户明确要求包含 `Player/Common` 时，才允许把该子树纳入结果

## 技能配置

- 技能配置文件：`Source/EM/.github/skills/foot-animation-analysis/Config.md`
- 必填字段：`{Project_Root}: Q:\Path\To\ProjectRoot`
- Python 分析脚本从这个配置文件里读取工程根目录。
- 如果配置文件不存在，应先询问用户 `Project_Root`，再创建该配置，然后继续 Python 分析步骤。
- 如果配置文件存在但路径无效，应停止猜测，改为向用户确认正确路径。

## Project_Root 标准提问模板

当 `Config.md` 缺失或无效时，在开始分析前应先向用户确认 `Project_Root`。

使用下面这段标准提问：

```text
脚步分析需要先确认 Project_Root。
请提供项目根目录的绝对路径，也就是 `EM.uproject` 所在目录。
示例: Q:\Pan01\demo\EM
```

如果现有配置路径无效，则改用：

```text
当前 `Config.md` 中的 `Project_Root` 无法使用。
请提供正确的项目根目录绝对路径，也就是 `EM.uproject` 所在目录。
示例: Q:\Pan01\demo\EM
```

用户回复后：

1. 验证目录存在。
2. 验证该目录下存在 `EM.uproject`。
3. 创建或更新 `Config.md` 为 `{Project_Root}: <UserPath>`。
4. 继续执行脚步分析流程。

## Json 导出步骤

使用 `UEditorCommonFunctionLibrary::ExportBoneAnimation` 导出以下两个脚骨轨道：

- `ik_foot_r`
- `ik_foot_l`

当前导出目标目录是工程的 `Saved` 目录。json 文件只作为本次分析的中间产物生成，并会在 commandlet 完成该资产处理后删除；如果需要定位本次中间文件，可按以下命名规则推断：

- `OutputPrefix_ik_foot_l.Json`
- `OutputPrefix_ik_foot_r.Json`

其中 `OutputPrefix` 表示 `角色目录前缀_动画短名`，例如：

- `Char001_Heitao_J_Heitao_Run_Loop`
- `Common_NodePlayer_Heitao_Run_Loop`
- `NPC001_Nvzhu_Nvzhu_Run_Loop`

`UAnimFootAnanlyzeCommandlet` 应作为首选编排入口。它已经支持解析 `Assets=` 并加载 `UAnimSequence`，因此应把整条流程优先串在该 commandlet 中完成。

## Python 分析步骤

使用 `Source/EM/.github/skills/foot-animation-analysis/plot_foot_contact_intervals.py` 分析导出的 json 文件。

脚本会先基于动画短名生成中间文件，之后由 commandlet 将保留结果重命名为唯一的 `OutputPrefix` 形式：

- `OutputPrefix_foot_contact_intervals.svg`
- `OutputPrefix_foot_alpha_temp.txt`

alpha 规则如下：

- 完全离地：`Alpha = 0`
- 完全着地：`Alpha = 1`
- 过渡区间：根据分析出的接触窗口和稳定着地区间，在 `0` 到 `1` 之间插值

当前脚本从 `Saved` 目录读取 json，并输出逐帧 txt。除非用户明确要求其他位置，否则输出默认保留在工程 `Saved` 目录。
默认情况下，脚本通过 `Config.md` 中的 `{Project_Root}` 来解析 `Saved` 目录。

脚本只使用 Python 标准库：

- `argparse`
- `json`
- `pathlib`
- `xml.sax.saxutils`

因此这一流程不需要安装任何第三方 Python 包。

## 曲线回写步骤

在同一次 commandlet 执行中读取生成的 `AssetName_foot_alpha_temp.txt`，把数据回写到同一个 `UAnimSequence`，然后再把保留结果文件重命名为 `OutputPrefix_foot_alpha_temp.txt`。

推荐曲线名：

- `Foot_Analy_L`
- `Foot_Analy_R`

`AddFloatCurveToAnimation` 已经处理了以下关键行为：

- 校验动画资产和输入数组
- 检查帧数，并在必要时按较小值截断
- 如存在同名曲线，先删除再重建
- 使用 `GetTimeAtFrame` 写入关键帧，并最终提交到序列

## 一次性 Commandlet 要求

优选的最终行为应为：

- 只调用一次 `UAnimFootAnanlyzeCommandlet`
- 只保留一个 `Misc/AnimFootAnalyzer.bat` 批处理入口
- 当用户提供的是后缀或其他批量查询时，必须先用 Python 收集完整资产集合，再执行 batch
- 整条流程在一次运行中完成：资产解析 -> json 导出 -> python 分析 -> alpha txt 解析 -> 曲线回写
- 在调用 batch 之前，必须先完成所有资产路径收集；然后由 Python 或 subagent 把该预收集结果写入 `Saved/TempFootCollection.txt`
- commandlet 通过 `CollectionFile=...` 读取输入，并在结束后删除 `TempFootCollection.txt`；batch 在返回后也会再次尽力删除同一路径
- 分析完成后，明确报告每只脚完全离地的帧，以及开始落地的帧
- 对于后缀批量模式，流程应为：后缀解析 -> 资产收集 -> 分号拼接 -> 单次批量分析
- 对于后缀批量模式，绝不允许循环遍历资产并逐个调用 batch 文件

batch 文件应支持两种入口：接受一个或多个资产路径时，在本地兼容模式下写入 `Saved/TempFootCollection.txt`；接受单个 `.txt` collection file 路径时，直接消费该文件并调用带 `-CollectionFile="..."` 的 commandlet：

```bat
AnimFootAnalyzer.bat "/Game/Asset/Char/Player/.../AnimName.AnimName"
AnimFootAnalyzer.bat "/Game/Asset/.../AnimA.AnimA;/Game/Asset/.../AnimB.AnimB"
AnimFootAnalyzer.bat "/Game/Asset/.../AnimA.AnimA" "/Game/Asset/.../AnimB.AnimB"
AnimFootAnalyzer.bat "Q:\Path\To\TempFootCollection.txt"
```

后缀批量示例：

```bat
AnimFootAnalyzer.bat "/Game/Asset/Char/Player/Char001_Heitao_J/Animation/Sequence/Heitao_Walk_Loop.Heitao_Walk_Loop;/Game/Asset/Char/Player/Char005_Shuimu/Animation/Sequence/Shuimu_Walk_Loop.Shuimu_Walk_Loop"
```

commandlet 应是唯一对外入口。如果流程中仍有只能手动独立执行的 Python 步骤，应优先把它收编进 commandlet 的流程编排，而不是要求用户执行多条手工命令。

## 实现指导

- 优先把编排逻辑实现到 `UAnimFootAnanlyzeCommandlet` 中，而不是依赖零散的编辑器按钮操作。
- 保持 `ExportBoneAnimation` 只负责骨骼轨道 json 导出；json 作为中间文件在当前资产处理结束后删除。
- 保持 `AddFloatCurveToAnimation` 只负责给单个动画序列写入一条命名 float 曲线。
- 跨步骤的胶水逻辑应放在 commandlet 或单独 helper 中，不要把底层工具 API 膨胀得过重。
- 所有保留输出文件都必须使用 `角色目录前缀_动画短名` 命名，不能只用裸动画短名，也不能用硬编码示例名。
- 如果要泛化 Python 脚本，应让资产名和保存目录支持命令行参数配置。
- 对于后缀批量模式，应复用内建的 `资产名称与后缀解析` 指令和共享命名规则，而不是重新硬编码各族群解析逻辑。
- 批量收集必须同时支持 `Player`、`Monster`、`Npc` 三类根目录。
- 对于仅给后缀或其他批量查询的输入，应先通过 Python 收集资产列表，再调用 `Misc/AnimFootAnalyzer.bat`。
- 当收集 `Player` 后缀资产时，Python 收集器必须默认跳过 `Player/Common` 子树。
- 收集结果必须稳定、去重，并由 Python 或 subagent 在调用 batch 或 commandlet 前写入 `Saved/TempFootCollection.txt`。
- 绝不允许通过“每个资产调用一次 `Misc/AnimFootAnalyzer.bat`”来实现后缀批量分析。
- 当前 batch 入口已经用 `Heitao_Walk_Loop` 和 `Zhangyu_Walk_Loop` 做过验证，两者都能在一次运行中完成 write-back。

## 输出要求

向用户汇报结果时，应包含：

- 解析后的动画资产路径
- 生成的 svg 和 alpha txt 文件名
- 如用户关心中间产物，可补充说明本次生成的 json 已在流程结束后删除
- 回写到动画资产中的曲线名
- 每只脚完全离地的帧
- 每只脚开始落地的帧
- 本次操作是单次 commandlet 一次性完成，还是仍需后续步骤
- 对于后缀批量模式，还应包含匹配数量和 `TempFootCollection.txt` 执行文件路径

对于批量模式，只按“逐资产结果”汇报。除非用户明确要求，否则不要额外输出共性、例外、模式归类、统计归纳这类分组总结。

推荐答复形态：

```text
已完成脚步分析。
资产: /Game/Asset/.../AnimName.AnimName
导出: OutputPrefix_ik_foot_l.Json, OutputPrefix_ik_foot_r.Json
分析结果: OutputPrefix_foot_contact_intervals.svg, OutputPrefix_foot_alpha_temp.txt
完全离地: Left [...], Right [...]
开始落地: Left [...], Right [...]
回写曲线: Foot_Analy_L, Foot_Analy_R
执行方式: 单次 AnimFootAnanlyze commandlet
```

后缀批量答复形态：

```text
已完成批量脚步分析。
后缀: Walk_Loop
范围: Player
匹配数量: 5
执行文件: Saved/TempFootCollection.txt
资产: /Game/Asset/.../AnimA.AnimA
导出: OutputPrefix_ik_foot_l.Json, OutputPrefix_ik_foot_r.Json
分析结果: OutputPrefix_foot_contact_intervals.svg, OutputPrefix_foot_alpha_temp.txt
完全离地: Left [...], Right [...]
开始落地: Left [...], Right [...]
回写曲线: Foot_Analy_L, Foot_Analy_R
资产: /Game/Asset/.../AnimB.AnimB
导出: OutputPrefix_ik_foot_l.Json, OutputPrefix_ik_foot_r.Json
分析结果: OutputPrefix_foot_contact_intervals.svg, OutputPrefix_foot_alpha_temp.txt
完全离地: Left [...], Right [...]
开始落地: Left [...], Right [...]
回写曲线: Foot_Analy_L, Foot_Analy_R
执行方式: 单次 AnimFootAnanlyze commandlet 批量输入
```

## 备注

- 本技能面向 `/Game/Asset/...` 下的动画资产。
- 如果用户提供的是显示名或文件系统路径，应先规范化，再执行流程。
- 如果一个短名匹配到多个资产，应停止并让用户消歧，避免错误回写到错误动画。
- 如果用户明确要求一次性 commandlet 行为，就不要把流程留成半手工状态。
- 如果请求是后缀类型，应先在指定族群根目录完成资产收集，再把所有匹配项一次性批量分析。
- 如果请求是后缀类型，应先收集，再对完整匹配集合只调用一次 batch。
- 如果请求是在 `Player` 范围内按后缀分析，除非用户明确要求，否则不要包含 `Player/Common`。
- 相同的后缀收集规则同样适用于 `Player`、`Monster`、`Npc`；差异只在命名规则。
- 如果最终目标是脚步分析，就应停留在本技能中，使用内建后缀解析逻辑，而不是跳去其他命名技能。
- 本技能必须能在其他用户机器上工作，且只能依赖当前工作区文件和用户显式提供的 `Project_Root`。
