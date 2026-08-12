---
name: "lark-mcp"
description: "飞书MCP代理技能。本地MCP代理，负责管理用户访问令牌(UAT)并转发MCP请求到远程飞书MCP服务器。

功能：
- UAT管理（自动存储、刷新）
- MCP请求转发（自动附加UAT）
- OAuth授权流程（浏览器扫码）
- 增量权限（缺什么权限自动补什么）

使用前需要先运行授权命令获取UAT。"
---

# lark-mcp

本地飞书MCP代理，负责UAT管理和请求转发。

## 工作原理

```
┌─────────┐     MCP请求      ┌─────────┐    HTTP+UAT    ┌─────────────┐
│  Trae   │ ──────────────→ │ lark-mcp│ ─────────────→ │ MCP服务器   │
│         │ ←────────────── │  代理   │ ←───────────── │ (远程)      │
└─────────┘    MCP响应+结果  └─────────┘    响应         └─────────────┘
                          ↑
                          │
                   ┌──────┴──────┐
                   │ uat_token.json
                   │ (本地文件)   │
                   └─────────────┘
```

## 快速开始

### 1. 首次授权

```bash
python {SKILL_PATH}/scripts/lark_mcp.py auth
```

命令执行后会：
1. 自动打开浏览器（或手动打开URL）
2. 扫码/点击授权
3. 自动获取并保存UAT

### 2. 检查UAT状态

```bash
python {SKILL_PATH}/scripts/lark_mcp.py check
```

### 3. 调用工具

**⚠️ 必须使用 Python 脚本方式调用，避免命令行转义问题：**

```python
import subprocess
import json

args = {
    "wiki_node": "ZneewDV5uiL95Sk84l9cysgSnAh",
    "title": "EM性能分析报告",
    "markdown": "## 执行摘要\n\n报告内容..."
}

script_path = r"{SKILL_PATH}\scripts\lark_mcp.py"
cmd = ["python", script_path, "invoke", "feishu_create_doc", json.dumps(args)]
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
```

## 命令行接口

| 命令 | 说明 |
|------|------|
| `auth` | 启动OAuth授权流程，获取新UAT |
| `auth --add-scope <scopes>` | 增量添加权限后重新授权 |
| `check` | 检查当前UAT是否有效 |
| `clear` | 清除保存的UAT |
| `tools` | 列出MCP服务器支持的所有工具 |
| `invoke <name> <args_json>` | 调用指定工具 |

## 增量权限

调用工具时，如果遇到权限不足错误，脚本会自动：
1. 检测缺失的权限
2. 自动重新发起授权流程（添加缺失权限）
3. 重试工具调用

示例输出：
```
[PERMISSION] Missing scopes detected: ['search:docs:read']
[PERMISSION] Re-authorizing to add missing scopes...
[PERMISSION] Re-authorization successful, retrying invoke...
```

也可以手动添加权限：
```bash
python scripts/lark_mcp.py auth --add-scope search:docs:read,docx:document:create
```

## 工具调用方式

### ⚠️ 重要：必须使用 Python subprocess 调用

**错误方式**（命令行直接调用会有转义问题）：
```bash
# ❌ 会出错
python scripts/lark_mcp.py invoke feishu_create_doc '{"title": "test", "markdown": "..."}'
```

**正确方式**（使用 Python subprocess）：
```python
import subprocess
import json

args = {
    "title": "测试文档",
    "wiki_space": "6989895554718875676",
    "markdown": "## 标题\n\n内容"
}

cmd = [
    "python",
    r"{SKILL_PATH}\scripts\lark_mcp.py",
    "invoke",
    "feishu_create_doc",
    json.dumps(args)
]

result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
```

## 常用工具

### feishu_search
搜索文档、消息等。

### feishu_create_doc
创建飞书云文档。

### feishu_fetch_doc
获取文档内容。

### feishu_update_doc
更新文档内容。

### feishu_im_message
发送消息。

### feishu_calendar_event
管理日历事件。

### feishu_task
管理任务。

### feishu_bitable
操作多维表格。

## UAT管理

UAT（User Access Token）是用户身份凭证，具有以下特点：
- 有效期约2小时
- 存储在本地文件 `config/uat_token.json`（相对于技能目录）
- 脚本会自动检测过期并在需要时自动刷新

### 刷新UAT

```bash
python {SKILL_PATH}/scripts/lark_mcp.py auth
```

## 目录结构

```
lark-mcp/
├── scripts/
│   └── lark_mcp.py      # 主脚本（核心功能）
├── commands/
│   └── *.py             # 临时调试脚本（非功能代码）
├── config/
│   └── uat_token.json   # UAT存储位置
└── SKILL.md             # 本文档
```

## 故障排除

### UAT过期
```
[WARN] UAT is invalid or expired
```
解决：运行 `python {SKILL_PATH}/scripts/lark_mcp.py auth` 重新授权

### 连接失败
```
[MCP] <- tools/list (error: Connection refused)
```
解决：检查MCP服务器是否运行

### 权限不足
```
[PERMISSION] Missing scopes detected: [...]
```
解决：脚本会自动重新授权，如果失败可手动运行：
```bash
python {LARK_MCP_SCRIPT} auth --add-scope <缺失的权限>
```

### 授权失败
检查：
1. LARK_APP_ID 和 LARK_APP_SECRET 是否正确
2. 飞书应用是否已启用OAuth能力
3. 回调地址是否在飞书开放平台配置正确
