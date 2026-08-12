---
name: unreal-mcp
description: 通过 Unreal MCP（user-unreal_mcp_server）读取 UE 蓝图/UMG/关卡信息，或创建、修改、编译、保存 UMG Widget Blueprint；也包含 UnrealMCP 工具本身的开发规范（新增/维护 MCP 工具）。当用户提到 UnrealMCP、read_blueprint、bind_blueprint_to_unlua、umg_get_tree、在编辑器中改蓝图/UMG、从 mockup 搭建界面、通过 MCP 与运行中的 UE 交互、或要开发/新增/维护 UnrealMCP 工具（改 Python tools/*.py 与 C++ Commands/）时使用。信息获取采用递进式披露；任何会修改资产的 MCP 操作必须先输出方案并等待用户明确确认。
---

# Unreal MCP 操作指南

通过 MCP 服务器 `user-unreal_mcp_server` 与**已启动且已连接 MCP 插件的 Unreal Editor** 交互。不要使用已废弃的 UMGAssetCommandlet 流程。

> **关联资料**
>
> - 首次使用请走一遍：[readme.md](.skill/UnrealMCP/readme.md)（仓库路径 `.skill\UnrealMCP\readme.md`，含 MCP 环境配置/安装步骤；该文件不随 skill 分发，故用此固定路径）
> - 工具完整列表：[tool-reference.md](reference/tool-reference.md)
> - Flow 资产读/写（对话树等）：`flow-mcp` skill（同 MCP server 的 `flow_*` 工具）
> - UI Lua 绑定规范：`ui-lua`
> - 离线蓝图深度分析（T3D）：`ue-blueprint-analyzer`

> **开发 / 维护本 MCP**：插件源码位置、新增/维护 MCP 工具、以及 skill / reference 维护流程，统一见开发规范 [reference/tool-development.md](reference/tool-development.md)。本 skill 正文只保留 MCP 的**使用执行规范**。

---

## 阶段 0：前置检查

调用任何 MCP 工具前：

1. **读工具 schema**：`CallMcpTool` 前必须先查看 `mcps/user-unreal_mcp_server/tools/<tool>.json`。
2. **确认 Editor 在线**：工具失败且提示连接问题时，告知用户先启动 UE 并确保 MCP 插件已连接，不要反复盲重试。
3. **区分任务类型**：


| 类型       | 定义                | 是否需用户确认         |
| -------- | ----------------- | --------------- |
| **信息获取** | 只读，不改变资产/关卡       | 否（但须递进披露，见阶段 1） |
| **操作执行** | 创建/修改/删除/编译/绑定/生成 | **是**（见阶段 2）    |


---

## 阶段 1：信息获取（递进式披露）

**禁止**在未询问的情况下一次性拉取全部细节（如 `read_blueprint` 的 `full` + 深层 `max_depth` + 动画 keys + 事件图节点）。

### 1.1 默认起点（第一层）

按用户问题选**最小够用**的只读工具，默认返回摘要：


| 用户意图            | 首选工具                                          | 默认参数                           |
| --------------- | --------------------------------------------- | ------------------------------ |
| 了解蓝图概况          | `read_blueprint`                              | `detail_level: "summary"`      |
| 查 UnLua 绑定（仅绑定） | `get_unlua_binding`                           | `blueprint_name`               |
| 查看 UMG 控件树      | `umg_get_tree`                                | `asset_path`                   |
| 读 UMG 控件属性      | `umg_get_widget_property`                     | `asset_path`、`name`；单属性加 `property` |
| 列出 UMG 动画名      | `umg_get_animations`                          | `asset_path`                   |
| 查 UMG 能力/支持类    | `umg_get_supported_capabilities`              | 无参                             |
| 查事件图节点          | `find_blueprint_nodes`                        | 按需加 `node_type` / `event_type` |
| 查关卡 Actor       | `get_actors_in_level` / `find_actors_by_name` | 按需                             |
| 读动画资产           | `read_anim_sequence` / `read_anim_montage`    | 资产路径                           |
| 读 Niagara       | `read_niagara_system`                         | 资产路径                           |


路径约定：

- **蓝图名**（`read_blueprint`、`bind_blueprint_to_unlua` 等）：仅资产名，如 `WBP_CommonGetItem`，工具会在 `/Game/` 下递归查找。
- **UMG 资产路径**（`umg_`*）：Content 包路径，如 `/Game/UI/WBP/Foo/WBP_Foo`。

### 1.2 汇报后询问是否深入

第一层结果返回后，用简短摘要回答用户问题，然后**明确询问**是否需要更详细信息。示例：

```
已获取 WBP_XXX 摘要：父类 EM.UIState，变量 12 个，函数 8 个，控件树 3 层。

是否需要继续查看：
A. 完整蓝图（事件图、引脚、UnLua 绑定）— read_blueprint full
B. 指定控件属性/Slot 详情 — umg_get_tree 后定点说明
C. 动画轨道与关键帧 — umg_get_animation_detail / umg_get_animation_keys
D. 不需要，当前信息足够
```

**仅当用户选择继续**时，才进入下一层。每层仍遵循「够用即止」。

### 1.3 信息获取层级参考

```
L1 摘要     read_blueprint(summary) / umg_get_tree / umg_get_animations
    ↓ 用户确认
L2 结构细节 read_blueprint(full) / umg_get_animation_detail
    ↓ 用户确认
L3 最细粒度 umg_get_animation_keys / find_blueprint_nodes(精确筛选)
```

### 1.4 信息获取禁止项

- ❌ 未经询问直接 `detail_level: "full"` 且 `max_depth` 很大
- ❌ **只查 UnLua 绑定时用 `read_blueprint` full**（会附带控件树/事件图等冗余信息）；应改用 `get_unlua_binding`，仅返回 `status` / `lua_module_path` / `lua_file_path` / `lua_file_exists_on_disk` 等绑定字段
- ❌ 为「可能用到」而预读多个无关蓝图
- ❌ 把 `open_asset` 当作纯读取（会在编辑器中打开资产，见阶段 2）

---

## 阶段 2：操作执行（必须先确认）

凡会**修改** Unreal 资产、关卡、绑定或编辑器状态的 MCP 调用，均属操作类。

### 2.1 强制确认门控

1. 根据用户需求与（可选的）L1 读取结果，输出 **《MCP 操作方案》**（模板见下）。
2. 询问：**「方案确认后我再执行 MCP 操作，是否可以？」**
3. **仅当**用户明确回复以下之一时，才可调用写操作工具：
  - `确认` / `可以` / `OK` / `ok`
  - `实现方案` / `按方案执行` / `开始吧`
4. 以下回复**不算**确认，不得执行：
  - 仅补充需求、讨论细节、问问题
  - `再看看` / `先别动` / `等等`
  - 模糊语气（`好像可以`、`应该行吧`）

用户修改方案后，重新输出方案并再次等待确认。

### 2.2 操作方案模板

```markdown
## MCP 操作方案

**目标**：[一句话描述要达成的效果]

**前置条件**：
- UE Editor 已启动且 MCP 已连接
- 目标资产：[路径或蓝图名]

**计划调用**（按顺序）：
1. `tool_name` — 参数摘要 — 预期效果
2. ...

**影响面**：
- 将修改的资产/关卡对象
- 是否覆盖同名资产 / 是否编译保存
- 是否影响 UnLua 绑定

**回滚提示**：[SVN/备份建议，若适用]

请确认后我再执行。
```

### 2.3 操作类工具分类（概览）

完整列表与参数见 [tool-reference.md](reference/tool-reference.md)。


| 类别            | 代表工具                                                                                                                                                            | 风险                                                                                                              |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| UMG 结构编辑      | `umg_create_blueprint`, `umg_add_widget`, `umg_batch`, `umg_remove_widget`, `umg_reparent_widget`, `umg_set_*`                                                  | 改 Widget 树，需 `umg_compile_save` 才真正落盘                                                                           |
| UMG 动画编辑      | `umg_add_animation`, `umg_set_animation_keys`, `umg_bind_widget_to_animation`, …                                                                                | 改动画数据                                                                                                           |
| 蓝图编辑          | `create_blueprint`, `add_blueprint_*`, `connect_blueprint_nodes`, `set_blueprint_property`, `set_blueprint_parent_class`, `compile_blueprint`, `save_blueprint` | 改逻辑/组件；多数改属性仅标脏内存，需 `save_blueprint` 落盘                                                                         |
| UnLua 绑定      | `bind_blueprint_to_unlua`, `unbind_blueprint_from_unlua`                                                                                                       | bind：改接口并实现 GetModuleName，自动编译保存；`create_lua_file=true` 时从模板生成 `.lua`（已存在则失败）。unbind：移除绑定（幂等），不删 `.lua` 文件 |
| UnLua 绑定校验/清理 | `validate_lua_bound_blueprints`                                                                                                                                 | `remove_invalid=false` 为只读 dry run；`remove_invalid=true` 会改写 `.lua` 删除失效 `@BoundBlueprint` 行（须先 dry run 并经用户授权） |
| 关卡 Actor      | `spawn_actor`, `delete_actor`, `set_actor_*`, `spawn_blueprint_actor`                                                                                           | 改当前关卡                                                                                                           |
| 编辑器           | `open_asset`, `create_input_mapping`                                                                                                                            | 打开标签页 / 改输入配置                                                                                                   |


### 2.4 UnLua 绑定要点

#### 用户请求绑定时的交互约定

当用户请求「把蓝图绑定到 Lua」时，按以下流程响应：

1. **先索要两项输入**：明确告知用户需要提供
  - **蓝图路径**（资产名或 `/Game/...` 路径，用于推导 `blueprint_name`）
  - **Lua 文件路径**（用于推导 `lua_module_path`，相对 `Content/Script/`、点号分隔、以 `_C` 结尾）
2. **说明将在用户确认方案后、同一轮次内连续完成的工作**（**注意：下列「校验」由 Agent 调用，不是 `bind_blueprint_to_unlua` 工具内置步骤**）：
  - **绑定**：调用 `bind_blueprint_to_unlua` 建立绑定（实现接口并写入 `GetModuleName`，自动编译保存；仅写入/追加 `@BoundBlueprint` 注释）
  - **双向校验（必做）**：绑定成功后**立即**在同一轮次调用 `validate_lua_bound_blueprints`（见下文「绑定与校验 SOP」），**不得**把 bind 成功当作流程结束
  - **模板文件生成**：当目标 Lua 文件不存在时，以 `create_lua_file=true` 从模板生成对应的 `.lua` 文件（若文件已存在则不覆盖，应改用 `create_lua_file=false` 绑定到现有文件）
3. `**_C` 命名检查**：若用户提供的 Lua 文件名 / `lua_module_path` 末尾未带 `_C`，须**先询问一次**是否对文件名补全 `_C`（蓝图绑定的 Lua 模块约定以 `_C` 结尾）。待用户答复后再继续：同意则用补全后的名字，否则沿用用户给定名字。该询问只进行一次，不重复追问。
4. **得到确认后再执行**：先输出《MCP 操作方案》（含蓝图名与 `lua_module_path`），按阶段 2.1 等待用户明确确认，确认后才调用上述工具。

`bind_blueprint_to_unlua` 参数：


| 参数                | 格式                                  | 示例                                         |
| ----------------- | ----------------------------------- | ------------------------------------------ |
| `blueprint_name`  | 蓝图资产名                               | `WBP_CommonGetItem`                        |
| `lua_module_path` | 相对 `Content/Script/`，点号分隔，以 `_C` 结尾 | `BluePrints.UI.Common.WBP_CommonGetItem_C` |


对应 Lua 文件：`Content/Script/BluePrints/UI/Common/WBP_CommonGetItem_C.lua`

绑定前必须在方案中写明蓝图名与 `lua_module_path`，用户确认后再调用。

`bind_blueprint_to_unlua` 会在 Lua 文件顶部写入 `-- @BoundBlueprint: /Game/...` 注释记录绑定来源（一个 Lua 可被多个蓝图绑定，可能多行）。

##### `@BoundBlueprint` 路径格式约定（统一用 package 路径）

- 添加 `@BoundBlueprint` 注释时，引用路径**统一使用 package 路径**（不带对象后缀），如 `/Game/UI/WBP/Foo/WBP_Foo`，**不要**写成完整对象路径 `/Game/UI/WBP/Foo/WBP_Foo.WBP_Foo`。这与工具写入器（`bind_blueprint_to_unlua` 与 blueprint 模式 `auto_complete`，均取 `Blueprint->GetOutermost()->GetName()`）的规范格式一致。
- 手工补/改注释时也遵循此约定，保持全工程注释格式统一。
- 工具侧的 `validate_lua_bound_blueprints` 已对引用路径做 package 归一化（带/不带对象后缀视为同一引用），即使误写完整对象路径也能正确解析、不产生重复行；但**写入仍以 package 路径为准**。

#### 工具能力边界（bind ≠ validate）

| 能力 | `bind_blueprint_to_unlua` | `validate_lua_bound_blueprints` |
|------|---------------------------|----------------------------------|
| 设置蓝图 `GetModuleName` | ✅ | ❌ |
| 写入/追加 `@BoundBlueprint` 注释 | ✅（仅本次绑定的蓝图一行） | Blueprint 模式可补缺失注释 |
| 校验注释 ↔ 蓝图真实绑定（双向） | ❌ **不自动调用** | ✅ |
| 删除失效注释行（仅 `invalid`） | ❌ | ✅（`remove_invalid=true`；**仅删 invalid，不删 warnings**） |

> **实现事实**：Python/C++ 的 `bind_blueprint_to_unlua` 返回后**不会**链式调用 `validate_lua_bound_blueprints`。Skill 中的「绑定后校验」是 **Agent 工作流强制步骤**，不是 MCP 工具内置行为。

#### 绑定与校验 SOP（Agent 强制，每次 bind 成功后同一轮次执行）

**禁止**在仅调用 `bind_blueprint_to_unlua` 后即向用户汇报「绑定完成」。必须按序完成：

| 步骤 | 调用 | 参数要点 | 目的 |
|------|------|----------|------|
| **S1 绑定** | `bind_blueprint_to_unlua` | `create_lua_file` 按文件是否存在选择 | 蓝图侧绑定 + 写入一条 `@BoundBlueprint` |
| **S2 Lua 模式 dry-run** | `validate_lua_bound_blueprints` | `lua_module_path=<模块>`，`remove_invalid=false` | **Lua → 蓝图**：逐行校验文件中所有 `@BoundBlueprint` 是否与真实 `GetModuleName` 一致 |
| **S2b 自动清理 invalid** | `validate_lua_bound_blueprints` | 同上 `lua_module_path`，`remove_invalid=true` | **当 S2 的 `invalid_count > 0` 时同一轮次立即执行**，自动删除 `invalid` 行（`BlueprintNotFound` / `EmptyBlueprintRef` / `DuplicateBlueprintRef`）；**无需再向用户征求删除授权** |
| **S3 蓝图模式补全（建议）** | `validate_lua_bound_blueprints` | `blueprint_name=<刚绑定的蓝图>`，`auto_complete_comment=true` | **蓝图 → Lua**：确认该蓝图在绑定 Lua 中有对应注释（缺失则补写） |
| **S4 汇报** | （无工具） | 汇总 S2/S2b/S3 的 `valid_count` / `invalid` / `removed_count` / `warnings` | 向用户说明双向绑定状态及已自动删除的失效行；**warnings 须单独说明处理建议** |

`warnings`（如 `BoundToDifferentModule`）**禁止**自动删除，须在 S4 汇报后由用户决定是否改绑/改注释。

**多蓝图共绑同一 Lua**：每绑定一个蓝图执行一次 S1 + S3；全部 bind 完成后对同一 `lua_module_path` 执行一次 S2 →（若有 invalid）S2b。

**无注释存量文件**：S2 若返回 `NoBoundBlueprintComments`，先用 `search_bindings_if_missing=true` 只读扫描，再决定是否补 bind/补注释，禁止静默跳过。

**S2b 执行条件**：仅当 S2 返回 `invalid_count > 0` 时调用；`invalid_count == 0` 时跳过 S2b。S2b 完成后可再跑一次 `remove_invalid=false` 确认 `invalid_count == 0`（可选）。

#### 绑定后校验（细则与失效原因）

`@BoundBlueprint` 注释会随时间失效（蓝图被删除、改绑、解绑），需用 `validate_lua_bound_blueprints` 校验。约定流程：

1. **每次 `bind_blueprint_to_unlua` 成功后**，在同一轮次按上表 **S2 → S2b（条件）→ S3 → S4** 执行，不得省略。
2. **先 dry run（S2）**：`remove_invalid=false`，列出 invalid / warnings 及原因。
3. **自动清理 invalid（S2b）**：若 `invalid_count > 0`，**立即**以 `remove_invalid=true` 再次调用并删除 **invalid** 行，**无需用户二次确认**（绑定方案确认已覆盖此写操作）。
4. **warnings 不自动处理**：`BlueprintNotBound` / `BoundToDifferentModule` 仅汇报，须用户决定是否改绑或改注释。

> 注：UnLua 编辑器的「Create Lua Template」也会写入 `@BoundBlueprint` 注释，但**不做校验**；双向校验/清理统一由 Agent 按本 SOP 调用 `validate_lua_bound_blueprints` 完成。

---

## 阶段 3：执行与交付

### 3.1 执行中

- 严格按已确认方案顺序调用；若中途失败，**停止**并报告错误，不擅自换方案重试。
- 需偏离方案时，先说明差异并重新走阶段 2 确认。

### 3.2 交付清单

```markdown
## MCP 操作交付

**已执行**：
- [x] tool_name — 结果摘要

**验证**：
- 编译/保存：[成功/失败]
- 磁盘资产：[路径] [存在/缺失]
- 绑定：[lua_module_path] [成功/失败]
- **双向校验（bind 后必报）**：
  - Lua 模式 dry-run：`valid <n>/<total>`，`invalid <m>`，`warnings <w>`
  - 自动清理 invalid：`removed <r>`（S2b；无 invalid 则为 0）
  - 蓝图模式（每个新绑蓝图）：`comment_present` / `comment_written`

**未执行 / 跳过**：[若有；**禁止**在未执行 S2 的情况下写「绑定完成」]

**建议后续**：[如需 SVN 提交范围、需在 UE 内人工检查项]
```

---

## UMG 创建与编辑专章

本节适用于创建/修改 Widget Blueprint 视觉结构与布局。操作前仍须遵守阶段 2 确认门控。

### 必填输入

创建或覆盖 UI 前，向用户确认以下值；缺失时先提问，仅在用户明确接受默认值或跟进后仍不补充时才使用默认：


| 项     | 说明                           | 默认值（仅 fallback）              |
| ----- | ---------------------------- | ---------------------------- |
| 资产包路径 | 如 `/Game/UI/WBP/Foo/WBP_Foo` | 从需求推导 `/Game/UI/...`         |
| 父类    | Widget Blueprint 父类          | `/Script/UMG.UserWidget`     |
| 根控件   | 名称 / 类                       | `RootCanvas` / `CanvasPanel` |
| 设计分辨率 | 目标分辨率                        | `1920x1080`                  |
| 同名覆盖  | 是否允许覆盖                       | 不删除；load 或 create            |
| 交互控件  | 是否需要可点击                      | 需要时用真实 `Button` / `CheckBox` |
| 逻辑绑定  | UnLua / 蓝图事件                 | 默认仅视觉结构                      |


### UMG 工作流

1. 确认资产路径与父类（缺失时先问用户）。
2. 不确定控件类或属性语义时，先调 `umg_get_supported_capabilities`。
3. `umg_create_blueprint` 创建壳，随即 `umg_compile_save` 落盘空资产。
4. 用 `umg_batch` 分批添加控件，每批约 10–20 步。**添加控件前按 `ui-comwidgets-standards` 选型**：叶子控件（文本/按钮/列表/按键提示/输入框等）优先用项目封装类型（`EM*` / `WBP_Com_*`），容器/布局用原生；`widget_class` 取目录中的标准类型。
5. 大界面在背景、容器、内容、控件、打磨各阶段后分别保存。
6. 结束：`umg_get_tree` → `umg_compile_save` → 检查 `Content/.../*.uasset` 存在。

### UMG 规则

- 成功修改的 UMG 写操作默认**自动编译并落盘**（`compile_save=true`）；编译失败则不保存并返回编译错误。传 `compile_save=false` 可仅标脏内存。
- `umg_batch` 仍在其末尾统一编译保存，内部子步骤不逐步保存。
- Canvas 布局：设 `CanvasPanelSlot.LayoutData` 整体；不要单独设 `Anchors` / `Offsets` 字段。
- **屏幕居中**：`Anchors=(0.5,0.5)`、`Alignment=(0.5,0.5)`，且 **位置 Offsets 默认 `(Left=0, Top=0, Right=0, Bottom=0)`**；尺寸通过控件自身属性（如 Image 的 `Brush.ImageSize`）设置，不要用负 Offsets 做居中。
- **Image 控件**：Slot 上一般还需开启 **Size To Content**（MCP 反射属性名 `bAutoSize=true`），让 Slot 随 Brush 尺寸自适应。
- 优先 `Overlay`、`CanvasPanel`、`HorizontalBox`、`VerticalBox` 分层，避免 Root 下挂过多直接子节点。
- 由父控件决定 slot 类型；`slot_type` 作兼容元数据即可。
- 项目自定义控件短名失败时，用完整类路径，如 `/Script/EM.EMCustomCheckBox`。
- 纯视觉占位可用 `Image` / `Border` / `TextBlock`；预期可交互时用真实控件。

### UMG 验收

- `umg_get_tree` 显示预期层级
- `umg_compile_save` 返回 `saved: true` 且无编译错误
- 磁盘上对应 `.uasset` 存在
- 不支持的类或属性回退已明确说明

---

## 与其他方案的选择


| 场景                              | 推荐                           |
| ------------------------------- | ---------------------------- |
| 快速在线读控件树、绑 UnLua                | **Unreal MCP**（本 skill）      |
| 离线完整蓝图分析（含 slot/anchor 细节 JSON） | `ue-blueprint-analyzer`（T3D） |
| 离线执行流/变量追踪文本导出                  | `ue-mastermind-export`       |


用户未指定时，**信息获取**优先 MCP 摘要（快）；需要离线深度分析时再建议 T3D/Mastermind，并说明需用户选择。

---

## 快速决策

```
用户请求
  ├─ 只查看/分析？ → 阶段 1 递进获取 → 每层结束询问是否深入
  └─ 要创建/修改/绑定？ → 阶段 2 输出方案 → 等待明确确认 → 阶段 3 执行 → UMG 专章规则
```

