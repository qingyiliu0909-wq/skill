# UnrealMCP 连接说明

> **直接让 AI 读取本文件进行部署流程分析即可。**

本文档说明如何在 EM 项目中，将 AI 客户端（Cursor / Claude Desktop / Trae 等）连接到 Unreal Editor，通过 MCP 协议读写蓝图、UMG 与关卡数据。


## 参考链接

| 资料 | 链接 / 路径 |
|------|-------------|
| **飞书文档（部署参考）** | https://herogames.feishu.cn/docx/EQ7nd8KmBoyzIYxf7jScqCVmnQe |
| **Agent 操作 Skill(持续更新)** | [unreal-mcp/SKILL.md](unreal-mcp/SKILL.md) |
| **MCP 工具完整列表(持续更新)** | [unreal-mcp/reference/tool-reference.md](unreal-mcp/reference/tool-reference.md) |
| **UI Lua 绑定规范** | `.claude/skills/ui-lua` 或 `.cursor/skills/ui-lua` |
| **离线蓝图分析（T3D）** | `.claude/skills/ue-blueprint-analyzer` |
| **插件 Python 说明** | `Plugins/UnrealMCP/Python/README.md` |

---

## 连接架构

```
AI 客户端（Cursor 等）
    │  MCP stdio 协议
    ▼
Python MCP Server（unreal_mcp_server.py）
    │  TCP 127.0.0.1:55777
    ▼
Unreal Editor（UnrealMCP 插件）
```

- **MCP 服务器名称**：`unreal_mcp_server`（在 Cursor 中显示为 `user-unreal_mcp_server`）
- **UE 监听端口**：`55777`（定义于 `Plugins/UnrealMCP/Source/UnrealMCP/Private/UnrealMCPBridge.cpp`）
- **Python 桥接目录**：`Plugins/UnrealMCP/Python`

---

## 前置条件

在按顺序操作前，请确认以下条件均已满足。

### 1. 环境与工具

| 项 | 要求 |
|----|------|
| 操作系统 | Windows（EM 项目当前主要平台） |
| Unreal Editor | 已安装并可正常打开 `EM.uproject` |
| Python | **3.10+**（以 `Plugins/UnrealMCP/Python/pyproject.toml` 的 `requires-python >=3.10` 为准，推荐 3.13；`init-unreal-mcp.bat` 会校验 `>=3.10`） |
| uv | Python 包管理器，用于运行 MCP Server |
| AI 客户端 | 已安装并支持 MCP（如 Cursor） |

### 2. 项目插件

- UnrealMCP 插件位于：`Plugins/UnrealMCP`
- 首次使用需在 UE 编辑器中确认插件已启用：
  - 菜单 **Edit → Plugins**，搜索 `UnrealMCP`，勾选启用
  - 或确认 `Plugins/UnrealMCP/UnrealMCP.uplugin` 存在且未被禁用
- 插件启动后会在本机 `127.0.0.1:55777` 监听 TCP 连接

### 3. Python 依赖

- 项目路径：`Plugins/UnrealMCP/Python`
- 依赖由 `uv sync` 自动安装（见下方一键脚本）
- 主要依赖：`mcp`、`fastmcp`、`fastapi`、`pydantic` 等（见 `pyproject.toml`）

### 4. MCP 客户端配置

- 需将 `unreal_mcp_server` 注册到 AI 客户端的 MCP 配置中
- 配置模板见本目录下的 [`unreal_mcp_server.mcp.json`](unreal_mcp_server.mcp.json)

---

## 自动部署（AI 可执行）

> 让 AI 直接代为部署时参考本块：以下区分「AI 可自动完成」与「必须人工」的步骤。分步细节见下方〈操作顺序〉。

> **AI 触发**：AI 读取完本 readme 后，应**主动询问用户**「是否现在开始进行 UnrealMCP 环境部署？」。仅在用户确认后，才按〈AI 可自动执行〉逐步执行；执行中遇到〈必须人工〉的步骤时，停下并提示用户操作，待其完成后再继续。

### AI 可自动执行（软件侧）

1. **安装依赖**：在 `Plugins/UnrealMCP/Python` 执行 `uv sync`（uv 按 `pyproject.toml` 的 `requires-python >=3.10` 自动准备解释器、装依赖）。
   - 等价于运行 `init-unreal-mcp.bat`；命令行 / AI 调用会自动跳过末尾 `pause`。首次装了 `uv` 但 PATH 未刷新时，把 `%USERPROFILE%\.local\bin` 加入 PATH 后重试。
2. **写入客户端配置**：读取 `unreal_mcp_server.mcp.json`，将其 `mcpServers.unreal_mcp_server` 节点合并进 AI 客户端的 MCP 配置文件。
3. **安装 Skill（必须）**：运行 `install_to_cursor.bat`（或 `install_to_claude.bat` / `install_to_trae.bat`），确保 AI 按规范操作 UMG / 蓝图。

### 必须人工（AI 无法代劳）

- 启动 UE 编辑器并启用 UnrealMCP 插件（Edit → Plugins），确认 Output Log 出现 `Server started on 127.0.0.1:55777`。
- 在 AI 客户端 MCP 面板中**启用 / 重载** `unreal_mcp_server`（首次需用户授权）。

完成上述后，AI 可调用任一只读工具（如 `get_unlua_binding`）验证端到端连通。

---

## 操作顺序

按以下顺序执行。首次搭建与日常连接的区别见各步骤说明。

### 步骤 1：一键初始化 Python 环境（仅首次或依赖变更时）

在资源管理器中双击运行：

```
.skill\UnrealMCP\init-unreal-mcp.bat
```

脚本将自动完成：

1. 检测并安装 `uv`（若未安装）
2. 校验 Python 版本（`>=3.10`，以 `pyproject.toml` 为准）
3. 在 `Plugins/UnrealMCP/Python` 执行 `uv sync`
4. 生成 MCP 配置片段 → `unreal_mcp_server.mcp.json`

若脚本失败，可手动执行：

```powershell
cd D:\DNA\trunk\demo\EM\Plugins\UnrealMCP\Python
uv sync
uv run python unreal_mcp_server.py
```

### 步骤 2：配置 AI 客户端 MCP

将 `unreal_mcp_server.mcp.json` 中的内容添加到客户端 MCP 配置。

**Cursor 示例**（Settings → MCP → 编辑配置）：

```json
{
  "mcpServers": {
    "unreal_mcp_server": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "D:\\DNA\\trunk\\demo\\EM\\Plugins\\UnrealMCP\\Python",
        "run",
        "unreal_mcp_server.py"
      ]
    }
  }
}
```

> 注意：请将 `--directory` 后的路径改为你本机 EM 项目的实际绝对路径。运行 `init-unreal-mcp.bat` 后会自动生成带正确路径的配置。

配置完成后，在 Cursor MCP 面板中确认 `unreal_mcp_server` 显示为**已启用 / 已连接**（绿色状态）。

### 步骤 3：安装 Agent Skill（必须）

为确保 AI 按规范操作 UMG / 蓝图，必须将 Skill 同步到客户端：

```bat
.skill\UnrealMCP\install_to_cursor.bat
```

- 目标路径：`.cursor/skills/unreal-mcp/`
- Claude 用户可运行 `install_to_claude.bat`
- Trae 用户可运行 `install_to_trae.bat`

> Skill 源码目录为 `unreal-mcp/`，请勿直接修改 `.cursor/skills/` 下的副本，下次 install 会被覆盖。

### 步骤 4：启动 Unreal Editor（必须先于 MCP 连接）

1. 打开 `EM.uproject`
2. 等待编辑器完全加载
3. 确认 UnrealMCP 插件已启用
4. 在 Output Log 中可看到类似日志：
   ```
   UnrealMCPBridge: Server started on 127.0.0.1:55777
   ```

**重要**：必须先启动 UE，再让 MCP Server 连接。若顺序颠倒，Python 端会报连接失败，可在 UE 启动后重载 MCP 或新开对话重试。


## 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `Failed to connect to Unreal` | UE 未启动或插件未启用 | 先开 UE，再在 Cursor 中重载 MCP |
| MCP 服务器显示红色 / 未连接 | `uv` 未安装或路径错误 | 重跑 `init-unreal-mcp.bat`，检查 JSON 中 `--directory` 路径 |
| 工具调用超时 | UE 正在编译 / 卡顿 | 等待编译完成后再调用 |
| `uv sync` 失败 | Python 版本不符（需 `>=3.10`） | 安装 Python 3.10+ 后执行 `uv venv --python 3.10 && uv sync` |
| 修改资产无效果 | 未 compile/save | UMG 写操作后需调用 `umg_compile_save` |

日志文件：`Plugins/UnrealMCP/Python/unreal_mcp.log`

---

## 连接成功后可做什么

连接建立后，可通过 MCP 进行以下操作（完整列表见 [tool-reference.md](unreal-mcp/reference/tool-reference.md)）：

| 类型 | 示例工具 |
|------|----------|
| 只读 | `read_blueprint`、`umg_get_tree`、`umg_get_animations`、`get_actors_in_level` |
| 写入（需确认） | `umg_add_widget`、`umg_compile_save`、`bind_blueprint_to_unlua`、`spawn_actor` |

操作规范与确认流程见 [SKILL.md](unreal-mcp/SKILL.md)。

---