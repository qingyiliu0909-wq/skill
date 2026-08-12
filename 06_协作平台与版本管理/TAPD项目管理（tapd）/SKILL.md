---
name: "tapd"
description: "TAPD敏捷项目管理技能，提供需求单创建、查询、去重等能力。支持工作流调用和命令行操作。"
---

# TAPD 需求单管理技能

## 技能概述

提供 TAPD 需求单的创建、查询、去重等功能。支持：
- **命令行操作**：通过 `tapd_cli.py` 脚本管理需求单
- **工作流集成**：通过 AINode 调用，实现自动化开单流程
- **去重机制**：创建前自动检查是否已存在，避免重复单子

## 快速开始

### 1. 查询需求单列表

```bash
python scripts/tapd_cli.py list --limit 100
```

### 2. 创建需求单

```bash
python scripts/tapd_cli.py create "性能优化需求" -d "描述内容" -o "负责人"
```

## 命令行接口

| 命令 | 说明 | 示例 |
|------|------|------|
| `list` | 查询列表 | `python scripts/tapd_cli.py list --limit 50` |
| `create <title>` | 创建需求单 | `python scripts/tapd_cli.py create "标题" -d "描述"` |
| `search <keyword>` | 搜索需求 | `python scripts/tapd_cli.py search "关键字"` |

### list 命令参数

| 参数 | 说明 |
|------|------|
| `-l, --limit` | 单次获取数量，默认 100 |
| `-s, --offset` | 偏移量，默认 0 |
| `-n, --name` | 按名字查询（模糊匹配） |
| `-p, --parent_id` | 按父节点ID查询 |

### list 命令使用场景

**查询总单及其子单的正确流程：**

TAPD 需求单有层级结构（总单 → 子单），如果直接查询所有数据会返回大量冗余信息。正确流程是分两步：

```bash
# 第1步：按名字查询总单
python scripts/tapd_cli.py list --name "性能优化总单"

# 返回结果示例：
# {
#   "id": "1131626021001294327",
#   "name": "【性能优化】1.4性能优化总单",
#   "children_count": 88
# }

# 第2步：用总单ID查询所有子单
python scripts/tapd_cli.py list --parent_id 1131626021001294327

# 这会返回该总单下的所有子单详情
```

**其他常用查询：**

```bash
# 按名字模糊查询
python scripts/tapd_cli.py list --name "动画"

# 查询某个迭代下的所有需求
python scripts/tapd_cli.py list --limit 200
```

### create 命令参数

| 参数 | 说明 |
|------|------|
| `-d, --description` | 需求描述 |
| `-o, --owner` | 负责人 |
| `-i, --iteration` | 迭代ID |
| `--developer` | 开发人员 |
| `--tester` | 测试人员 |
| `--reviewer` | 评审人员 |
| `--acceptor` | 验收人 |

## 智能去重

**去重由 AI 判断，不相信简单字符串匹配。**

AI 会获取需求单列表，根据以下维度综合判断是否重复：

| 判断维度 | 说明 |
|---------|------|
| 标题相似度 | 语义相似的标题可能重复 |
| 描述重叠 | 描述中提到的模块、问题是否已有 |
| 创建时间 | 短期内同类型问题可能已开单 |
| 负责人 | 相同负责人处理类似问题可能是重复 |

### AI 去重流程

```
1. 调用 list --name 命令按问题关键词查询相关总单
2. 如找到总单，用 --parent_id 查询其所有子单；如无总单，查所有单子
3. 将需求单列表和问题描述一并交给 AI
4. AI 综合分析判断是否重复
5. 如重复，返回已有链接；如不重复，创建新单
```

**注意**：TAPD 需求单有层级结构，应优先查询总单及其子单，避免遗漏重复项。

这确保了：
- AI 智能判断，避免误判
- 语义相似但表述不同的重复能被检测
- 创建者可以干预判断结果

## 工作流集成

在 UTrace 工作流中，TAPD 节点用于根据分析结果自动创建需求单：

```json
{
  "id": "tapd_task",
  "class_id": "AINode.composite_execute",
  "params": {
    "text_prompt": {
      "mode": "static",
      "value": "## TAPD 开单判断\n\n根据分析内容判断是否需要创建 TAPD 单子。\n\n### 判断条件\n- 如果分析结果包含明确的问题描述和影响范围 → 需要开单\n- 如果只是例行分析无明确问题 → 不需要开单\n\n### 执行流程\n1. 调用 TAPD CLI 的 list --name 命令按问题关键词查询相关总单\n2. 如找到总单，用 --parent_id 查询其所有子单；如无总单，查所有单子\n3. 将需求单列表和问题描述一并交给 AI 分析\n4. AI 根据标题相似度、描述重叠、创建时间等维度判断是否重复\n5. 如重复，返回已有链接；如不重复，调用 create 命令创建新单\n6. 返回创建结果（URL 或已存在信息）"
    },
    "ai_output": {
      "mode": "exposed"
    }
  }
}
```

## 目录结构

```
Tapd/
├── SKILL.md              # 本文档
└── scripts/
    └── tapd_cli.py       # 自包含的命令行工具（不依赖 tapd/ 目录）
```

**注意**：`tapd/` 目录将被移除，所有代码已重构到 `scripts/tapd_cli.py` 中。

## 配置说明

默认配置在 `tapd/api.py` 的 `TapdEndpoint` 类中：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `WORKSPACE_ID` | 工作空间 ID | `31626021` |
| `USER_NAME` | 用户名 | `gNxpkwrr` |
| `DEFAULT_WORKITEM_TYPE` | 工作项类型 ID | `1131626021001000158` |

可通过环境变量或配置文件覆盖。

## 返回值格式

### dedup 命令

```json
{
  "exists": true,
  "story_url": "https://www.tapd.cn/tapd_fe/31626021/story/detail/xxx",
  "story_id": "xxx",
  "message": "已存在: https://..."
}
```

### create 命令

```json
{
  "success": true,
  "story_url": "https://www.tapd.cn/tapd_fe/31626021/story/detail/xxx",
  "story_id": "xxx",
  "message": "创建成功: https://..."
}
```

### list 命令

```json
{
  "success": true,
  "count": 100,
  "stories": [...]
}
```
