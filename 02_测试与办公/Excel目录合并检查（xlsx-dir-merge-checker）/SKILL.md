---
name: xlsx-dir-merge-checker
description: 对比两个目录下的 Excel 配表，判断目录 B 是否有内容未 merge 到目录 A；严格校验表头完整性，并列出缺失表、表头、数据及对应 SVN 提交。Use when comparing two ExportDatas/datas directories, branch merge checks, 表头 merge, 未 merge 内容, or SVN merge verification.
---

# 目录配表 Merge 检查

根据两个目录文件，判断目录 B 是否有内容没有 merge 到目录 A，不允许缺少表头，有缺少或者没有 merge 的内容列出是哪个表，哪个表头，哪次 SVN 提交没有 merge。

## 角色定义

| 目录 | 含义 |
|------|------|
| **目录 A** | merge 目标目录（已合入侧，如 trunk / 主版本） |
| **目录 B** | merge 来源目录（待合入侧，如分支 / 版本目录） |

检查方向：**以目录 B 为准**，找出 B 中存在但 A 中缺失或不一致的内容。

## 触发场景

- “检查两个目录有没有 merge 完”
- “目录 B 有没有内容没 merge 到目录 A”
- “对比两个 ExportDatas/datas 目录”
- “查缺表头 / 缺列 / 缺行 / 哪次 SVN 没 merge”

## 输入参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `目录A` | merge 目标目录绝对路径 | 必填 |
| `目录B` | merge 来源目录绝对路径 | 必填 |
| `glob` | 扫描文件模式 | `**/*.xlsx` |

常见目录示例：

- 目录 A：`D:\PAN01-SVN\demo\EM\ExportDatas\datas`
- 目录 B：`D:\PAN01-SVN-1.4\EM-1.4\ExportDatas\datas`

## 执行流程

### Step 1: 确认目录

1. 确认目录 A、目录 B 均存在且为 SVN 工作副本（用于追溯提交）。
2. 若用户只给分支名，按项目惯例补全为 `ExportDatas/datas` 根目录。
3. 若 A/B 不是同一相对路径结构，先让用户确认对应关系。

### Step 2: 运行对比脚本

优先使用项目自带 Python：

```powershell
$Py = if (Test-Path "{EM_ROOT}\ExportDatas\tools\py37\py37.exe") {
  "{EM_ROOT}\ExportDatas\tools\py37\py37.exe"
} else { "python" }

& $Py "{SKILL_ROOT}\scripts\compare_dirs.py" "{目录A}" "{目录B}"
```

可选参数：

```powershell
& $Py "{SKILL_ROOT}\scripts\compare_dirs.py" "{目录A}" "{目录B}" --json
& $Py "{SKILL_ROOT}\scripts\compare_dirs.py" "{目录A}" "{目录B}" --no-svn
& $Py "{SKILL_ROOT}\scripts\compare_dirs.py" "{目录A}" "{目录B}" --svn-log-limit 120
```

### Step 3: 输出结果

脚本退出码：

- `0`：未发现未 merge 内容
- `1`：存在未 merge 内容
- `2`：参数或目录错误

## 检查规则（强约束）

### 1. 表头不可缺失

Excel 配表表头结构（前 4 行）：

| 行号 | 内容 |
|------|------|
| 第 1 行 | 描述（中文） |
| 第 2 行 | 类型 |
| 第 3 行 | 字段名 |
| 第 4 行 | server/client |

- 以 **第 3 行字段名** 作为列主键；字段名为空时回退到第 1 行描述。
- **目录 B 有的表头列，目录 A 必须存在**，否则记为 `missing_header`（不允许缺少表头）。
- 四行表头任意一行与 B 不一致，记为 `header_mismatch`。

### 2. 数据行对比

- 数据从第 5 行开始。
- 以首列非空值作为主键（通常是 ID 列）。
- B 有而 A 无的行 → `missing_row`
- 同行同列值不一致 → `cell_mismatch`

### 3. 表与 Sheet

- B 有而 A 无的 xlsx → `missing_table`
- B 有而 A 无的 Sheet → `missing_sheet`
- Sheet 名支持 `【中文|EnglishName】` 格式，按 EnglishName 对齐。

### 4. SVN 提交追溯

对每个差异项，在 **目录 B 侧文件** 上执行 `svn log`，定位引入该表头/行/单元格变更的 revision。

输出必须包含：

- **表**：相对路径，如 `Quest/QuestChain.xlsx`
- **表头**：字段名或 `主键 / 字段名`
- **未 merge 的 SVN 提交**：`r版本号 | 提交者 | 提交说明`

若 SVN 不可用或历史过深未能定位，明确写“未能自动定位”，并给出 `svn log -v <B侧文件>` 建议。

## 输出模板

```markdown
# 目录 Merge 检查结果

- 目录 A（目标）: ...
- 目录 B（来源）: ...

## 未 merge 清单

| 表 | Sheet | 类型 | 表头/主键 | 详情 | 未 merge 的 SVN 提交 |
|----|-------|------|-----------|------|----------------------|
| Quest/QuestChain.xlsx | QuestChain | missing_header | RewardId | 目录 A 缺少表头列 | r12345 \| zhangsan \| 【1.4】新增任务奖励字段 |
| Quest/QuestChain.xlsx | QuestChain | missing_row | 100231 | 目录 A 缺少数据行 | r12346 \| lisi \| 补充 1.4 任务链 |
```

全部通过时：

```markdown
未发现目录 B 中存在、但目录 A 未 merge 的内容。
```

## 补充：mergeinfo 交叉验证（可选）

当 A、B 均为 SVN 工作副本且存在分支关系时，可追加：

```powershell
svn mergeinfo --show-revs eligible <B的SVN URL> <A的工作副本路径>
```

将 eligible revisions 与脚本输出的 revision 交叉核对，提高结论可信度。

## 注意事项

- 忽略 `~$` 开头的 Excel 临时文件。
- 只比较 B 中存在的文件；A 多出来的文件不在本 skill 范围内。
- xlsx 为二进制文件，SVN 追溯默认检查最近 80 次提交；可通过 `--svn-log-limit` 加大范围。
- 若需对比 Lua 导出结果，改用 `svn-diff-datas` skill；本 skill 聚焦 **Excel 源表目录**。
