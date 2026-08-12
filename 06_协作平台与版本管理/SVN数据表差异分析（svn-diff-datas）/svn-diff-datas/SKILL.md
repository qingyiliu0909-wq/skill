---
name: svn-diff-datas
description: 根据 SVN 版本号查询 Content/Script/Datas 目录下文件的变更 diff，并展开 RT 引用进行对比。当用户提供 SVN 版本号并想查看数据表文件变更时使用此 skill。
---

# SVN 版本 Datas Diff 查询（支持 RT 展开）

## 功能说明

根据用户提供的 SVN 版本号，查询该版本中 `Content/Script/Datas` 目录下文件的变更，并在分析时严格遵循以下顺序：

1. **先输出详细的修改前 / 修改后对比**
2. **再输出更细致的变化分析**

如果 Lua 数据文件中存在 `T.RT_N` 这类可复用表（RT, Reusable Table）引用，需要优先展开后再做对比，避免只看到“引用变了”却看不到“实际数据变了什么”。

---

## 输出要求（强约束）

当使用本 skill 分析某个 SVN 版本的 Datas 改动时，输出必须包含以下两大部分，且顺序不能颠倒：

### 第一部分：详细前后对比

必须先给出**足够详细**的前后对比，而不是只写一句“某字段改了”。

至少应包含：

- 变更文件列表
- 每个文件的变更前版本内容片段
- 每个文件的变更后版本内容片段
- 原始 diff
- RT 展开后的 diff
- 若 diff 很长，仍要按“字段 / 数据块 / key 路径”拆分说明，不能只给总结

### 第二部分：详细分析

在前后对比之后，再给出**更细致的分析**。分析不能只停留在“新增 / 删除 / 修改”三个词上，而要继续说明：

- 改动发生在哪些表、字段、索引、key 路径
- 每一处改动的旧值与新值分别是什么
- 是结构变化还是数据值变化
- 是否属于 RT 展开后才看得出的真实变化
- 这些变化更像是数值调整、配置修正、资源替换、逻辑开关切换，还是结构重构
- 可能影响到哪些玩法、UI、读取逻辑、客户端展示或 C++ / Lua 数据访问
- 是否存在高风险项，例如字段删除、类型变化、数组长度变化、默认值变化、枚举语义变化

如果没有足够证据，不要编造业务结论；应明确写“从当前 diff 只能确认……，无法直接确认……”。  
但只要能从配置结构中推断出潜在影响，就应写出来。

---

## 工具说明

### Python 环境

项目自带 Python 环境，优先使用系统 Python，若无则使用项目自带：

```powershell
# 定义 Python 命令（优先系统 Python，备选项目自带）
$PythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "ExportDatas\tools\py37\py37.exe" }

# 使用 svn-diff-datas\tools 目录中的展开脚本
$ExpandRtScript = Resolve-Path ".skill\lua表格svndiff\svn-diff-datas\tools\expand_lua_rt.py"

# 统一使用 skill 目录存放临时文件
$SkillDir = Resolve-Path ".skill\lua表格svndiff\svn-diff-datas"
$TempDir = Join-Path $SkillDir "_tmp"
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
```

### expand_lua_rt.py

位置：`.skill\lua表格svndiff\svn-diff-datas\tools\expand_lua_rt.py`

功能：将 Lua 数据文件中的 `T.RT_N` 引用展开为实际表格内容，便于观察真实数据变化。

使用方式：

```powershell
# 单文件展开
& $PythonCmd $ExpandRtScript "Content\Script\Datas\FileName.lua" -p

# 展开并保存到文件
& $PythonCmd $ExpandRtScript "Content\Script\Datas\FileName.lua" -o "FileName.expanded.lua"
```

---

## 执行步骤

### 1. 获取版本提交信息

用户会提供版本号（如 `r12345` 或 `12345`），先统一处理版本号，然后执行：

```powershell
svn log -r {版本号} -v
```

这会显示该版本的：

- 提交者
- 提交时间
- 提交注释
- 变更文件列表

### 2. 筛选 Datas 目录文件

从变更文件列表中筛选 `Content/Script/Datas` 目录下的文件（通常是 `.lua` 文件）。

如果没有该目录下的文件变更，直接明确告知用户并结束流程。

### 3. 获取每个文件的修改前 / 修改后内容

对每个筛选出的文件，都要拿到：

- 修改前版本（`版本号 - 1`）
- 修改后版本（`版本号`）

```powershell
# 获取修改前版本
svn cat -r {版本号-1} "Content/Script/Datas/文件名.lua" > (Join-Path $TempDir "temp_before.lua")

# 获取修改后版本
svn cat -r {版本号} "Content/Script/Datas/文件名.lua" > (Join-Path $TempDir "temp_after.lua")
```

### 4. 展开 RT 引用

对两个版本都执行 RT 展开：

```powershell
& $PythonCmd $ExpandRtScript (Join-Path $TempDir "temp_before.lua") -o (Join-Path $TempDir "temp_before_expanded.lua")
& $PythonCmd $ExpandRtScript (Join-Path $TempDir "temp_after.lua") -o (Join-Path $TempDir "temp_after_expanded.lua")
```

### 5. 生成两类 diff

必须同时准备：

- **原始 diff**：便于看到源码层面的真实改动
- **RT 展开后的 diff**：便于看到真实数据层面的改动

```powershell
# 原始 diff
git diff --no-index -- (Join-Path $TempDir "temp_before.lua") (Join-Path $TempDir "temp_after.lua")

# RT 展开后的 diff
git diff --no-index -- (Join-Path $TempDir "temp_before_expanded.lua") (Join-Path $TempDir "temp_after_expanded.lua")
```

如果 `git diff --no-index` 不可用，再退化到其他 diff 手段；但输出目标不变，仍要保留“原始”和“展开后”两种视角。

### 6. 输出结果时的固定结构

每个文件都按下面的固定结构输出，**先对比，后分析**：

#### 6.1 文件级基本信息

- 文件路径
- 改动类型（新增 / 删除 / 修改）
- 是否包含 RT 展开差异
- 是否建议关注风险

#### 6.2 详细前后对比（必须先输出）

这一段必须尽量具体，建议包含：

1. **修改前关键片段**
2. **修改后关键片段**
3. **原始 diff 摘要**
4. **RT 展开后 diff 摘要**
5. **逐项变化清单**

逐项变化清单建议写成下面这种形式：

- 路径：`MainTable.SomeField[3].Reward`
- 修改前：`101`
- 修改后：`102`
- 变化类型：值修改

或：

- 路径：`ActiveGuide.GamepadIcon[2]`
- 修改前：`T.RT_1`
- 修改后：`T.RT_2`
- RT 展开前观察：引用目标变化
- RT 展开后观察：`{ "LB", "RS" } -> { "B", "LS" }`

#### 6.3 详细分析（放在对比之后）

分析时至少覆盖以下维度：

1. **改动内容分析**
   - 哪些字段被新增、删除、替换、重排
   - 哪些值发生了实际变化
   - 哪些变化只在 RT 展开后才变得明确

2. **结构影响分析**
   - 表结构是否变化
   - 数组 / 字典的长度、顺序、索引是否变化
   - 字段类型或数据形态是否变化

3. **业务语义分析**
   - 更像是数值平衡调整、开关切换、资源引用替换、文案或表现修正，还是配置结构调整
   - 如果从字段命名可以看出用途，要点明用途

4. **潜在影响面分析**
   - 可能影响哪些 Lua 读取逻辑
   - 可能影响哪些 C++ 包装数据访问
   - 可能影响哪些 UI 展示、战斗参数、奖励展示、输入映射、功能开关等

5. **风险分析**
   - 删除字段 / 删除条目
   - 默认值变化
   - 空表变非空 / 非空变空
   - 类型变化
   - RT 引用改动导致多个位置一并变化

6. **结论总结**
   - 用 2~5 条总结“这个文件最核心的变化”
   - 明确区分“确定事实”和“合理推测”

### 7. 多文件场景下的总总结

如果一个版本改了多个 Datas 文件，单文件分析结束后，还要补一段**版本级总结**：

- 本次总共改了哪些文件
- 哪些文件是高风险
- 哪些文件主要是数值微调
- 哪些文件是结构级变化
- 是否存在多个文件围绕同一功能一起改动的迹象

### 8. 让用户选择输出方式

如有必要，可使用提问工具让用户选择输出方式：

**问题**：`如何输出 diff 结果？`

**选项**：

1. **输出到文件** — 保存完整 diff 和分析结果
2. **输出到当前窗口** — 直接在对话中展示
3. **同时输出原始和展开版本** — 便于并排理解

如果用户没有特别要求，优先：

- 在当前窗口展示**精简但详细**的对比与分析
- 对超长 diff 输出到文件，并在对话中给摘要

### 9. 清理临时文件

分析完成后删除临时文件：

```powershell
Remove-Item -Force `
    (Join-Path $TempDir "temp_before.lua"), `
    (Join-Path $TempDir "temp_after.lua"), `
    (Join-Path $TempDir "temp_before_expanded.lua"), `
    (Join-Path $TempDir "temp_after_expanded.lua") `
    -ErrorAction SilentlyContinue
```

---

## 推荐输出模板

```text
版本信息
- 版本号：r12345
- 提交者：xxx
- 时间：xxxx-xx-xx
- 提交说明：xxxx

变更文件列表
- Content/Script/Datas/A.lua
- Content/Script/Datas/B.lua

========================================
文件：Content/Script/Datas/A.lua
========================================

[一] 详细前后对比
1. 修改前关键片段
2. 修改后关键片段
3. 原始 diff 摘要
4. RT 展开后 diff 摘要
5. 逐项变化清单
   - 路径：...
     修改前：...
     修改后：...
     类型：...

[二] 详细分析
1. 改动内容分析
2. 结构影响分析
3. 业务语义分析
4. 潜在影响面分析
5. 风险分析
6. 结论总结

========================================
版本级总结
========================================
- 核心变化 1：...
- 核心变化 2：...
- 高风险项：...
- 建议关注：...
```

---

## RT 展开示例

**原始代码（含 RT 引用）：**

```lua
T.RT_1 = {
    "LB",
    "RS",
}
T.RT_2 = {
    "B",
    "LS",
}
return ReadOnly("GamepadMap", {
    ActiveGuide = {
        GamepadIcon = {
            [1] = T.RT_1,
            [2] = T.RT_1,
            [3] = T.RT_2,
        }
    }
})
```

**展开后代码：**

```lua
--[[ RT_1 definition (now expanded below):
T.RT_1 = {
    "LB",
    "RS",
}
]]
--[[ RT_2 definition (now expanded below):
T.RT_2 = {
    "B",
    "LS",
}
]]
return ReadOnly("GamepadMap", {
    ActiveGuide = {
        GamepadIcon = {
            [1] = { "LB", "RS" },
            [2] = { "LB", "RS" },
            [3] = { "B", "LS" },
        }
    }
})
```

---

## 批量处理脚本

```powershell
$version = "12345"
$prevVersion = [int]$version - 1
$PythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "ExportDatas\tools\py37\py37.exe" }
$ExpandRtScript = Resolve-Path ".skill\lua表格svndiff\svn-diff-datas\tools\expand_lua_rt.py"
$SkillDir = Resolve-Path ".skill\lua表格svndiff\svn-diff-datas"
$TempDir = Join-Path $SkillDir "_tmp"
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

$changedFiles = svn diff -r $prevVersion:$version --summarize |
    Where-Object { $_ -match "Content/Script/Datas/" }

foreach ($fileLine in $changedFiles) {
    $file = $fileLine.Substring(1).Trim()

    svn cat -r $prevVersion $file > (Join-Path $TempDir "temp_before.lua")
    svn cat -r $version $file > (Join-Path $TempDir "temp_after.lua")

    & $PythonCmd $ExpandRtScript (Join-Path $TempDir "temp_before.lua") -o (Join-Path $TempDir "temp_before_exp.lua")
    & $PythonCmd $ExpandRtScript (Join-Path $TempDir "temp_after.lua") -o (Join-Path $TempDir "temp_after_exp.lua")

    Write-Host "=== $file ==="
    Write-Host "--- 原始 diff ---"
    git diff --no-index -- (Join-Path $TempDir "temp_before.lua") (Join-Path $TempDir "temp_after.lua")
    Write-Host "--- RT 展开后 diff ---"
    git diff --no-index -- (Join-Path $TempDir "temp_before_exp.lua") (Join-Path $TempDir "temp_after_exp.lua")
}

Remove-Item (Join-Path $TempDir "temp_*.lua") -Force -ErrorAction SilentlyContinue
```

---

## 示例用法

用户输入：

```text
查看 r12345 的 datas 变更
```

或：

```text
svn diff 12345 datas
```

---

## 注意事项

- 版本号可以带 `r` 前缀也可以不带，需要统一处理
- RT 展开可能显著增加输出体积，但必须优先保证可读性和可分析性
- 嵌套 RT 引用会被递归展开
- 展开深度限制为 10 层，防止循环引用
- diff 很长时可以分段展示，但不能跳过“修改前 / 修改后对比”这一步
- 分析必须建立在已展示的 diff 和前后内容上，不能只给结论
