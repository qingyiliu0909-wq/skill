# UnrealMCP 工具开发规范（开发 / 新增 MCP 工具｜初版）

> 本文档约束**开发 UnrealMCP 工具本身**（插件 C++/Python 代码），以及维护本 skill 文档的流程（见第六节）。规范以现有 **UMG 工具链** 的实现风格为蓝本提炼，为**初版**，发现与代码不一致时以工程实际为准并按需更新本文。
>
> 注：`Plugins/UnrealMCP/Python/README.md` 的 *Development* 段（"modify `UnrealMCPBridge.py`…"）**已过时**——工程没有 `UnrealMCPBridge.py`，工具按域拆在 `Python/tools/*.py`，C++ 命令在 `Source/UnrealMCP/Private/Commands/`。以本文为准。

## 〇、MCP 插件源码位置

需改 MCP 行为 / 排查实现时用（区别于 skill 文档源码 `.skill/UnrealMCP/unreal-mcp/`）：

- **C++**：`Plugins/UnrealMCP/Source/UnrealMCP/`（命令实现在 `Private/Commands/`；公共工具类为各 `*Utils`，如 UMG 编译落盘 `UMGWidgetUtils.cpp::CompileAndMaybeSave`）
- **Python（MCP server）**：`Plugins/UnrealMCP/Python/`（入口 `unreal_mcp_server.py`，工具转发在 `tools/*.py`）
- 改 C++ 需**重新编译插件**才生效；改 Python 重启 MCP server 即可

## 一、一个工具的完整调用链

一个 MCP 工具从「Agent 调用」到「UE 执行」要贯穿 5 层，缺一不可：

```
Agent → descriptor JSON ──► Python tool 层 ──► server 注册 ──► C++ Bridge 分发 ──► C++ Command Handler ──► (Utils) → UE
        tools/<tool>.json   tools/<dom>_tools  unreal_mcp_     UnrealMCPBridge.cpp  UnrealMCP<Dom>Commands  *Utils 类
                            .py @mcp.tool()    server.py        ExecuteCommand       .cpp HandleCommand
```


| 层         | 文件                                                                           | 职责                                                                |
| --------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Python 工具 | `Python/tools/<domain>_tools.py`                                             | `@mcp.tool()` 定义参数与 docstring，转发命令到 UE                            |
| Server 注册 | `Python/unreal_mcp_server.py`                                                | `import` 并调用各域 `register_<domain>_tools(mcp)`                     |
| C++ 分发    | `Source/UnrealMCP/Private/UnrealMCPBridge.cpp`                               | `ExecuteCommand` 按 `CommandType` 路由到对应域 Command 对象（GameThread 执行） |
| C++ 命令处理  | `Source/UnrealMCP/Private/Commands/UnrealMCP<Domain>Commands.cpp`            | `HandleCommand` 二级分发到私有 `Handle<Xxx>`，解析参数、执行、返回 JSON             |
| C++ 公共工具  | `Source/UnrealMCP/.../Commands/<Domain>/*Utils.*` & `UnrealMCPCommonUtils.*` | 复用逻辑（查资产、解析 JSON、构造响应、编译落盘等）                                      |


## 二、在「已有域」新增一个工具（最常见）

以给 UMG 域新增 `umg_foo` 为例，按顺序改 4 处代码 + 3 处文档：

**1) C++ 命令处理类**（`UnrealMCPUMGCommands.h` / `.cpp`）

- `.h` 私有区声明 `TSharedPtr<FJsonObject> HandleUMGFoo(const TSharedPtr<FJsonObject>& Params);`
- `.cpp` 在 `HandleCommand` 的 if/else 链加分支：`else if (CommandName == TEXT("umg_foo")) Result = HandleUMGFoo(Params);`
- 实现 `HandleUMGFoo`：解析→校验→执行→返回（见「四、编码约定」）。

**2) C++ Bridge 分发**（`UnrealMCPBridge.cpp::ExecuteCommand`）
在对应域的 `CommandType == TEXT(...)` 列表里加上 `|| CommandType == TEXT("umg_foo")`，确保路由到 `UMGCommands->HandleCommand(...)`。

**3) Python 工具转发**（`tools/umg_tools.py` 的 `register_umg_tools`）

```python
@mcp.tool()
def umg_foo(
    ctx: Context,
    asset_path: str,
    bar: int = 0,
    compile_save: bool = True,
) -> Dict[str, Any]:
    """一句话功能说明（会成为工具描述）。说明默认值与副作用。"""
    try:
        return _send_umg_command("umg_foo", {
            "asset_path": asset_path,
            "bar": bar,
            "compile_save": compile_save,
        })
    except Exception as e:
        error_msg = f"Error in umg_foo: {e}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}
```

**4) descriptor + 文档**：生成/更新 `mcps/user-unreal_mcp_server/tools/umg_foo.json`，并在 `tool-reference.md` 加一行（标注 R / W / R/W）、必要时在 `SKILL.md` 相关章节补充。

**5) 生效**：改了 C++ → **重新编译插件**；只改 Python → **重启 MCP server**。

## 三、新增一个「域」（domain）

当工具属于全新领域（既不属于 umg/blueprint/node/editor/project/niagara/animation）时：

1. 新建 `Python/tools/<domain>_tools.py`，提供 `register_<domain>_tools(mcp)` 与私有 `_send_<domain>_command`（参照 `umg_tools.py` 的 `_send_umg_command`）。
2. 在 `unreal_mcp_server.py` 顶部 `from tools.<domain>_tools import register_<domain>_tools`，并在注册区调用一次。
3. 新建 C++ `FUnrealMCP<Domain>Commands`（`.h` + `.cpp`，含 `HandleCommand`）。
4. 在 `UnrealMCPBridge` 构造函数 `MakeShared<FUnrealMCP<Domain>Commands>()` 实例化并持有，在 `ExecuteCommand` 加该域的分发分支。

## 四、编码约定

- **命名**：命令名 = Python 工具函数名，`snake_case` 且**带域前缀**（`umg_`*、`add_blueprint_*`、`read_*`）。C++ 处理函数用 `Handle<PascalCase>`。
- **参数键名**：Python 形参与 JSON key 可不同（如 `widget_class` 转发为 `"class"`）；C++ 端用同一 JSON key 解析。新增时尽量保持形参名==JSON key，确需不同要在 docstring/reference 注明。
- **参数解析（C++）**：用 `Params->TryGetStringField/TryGetBoolField/...` 或 `FUnrealMCPCommonUtils` 的 `GetIntArrayFromJson` / `GetVector2DFromJson` 等；必填字段缺失/非法立即 `return FUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'xxx'..."))`。
- **响应结构（C++）**：成功用 `FUnrealMCPCommonUtils::CreateSuccessResponse(Data)`（带 `success:true` + 数据），失败用 `CreateErrorResponse(Message)`。Python 层会把 `status==error` 与 `success==false` 两种统一成 `{status:error, error}`，所以 Python 兜底返回 `{"success": False, "message": ...}` 即可。
- **C++↔Python 同步确认（改 C++ 后必做）**：每次改动 UnrealMCP 的 C++ 源码后，**必须回查 Python 侧是否需要同步**，因为 Agent 看到的工具契约来自 Python `@mcp.tool()` docstring 与 descriptor JSON：
  - 命令名 / JSON key / 必填项变化（新增、改名、删除、改可选性）→ 同步 `tools/<domain>_tools.py` 的 `@mcp.tool()` 形参与转发的 command/参数，以及 `unreal_mcp_server.py` 的注册。
  - **入参语义 / 默认值 / 取值范围变化，或返回字段变化（新增/改名/删字段、改类型、改含义）→ 同步工具 docstring 的「参数说明」与「返回值说明」，以及 descriptor JSON（`mcps/user-unreal_mcp_server/tools/<tool>.json`）的 parameters / returns 描述。**
  - 仅改 C++ 内部实现、不影响协议（命令名/参数/返回结构均不变）→ 无需改 Python，但仍要在自检中**明确确认「无协议变化」**。
  - 原则：**C++ 实际行为是唯一真源（source of truth），Python docstring / descriptor 必须与之一致**；发现不一致时以 C++ 为准并立即修正 Python 侧。
- **R/W 分类**：只读工具仅返回数据，不改资产；写工具改资产并须遵守 `SKILL.md` 阶段 2 确认门控，且在 `tool-reference.md` 标 **W** / **R/W**。
- **幂等**：无副作用的"没找到/已存在/无需改"应返回**成功 + 标志位**（如 `found:false` / `created:false` / `deleted:false`，且不标脏资产），而非报错；需要"缺失即报错"时用显式参数（如 `fail_if_missing=true`）。
- **编译/落盘语义**：
  - UMG 写工具统一带 `compile_save`（默认 `true`），由 `FUMGWidgetUtils::ApplyAutoCompileSaveIfNeeded` 在**成功且非 no-op**时自动 compile+save；编译失败不保存并回报错误。`compile_save=false` 仅标脏内存（用于手动批处理 `umg_batch`）。
  - 蓝图类多数 `set_`* 只标脏内存，需显式 `save_blueprint` 落盘（`compile=true` 先编译）。
- **线程**：`ExecuteCommand` 已通过 `AsyncTask(ENamedThreads::GameThread, ...)` 在 GameThread 执行 handler，handler 内可直接操作 UObject/资产，**勿再自行切线程**。
- **日志（Python）**：`logger = logging.getLogger("UnrealMCP")`；转发前 `logger.info` 命令与参数，异常 `logger.error`。
- **批处理**：若工具需支持批量，参考 `umg_batch`（`operations` 数组 + fail-fast + `partial_results`），单步成功不等于落盘，末尾再统一 compile_save。

## 五、验收 checklist（提交前自检）

- 5 层齐全：descriptor JSON / Python tool / server 注册 / Bridge 分发 / Command handler 都已加且命令名一致
- C++编译通过（改 C++ 必重编）；只改 Python 已重启 server
- **改 C++ 后已回查 Python 侧同步**：命令名 / JSON key / 必填项一致，工具 docstring 的参数说明与返回值说明、descriptor JSON 均与 C++ 实际行为一致（若无协议变化，也已明确确认无需改 Python）
- 用 descriptor 实际调用一次：成功路径返回结构正确，错误路径返回 `CreateErrorResponse` 文案清晰
- 写工具：compile_save / save 语义正确，no-op 不误报错、不误标脏
- `tool-reference.md` 已补行并标注 R/W；`SKILL.md` 必要处已更新
- 写操作仍遵循 `SKILL.md` 阶段 2 确认门控

## 六、Skill / reference 文档维护流程（维护本 skill 时必走）

> 本节约束**维护本 skill 文档**（`SKILL.md` / `tool-reference.md` / 工具说明），区别于上文「开发工具本身」的代码改动。

当用户请求**更新本 skill 的描述 / reference / 工具说明**（如「更新 skill」「同步最新工具」「校对 reference」）时，按以下流程执行，**改前必先列差异并取得确认**：

1. **全面自检 MCP 工具链**：以 MCP server 当前实际工具为准，逐一比对，不凭记忆。
  - 用 `mcps/user-unreal_mcp_server/tools/*.json` 的 descriptor 清单作为「现有工具全集」（必要时实际调用一次以确认在线状态与工具是否真被注册）。
  - 与 `SKILL.md`、`tool-reference.md` 中出现的工具名与参数描述逐项对照。
2. **归类差异**：
  - **新增工具**：工具链有、文档未收录 → 拟新增条目（含类型 R/W、参数、风险）。
  - **废除工具**：文档提及、工具链已无 → 拟删除相关条目（直接删，不保留）。
  - **描述过时**：工具仍在但参数/行为/模式已变（如新增参数、单模式变双模式）→ 拟修正。
3. **列出改动清单**：把上述「新增 / 删除 / 修正」分类列给用户，**等待明确确认**（遵循 `SKILL.md` 阶段 2 操作确认门控）。
4. **确认后修改并同步**：仅改源码目录（`.skill/.../unreal-mcp/`）的 `SKILL.md` / `reference/tool-reference.md`，再运行 `install_to_cursor.bat` 与 `install_to_claude.bat` 同步，最后报告改动小结与同步结果。

> 注意：本流程本身属于「文档/skill 维护」，自检（读 descriptor、只读调用）无需确认；但**写回文档前必须先列差异并取得用户确认**。
