# 脚步动画分析 README

## 概述

`foot-animation-analysis` 是一个工作区技能，用于分析动画中的脚步接触情况，导出 `ik_foot_l` 和 `ik_foot_r` 轨道数据，生成脚步接触图与 alpha 文件，并将 alpha 曲线回写到动画资产。

本技能同时支持按后缀批量处理，例如：

- 分析 `Player` 下所有 `Walk_Loop` 动画
- 分析 `Monster` 下符合某个后缀的全部动画
- 分析 `Npc` 下符合某个后缀的全部动画

本技能应基于当前工作区与用户提供的 `Project_Root` 运行，不应依赖记忆、机器本地历史或写死的本地路径。

## 必要输入

本技能可以从以下任一输入开始：

- 一个 Unreal 动画资产路径，例如 `/Game/Asset/Char/Player/.../AnimName.AnimName`
- 一个动画短名，例如 `Heitao_Walk_Loop`
- 一个后缀查询，例如 `suffix=Walk_Loop family=Player`

## Project_Root 要求

Python 步骤从以下文件读取 `Project_Root`：

- `Source/EM/.github/skills/foot-animation-analysis/Config.md`

预期格式：

```text
{Project_Root}: Q:\Path\To\ProjectRoot
```

其中 `Project_Root` 指包含 `EM.uproject` 的目录。

如果 `Config.md` 不存在，或者其中保存的路径无效，本技能在继续前必须先向用户询问 `Project_Root`。

标准提问：

```text
脚步分析需要先确认 Project_Root。
请提供项目根目录的绝对路径，也就是 `EM.uproject` 所在目录。
示例: Q:\Pan01\demo\EM
```

## 典型工作流

### 1. 单资产分析

输入示例：

- `/Game/Asset/Char/Player/Char001_Heitao_J/Animation/Sequence/Locomotion/Heitao_Walk_Loop.Heitao_Walk_Loop`
- `Heitao_Walk_Loop`

流程：

1. 解析资产路径。
2. 导出 `ik_foot_l` 与 `ik_foot_r` json。
3. 运行 `plot_foot_contact_intervals.py`。
4. 生成 `*_foot_contact_intervals.svg` 与 `*_foot_alpha_temp.txt`。
5. 将 `Foot_Analy_L` 与 `Foot_Analy_R` 回写到动画资产。

### 2. 后缀批量分析

输入示例：

- `suffix=Walk_Loop family=Player`
- `分析 Monster 下所有 Walk_Loop 的脚步`
- `分析角色脚步 Walk_loop`

流程：

1. 将 `Walk_loop` 这类后缀变体规范化为 `Walk_Loop`。
2. 判断族群范围：`Player`、`Monster`、`Npc` 或全部。
3. 在对应 `Animation/Sequence` 根目录下搜索匹配资产。
4. 如果范围包含 `Player`，默认排除 `Player/Common` 子树。
5. 将匹配结果转换成 Unreal 资产路径。
6. 通过 Python 先完成完整匹配集的收集、去重与稳定排序。
7. 将结果用 `;` 拼接成批处理输入，或写入批处理暂存文件。
8. 只执行一次批量脚步分析命令。

## 族群根目录

- Player: `Q:\Pan01\demo\EM\Content\Asset\Char\Player\*\Animation\Sequence\*.uasset`
- Monster: `Q:\Pan01\demo\EM\Content\Asset\Char\Monster\*\Animation\Sequence\*.uasset`
- Npc: `Q:\Pan01\demo\EM\Content\Asset\Char\Npc\*\Animation\Sequence\*.uasset`

## 外部入口

对外批处理入口为：

- `Misc/AnimFootAnalyzer.bat`

支持以下调用形式：

```bat
AnimFootAnalyzer.bat "/Game/Asset/Char/Player/.../AnimName.AnimName"
AnimFootAnalyzer.bat "/Game/Asset/.../AnimA.AnimA;/Game/Asset/.../AnimB.AnimB"
AnimFootAnalyzer.bat "/Game/Asset/.../AnimA.AnimA" "/Game/Asset/.../AnimB.AnimB"
```

当前 batch 文件会先把收到的所有资产路径写入 `Saved/TempFootCollection.txt`，再以 `-CollectionFile="..."` 调用 `UAnimFootAnanlyzeCommandlet`。

`TempFootCollection.txt` 是临时文件。commandlet 在结束时删除它，batch 文件在 `UE4Editor-Cmd.exe` 返回后也会做一次尽力清理。

## 生成产物

每个分析后的资产会在 `Saved/` 下生成：

- `OutputPrefix_ik_foot_l.Json`
- `OutputPrefix_ik_foot_r.Json`
- `OutputPrefix_foot_contact_intervals.svg`
- `OutputPrefix_foot_alpha_temp.txt`

同时回写以下曲线到动画资产：

- `Foot_Analy_L`
- `Foot_Analy_R`

其中 `OutputPrefix` 表示 `角色目录前缀_动画短名`，例如：

- `Char001_Heitao_J_Heitao_Run_Loop`
- `Common_NodePlayer_Heitao_Run_Loop`
- `NPC001_Nvzhu_Nvzhu_Run_Loop`

## 共享命名规则

后缀解析与族群识别遵循以下规则：

- [Character Animation Naming Rules](../animation-asset-suffix-finder/references/char-animation-naming-rules.md)

脚步分析技能已经内建所需的后缀解析逻辑，因此在脚步分析流程中，不需要再额外跳转到其他命名技能。

## 常见问题

### 缺少 Config.md

现象：

- Python 步骤因缺少 `Config.md` 而失败。

处理方式：

- 向用户确认 `Project_Root`
- 创建 `Config.md`
- 重新执行流程

### Project_Root 无效

现象：

- `Config.md` 存在，但路径不存在，或对应目录下没有 `EM.uproject`

处理方式：

- 向用户确认正确路径
- 更新 `Config.md`
- 重新执行流程

### 匹配到错误资产

现象：

- 一个短名匹配到了多个资产

处理方式：

- 停止执行，并要求用户做消歧

## 推荐输出格式

单资产：

```text
已完成脚步分析。
资产: /Game/Asset/.../AnimName.AnimName
导出: OutputPrefix_ik_foot_l.Json, OutputPrefix_ik_foot_r.Json
分析结果: OutputPrefix_foot_contact_intervals.svg, OutputPrefix_foot_alpha_temp.txt
回写曲线: Foot_Analy_L, Foot_Analy_R
执行方式: 单次 AnimFootAnanlyze commandlet
```

按后缀批量：

```text
已完成批量脚步分析。
后缀: Walk_Loop
范围: Player
匹配数量: 5
执行文件: Saved/TempFootCollection.txt
资产: /Game/Asset/.../AnimA.AnimA
导出: OutputPrefix_ik_foot_l.Json, OutputPrefix_ik_foot_r.Json
分析结果: OutputPrefix_foot_contact_intervals.svg, OutputPrefix_foot_alpha_temp.txt
回写曲线: Foot_Analy_L, Foot_Analy_R
资产: /Game/Asset/.../AnimB.AnimB
导出: OutputPrefix_ik_foot_l.Json, OutputPrefix_ik_foot_r.Json
分析结果: OutputPrefix_foot_contact_intervals.svg, OutputPrefix_foot_alpha_temp.txt
回写曲线: Foot_Analy_L, Foot_Analy_R
执行方式: 单次 AnimFootAnanlyze commandlet 批量输入
```

对于批量模式，只按逐资产结果汇报。除非用户明确要求，否则不要再补充共性、例外、模式归类或统计归纳这类分组总结。