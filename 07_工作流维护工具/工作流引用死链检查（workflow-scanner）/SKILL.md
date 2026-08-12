---
name: "workflow_scanner"
description: "工作流扫描原子能力。扫描工作流Wiki文档中的[[引用]]死链,自动修复或生成报告。被工作流验证步骤调用。"
---

# Workflow Scanner

工作流扫描原子能力,提供死链扫描与修复功能。

## 能力定位

- **架构层级**: 能力层(原子能力)
- **调用方**: 工作流标准步骤(如"验证目录结构")
- **核心职责**: 扫描Wiki文档死链,自动修复或生成报告

## 标准接口

### 输入

```yaml
scan_path: 扫描路径(如 .worker/.wiki/)
fix_mode: 修复模式(scan_only|auto_fix)
report_format: 报告格式(json|markdown|both)
```

### 输出

```yaml
scan_result: 扫描结果(OK|DEAD_LINKS_FOUND)
report_path: 报告路径(.worker/running/reports/scan/dead_links_<timestamp>.md)
dead_links_count: 死链数量
fixed_count: 修复数量(仅auto_fix模式)
```

### 执行契约

```text
输入: scan_path, fix_mode, report_format
  ↓
扫描所有 .md 文件
  ↓
解析 [[引用]] 链接
  ↓
检查目标文件是否存在
  ↓
记录死链信息
  ↓
执行修复(可选)
  ↓
生成报告
  ↓
输出: scan_result, report_path, dead_links_count, fixed_count
```

## Obsidian链接解析支持

本技能支持Obsidian智能链接解析机制：

### 链接状态分类（v2新增）

| 状态 | 说明 | 处理建议 |
|------|------|---------|
| OK | 路径正确，文件存在 | 无需处理 |
| PATH_ISSUE | 文件存在但路径不规范 | Obsidian可解析，可选修复 |
| DEAD_LINK | 文件不存在（真死链） | 创建文件或删除引用 |

### Obsidian解析规则

Obsidian具有智能解析能力：
- **文件名匹配优先**：即使路径不规范，只要文件名正确，通常能找到
- **全局搜索机制**：在整个vault中搜索匹配的文件名
- **容忍路径错误**：允许相对路径不准确

## 链接最佳实践规范

### 推荐策略：文件名优先 + 跨类别路径

#### 1. 文件名优先（如果唯一）
```markdown
[[Superpowers统一架构原则]]  ✅ 文件名在vault中唯一
[[Repo扩展专项_工作流设计原则]]  ✅ 自解释，唯一
```

#### 2. 跨类别加路径
```markdown
[[知识/Superpowers统一架构原则]]  ✅ 清晰
[[工作流/Repo扩展专项/WORKFLOW]]  ⚠️ 路径较长，可接受
```

#### 3. 避免深层相对路径
```markdown
[[../../知识/xxx]]  ❌ 易错，难以维护
[[知识/xxx]]        ✅ 更清晰，推荐
```

### 核心原则

```
可读性 > 精确性 > 简洁性

原则1：路径深度 ≤ 3层
原则2：优先使用文件名（如果唯一）
原则3：跨类别必须使用路径
原则4：避免../../多层回退
```

### 命名规范

确保文件名自带完整上下文：
```markdown
✅ Repo扩展专项_工作流设计原则.md（自解释）
✅ 性能与稳定性_代码路径速查.md（自解释）
❌ 原则.md（缺乏上下文）
❌ 速查.md（缺乏上下文）
```

## 死链类型与修复策略

| 类型 | 说明 | 自动修复策略 |
|------|------|-------------|
| FILE_NOT_FOUND | 引用的文件不存在 | 报告，建议创建文件或删除引用 |
| PATH_ISSUE | 文件存在但路径不规范 | 报告，建议修正路径（可选） |
| DEAD_LINK | 明确路径不存在 | 报告，建议创建文件或删除引用 |

**重要**：v2版本只扫描不自动修复，生成报告供人工决策

## 使用方法

本技能是原子能力,由工作流标准步骤调用:

### 工作流中调用示例

```markdown
# 验证目录结构

## 技能依赖
- workflow_reviewer
- workflow_scanner

## 执行步骤
1. 调用 workflow_reviewer 执行架构审查
2. 调用 workflow_scanner 执行死链扫描
3. 审阅报告
4. 决定是否需要修复
```

### 直接调用(调试用途)

```text
扫描Wiki链接:
- 扫描路径: .worker/.wiki/
- 修复模式: scan_only
- 报告格式: both
```

## 扫描报告格式

所有扫描报告输出到 `.worker/running/reports/scan/` 目录:

### JSON 报告格式

```json
{
  "scan_result": "DEAD_LINKS_FOUND",
  "scan_time": "2026-07-16T10:00:00Z",
  "root_directory": ".worker/.wiki",
  "total_files": 100,
  "total_links": 250,
  "dead_links_count": 5,
  "dead_links": [
    {
      "source_file": "标准步骤/01_设计评估.md",
      "line": 29,
      "dead_link": "[[专项补丁库/任务专项设计规范.md]]",
      "target_path": ".worker/.wiki/标准步骤/专项补丁库/任务专项设计规范.md",
      "reason": "FILE_NOT_FOUND"
    }
  ],
  "fix_result": "FIXES_APPLIED",
  "total_fixes": 5,
  "success_count": 5,
  "failed_count": 0
}
```

### Markdown 报告格式

```markdown
## Wiki链接扫描报告

**扫描时间**: 2026-07-16 10:00:00
**扫描范围**: .worker/.wiki/
**扫描结果**: 发现死链

### 扫描摘要

- 总文件数: 100
- 总链接数: 250
- 死链数量: 5
- 修复数量: 5

### 死链详细列表

| 源文件 | 行号 | 死链 | 目标路径 | 原因 |
|--------|------|------|---------|------|
| 标准步骤/01_设计评估.md | 29 | [[专项补丁库/任务专项设计规范.md]] | ... | FILE_NOT_FOUND |

### 修复记录

| 源文件 | 死链 | 修复动作 | 状态 |
|--------|------|---------|------|
| 标准步骤/01_设计评估.md | [[专项补丁库/任务专项设计规范.md]] | REMOVE_LINK | SUCCESS |
```

## 技术实现

### Python 脚本位置

```
v2版本（推荐）：
.worker/.skill/工具类/Agent Repo/workflow_scanner/scripts/repo_task_tool_v2.py

v1版本（已废弃）：
.worker/.skill/工具类/Agent Repo/workflow_scanner/scripts/repo_task_tool.py
```

### 命令行调用

#### v2版本（推荐）
```powershell
# 仅扫描（推荐）
python ".worker/.skill/工具类/Agent Repo/workflow_scanner/scripts/repo_task_tool_v2.py" .worker/.wiki --json report.json --md report.md
```

#### v1版本（不推荐）
```powershell
# 扫描并修复（危险，已废弃）
python ".worker/.skill/工具类/Agent Repo/workflow_scanner/scripts/repo_task_tool.py" .worker/.wiki --fix --json report.json --md report.md
```

### v2版本改进

1. **支持Obsidian智能解析**
   - 文件名匹配优先
   - 区分三种链接状态

2. **更安全的修复策略**
   - 只扫描不自动修复
   - 生成报告供人工决策

3. **更准确的判断**
   - 区分"真死链"和"路径问题"
   - 避免误删有效链接

## 注意事项

1. **安全修复**: 修复前会自动备份原文件到 `.backup` 目录
2. **增量扫描**: 支持扫描指定子目录
3. **报告输出**: 建议同时输出 JSON 和 Markdown 报告
4. **性能优化**: 大型Wiki库扫描可能需要较长时间

## 版本信息

- **当前版本**: 4.0 (repo_task_tool_v2)
- **更新时间**: 2026-07-16
- **更新原因**: 支持Obsidian智能解析，改进判断逻辑，修复误删问题
- **历史版本**:
  - 3.0: 重命名为 workflow_scanner
  - 2.0: repo_task_tool（已废弃）
  - 1.0: 初版

### v4.0主要改进

1. ✅ 支持Obsidian智能链接解析
2. ✅ 区分三种链接状态（OK/PATH_ISSUE/DEAD_LINK）
3. ✅ 更安全的修复策略（只扫描不自动修复）
4. ✅ 更准确的判断（避免误删有效链接）
5. ✅ 添加链接最佳实践规范