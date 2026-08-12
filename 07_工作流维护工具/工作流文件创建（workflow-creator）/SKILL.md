---
name: "workflow_creator"
description: "工作流资产创建原子能力。执行文件创建、目录管理和导航注册的纯物理操作。不理解业务语义,只接收具体的文件操作指令。被工作流迭代步骤调用。"
---

# Workflow Creator

工作流资产创建原子能力,提供纯物理文件操作功能。

## 能力定位

- **架构层级**: 能力层(原子能力)
- **调用方**: 工作流标准步骤(如"工作流迭代-步骤6执行优化")
- **核心职责**: 执行物理文件操作(创建目录、创建文件、更新导航),不关心业务语义

## 标准接口

### 输入

```yaml
operation_type: 操作类型(create_directory|create_file|update_file|register_navigation)
target_path: 目标路径
content: 文件内容(create_file/update_file时必需)
navigation_info: 导航信息(register_navigation时必需)
```

### 输出

```yaml
operation_result: 执行结果(success|failed)
created_files: 创建的文件路径列表
error_message: 错误信息(失败时)
```

### 执行契约

```text
输入: operation_type, target_path, content(可选), navigation_info(可选)
  ↓
验证操作类型
  ↓
执行物理操作(mkdir/write/update)
  ↓
返回执行结果
  ↓
输出: operation_result, created_files, error_message
```

## 支持的操作类型

| 操作类型 | 说明 | 必需参数 |
|---------|------|---------|
| create_directory | 创建目录 | target_path |
| create_file | 创建文件 | target_path, content |
| update_file | 更新文件 | target_path, content |
| register_navigation | 注册导航 | target_path(.wiki/导航.md), navigation_info |

## 使用方法

本技能是原子能力,由工作流标准步骤调用:

### 工作流中调用示例

```markdown
# 执行优化(工作流迭代-步骤6)

## 技能依赖
- workflow_creator

## 执行步骤
1. 构造工作流目录结构规范
2. 调用 workflow_creator 创建目录
3. 调用 workflow_creator 创建文件
4. 调用 workflow_creator 注册导航
```

### 直接调用(调试用途)

```text
创建工作流资产:
- 操作类型: create_directory
- 目标路径: .worker/.wiki/工作流/QA/

创建工作流资产:
- 操作类型: create_file
- 目标路径: .worker/.wiki/工作流/QA/_INDEX.md
- 内容: # QA 类别索引...
```

## 核心约束

1. **不理解业务**: 只关心"文件路径"和"文件内容",不理解业务语义
2. **物理操作**: 只执行 mkdir/write/update,不进行设计评估或架构审查
3. **幂等性**: 相同操作重复执行不会报错(已存在的目录不会重复创建)
4. **失败即停**: 操作失败时立即返回错误,不继续后续操作

## 批量操作支持

支持批量操作,减少调用次数:

```yaml
operations:
  - operation_type: create_directory
    target_path: .worker/.wiki/工作流/QA/
  - operation_type: create_file
    target_path: .worker/.wiki/工作流/QA/_INDEX.md
    content: "# QA 类别索引..."
  - operation_type: create_file
    target_path: .worker/.wiki/工作流/QA/WORKFLOW.md
    content: "---\nname: QA..."
```

## 导航注册格式

当操作类型为 `register_navigation` 时,需要提供导航信息:

```yaml
navigation_info:
  category: QA
  description: 质量保证、测试自动化
  keywords: [测试, 验证, 自动化]
  path: 工作流/QA/
```

## 输出规范

所有操作结果返回结构化数据:

```json
{
  "operation_result": "success",
  "created_files": [
    ".worker/.wiki/工作流/QA/_INDEX.md",
    ".worker/.wiki/工作流/QA/WORKFLOW.md"
  ],
  "error_message": null
}
```

失败时:

```json
{
  "operation_result": "failed",
  "created_files": [],
  "error_message": "无法创建目录: 权限不足"
}
```

## 注意事项

1. **路径验证**: 执行前验证父目录是否存在,不存在则报错
2. **内容编码**: 文件内容必须是 UTF-8 编码
3. **路径分隔符**: 统一使用 `/` 分隔符,Windows 环境自动转换
4. **原子性**: 单个操作失败不会影响已完成的操作,但批量操作会中断

## 版本信息

- **版本**: 3.0
- **重构时间**: 2026-07-16
- **重构原因**: 采用功能导向命名,重命名为 workflow_creator
- **历史版本**: 2.0 (repo_task_creator)