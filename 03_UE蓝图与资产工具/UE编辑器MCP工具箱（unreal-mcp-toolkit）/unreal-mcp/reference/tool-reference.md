# Unreal MCP 工具参考

MCP 服务器：`user-unreal_mcp_server`  
调用前务必读取 `mcps/user-unreal_mcp_server/tools/<tool>.json` 获取最新 schema。

> **插件源码位置**（需改 MCP 行为 / 排查实现时用）
> - **C++**：`Plugins/UnrealMCP/Source/UnrealMCP/`（命令实现在 `Private/Commands/`，如 `UnrealMCPUMGCommands.cpp`；公共工具类为各 `*Utils`，如编译落盘 `UMGWidgetUtils.cpp::CompileAndMaybeSave`）
> - **Python（MCP server）**：`Plugins/UnrealMCP/Python/`（入口 `unreal_mcp_server.py`，工具转发在 `tools/*.py`）
> - 改 C++ 需**重新编译插件**才生效；改 Python 重启 MCP server 即可

图例：**R** = 只读（信息获取）　**W** = 写操作（须用户确认）　**R/W\*** = 视参数而定，默认参数会写文件、另有纯只读用法（须用户确认，见该行说明）

---

## 蓝图读取与编辑

| 工具 | 类型 | 说明 |
|------|------|------|
| `read_blueprint` | R | 读蓝图结构。`detail_level`: `summary`（默认）/ `full`；`max_depth` 控制遍历深度 |
| `get_unlua_binding` | R | **仅查 UnLua 绑定**。`blueprint_name` 即可，返回 `status`（`Bound`/`Unbound`/`NoModuleFunction`）、`lua_module_path`、`lua_file_path`、`lua_file_exists_on_disk`、`implements_unlua_interface` 等，无控件树/事件图冗余 |
| `validate_lua_bound_blueprints` | R/W* | 校验 `@BoundBlueprint` 一致性。Lua 模式：`remove_invalid=false` dry-run 后，**bind 流程中若 `invalid_count>0` Agent 须自动再调 `remove_invalid=true` 删 invalid**（不删 warnings）。Blueprint 模式：`auto_complete_comment` 补注释。见 SKILL §2.4 |
| `find_blueprint_nodes` | R | 在事件图中查找节点，可筛 `node_type`、`event_type` |
| `create_blueprint` | W | 创建蓝图类，需 `name`、`parent_class` |
| `compile_blueprint` | W | 编译指定蓝图 |
| `save_blueprint` | W | 蓝图落盘写 `.uasset`。多数改属性工具仅标脏内存，需调它持久化；`compile=true`（默认）先编译再保存 |
| `set_blueprint_property` | W | 设置蓝图 CDO 属性 |
| `get_blueprint_property` | R | 读蓝图 CDO（类默认对象）属性值。需先编译过。传 `property_name` 读单个（返回 `found`/`property_type`/`property_value`）；省略则返回全部可见属性 map（`property_count`/`properties`）。值为反射文本（如向量 `(X=..,Y=..,Z=..)`、布尔 `true`/`false`） |
| `set_blueprint_parent_class` | W | 改已存在蓝图的父类并自动 compile+save，需 `blueprint_name`、`parent_class`（如 `UIState` 或 `/Script/EM.UIState`） |
| `add_component_to_blueprint` | W | 向蓝图添加组件 |
| `set_component_property` | W | 设置组件属性 |
| `set_static_mesh_properties` | W | 设置静态网格属性 |
| `set_physics_properties` | W | 设置物理属性 |
| `add_blueprint_variable` | W | 添加蓝图变量 |
| `rename_blueprint_variable` | W | 重命名蓝图**成员变量**（`NewVariables`），并更新图中 Get/Set 引用。先校验 `old_name` 存在再判幂等：同名且存在 → `renamed=false`；`fail_if_missing=true` 时缺失即报错（含同名）；仅改大小写由 `CompareRenameNames` 拒绝；目标名已存在报错；`fail_if_missing=false` 时缺失不标脏。不自动 save，需 `save_blueprint`。不改 UMG 控件名/动画名 |
| `add_blueprint_event_node` | W | 添加事件节点 |
| `add_blueprint_function_node` | W | 添加函数调用节点 |
| `add_blueprint_input_action_node` | W | 添加输入动作节点 |
| `add_blueprint_self_reference` | W | 添加 Self 引用节点 |
| `add_blueprint_get_self_component_reference` | W | 添加 Get Self Component 引用 |
| `connect_blueprint_nodes` | W | 连接蓝图节点引脚 |
| `bind_blueprint_to_unlua` | W | 绑定 UnLua：编译保存、写入 `@BoundBlueprint`；**不**自动校验。bind 后 Agent 须按 SKILL §2.4 SOP 调用 `validate_lua_bound_blueprints`。`create_lua_file=true` 时从模板生成 `.lua`（已存在则失败） |
| `unbind_blueprint_from_unlua` | W | 解绑 UnLua（`bind` 的逆操作）：`interface` 绑定→移除本蓝图接口及其 GetModuleName 接口图；`override` 绑定→移除覆写的 GetModuleName 函数图（回退父类原生实现）。幂等（无可移除时 `changed=false` 不写盘）；不删除 `.lua` 文件。父类仍实现接口时返回 `inherited_binding_remains=true` |

---

## UMG Widget Blueprint

### 读取

| 工具 | 说明 |
|------|------|
| `umg_find_widget_blueprint` | 查找 Widget 蓝图 |
| `umg_get_tree` | 控件树摘要；ListView/TileView 含 entry 类信息；节点含 `is_variable`（对应设计师 Is Variable） |
| `umg_get_widget_property` | 读取控件本体属性值（ExportText）。传 `property`（如 `Text`/`Font`/`ColorAndOpacity`/`AutoWrapText`/`DefaultTextStyle`）返回单个 `value_text`；不传返回全部非对象控件属性 `properties`（复制样式推荐用此）。值为 ImportText 格式，可回灌 `umg_set_widget_property` |
| `umg_get_slot_property` | 读取控件 Slot 属性值（ExportText）。传 `property`（**顶层**属性名：CanvasPanelSlot 用 `LayoutData`——Anchors/Offsets/Alignment 是其嵌套字段、非顶层属性，另有 `ZOrder`/`bAutoSize`；BoxSlot 用 `Size`/`Padding`/`HorizontalAlignment`/`VerticalAlignment`）返回单个 `value_text`；不传返回全部非对象 Slot 属性 `properties`（复制布局推荐用此）。值为 ImportText 格式，可回灌 `umg_set_slot_property` 复制锚点/位置/尺寸 |
| `umg_get_supported_capabilities` | 支持的控件类与能力 |
| `umg_get_animations` | 动画列表（name、时长等） |
| `umg_get_animation_detail` | 单动画绑定、轨道、同步警告 |
| `umg_get_animation_keys` | 动画关键帧；材质轨支持 `material_source_path` + `material_parameter` |

### 控件材质轨道（Widget Material）

`property` 固定传 `"Brush Material"`（向后兼容）；用 `material_source_path` 区分材质来源：

| material_source_path | 控件类型 | 说明 |
|----------------------|----------|------|
| `Brush`（默认） | Image / Border | 画刷材质 |
| `Font` | TextBlock | 字体材质（如 `Mask_U_Offset`） |
| `Font.OutlineSettings` | TextBlock | 描边材质 |
| 完整嵌套路径 | RichTextBlock 等 | 如 `DefaultTextStyleOverride.Font` |

- 读写已有轨道时，可只传 `material_parameter`，按参数名自动匹配（参数曲线须已有关键帧）
- 同一 binding 多条材质轨时，须显式传 `material_source_path`
- 须 `binding_type='widget'`

### 写入

所有写入工具支持 `compile_save`（默认 `true`）：成功修改后自动编译，编译成功才落盘；编译失败不保存并返回错误。无实际变更的成功响应（如 `existed=true`、`found=false`）跳过保存。`umg_batch` 在末尾统一编译保存。

| 工具 | 说明 |
|------|------|
| `umg_create_blueprint` | 创建/加载 WBP，确保有 RootWidget |
| `umg_add_widget` | 添加控件 |
| `umg_remove_widget` | 删除控件 |
| `umg_reparent_widget` | 重设父节点 |
| `umg_set_widget_property` | 设置控件属性 |
| `umg_set_widget_is_variable` | 设置控件设计师「Is Variable」（`bIsVariable`）；对齐 Details：事务内 Template+Preview 双写（`SyncPreviewWidgetIsVariableFromTemplate`）再 `MarkBlueprintAsStructurallyModified`。取消且图中仍引用该名时默认报错，`force=true` 可强制。幂等 `changed=false` 不落盘。整页 `RefreshPreview` 见 `FUMGWidgetUtils::RefreshOpenWidgetBlueprintEditorPreview`（须在事务外调用） |
| `umg_set_slot_property` | 设置 Slot 属性 |
| `umg_compile_save` | 编译并保存到磁盘 |
| `umg_batch` | 批量操作序列，可选 `compile_save` |
| `create_umg_widget_blueprint` | 旧版创建接口（优先 `umg_create_blueprint`） |
| `add_button_to_widget` | 快捷添加按钮 |
| `add_text_block_to_widget` | 快捷添加文本 |
| `bind_widget_event` | 绑定控件事件 |
| `set_text_block_binding` | 设置 TextBlock 绑定 |
| `add_widget_to_viewport` | 将 Widget 加入视口（运行时/调试） |

### UMG 动画写入

| 工具 | 说明 |
|------|------|
| `umg_add_animation` | 新建动画 |
| `umg_delete_animation` | 删除动画 |
| `umg_rename_animation` | 重命名；幂等（大小写完全相同）；仅改大小写由 `CompareRenameNames` 拒绝 |
| `umg_add_animation_track` | 添加轨道；材质轨传 `material_source_path`（Brush/Font/…） |
| `umg_delete_animation_track` | 删除轨道；材质轨可选 `material_source_path` / `material_parameter` |
| `umg_set_animation_keys` | 设置关键帧；材质轨须 `material_parameter`，可选 `material_source_path` |
| `umg_delete_animation_key` | 删除关键帧；材质轨须 `material_parameter`，可选 `material_source_path` |
| `umg_bind_widget_to_animation` | 控件绑定到动画 |
| `umg_unbind_widget_from_animation` | 解除绑定 |
| `umg_cleanup_zombie_animation_bindings` | 清理无效绑定 |

---

## 关卡与 Actor

| 工具 | 类型 | 说明 |
|------|------|------|
| `get_actors_in_level` | R | 当前关卡全部 Actor |
| `find_actors_by_name` | R | 按名称查找 Actor |
| `get_actor_properties` | R | 读取 Actor 属性 |
| `spawn_actor` | W | 生成 Actor |
| `spawn_blueprint_actor` | W | 生成蓝图 Actor |
| `delete_actor` | W | 删除 Actor |
| `set_actor_property` | W | 设置 Actor 属性 |
| `set_actor_transform` | W | 设置 Transform |

---

## 动画与特效资产读取

| 工具 | 说明 |
|------|------|
| `read_anim_sequence` | 读 AnimSequence |
| `read_anim_montage` | 读 AnimMontage |
| `find_anim_assets_by_suffix` | 按后缀查找动画资产 |
| `analyze_foot_trajectory` | 分析脚部轨迹 |
| `read_niagara_system` | 读 Niagara 系统 |

---

## 编辑器与其他

| 工具 | 类型 | 说明 |
|------|------|------|
| `open_asset` | W* | 在编辑器中打开资产（`asset_path` / `asset_paths` / `operations`） |
| `create_input_mapping` | W | 创建输入映射 |

\* `open_asset` 会改变编辑器 UI 状态，按写操作门控处理。

---

## 路径格式速查

| 场景 | 格式 | 示例 |
|------|------|------|
| 蓝图名参数 | 仅名称 | `WBP_AutoChessMain` |
| UMG asset_path | Content 包路径 | `/Game/UI/WBP/AutoChess/WBP_AutoChessMain` |
| 也接受的 UMG 路径 | UObject / 编辑器复制串 | `WidgetBlueprint'/Game/UI/.../WBP_Foo.WBP_Foo'` |
| UnLua 模块路径 | 点号，相对 Script | `BluePrints.UI.AutoChess.WBP_AutoChessMain_C` |

---

## read_blueprint detail_level 对比

| 级别 | 返回内容 | 适用 |
|------|----------|------|
| `summary` | 父类、组件列表、变量名、函数名 | 默认第一层 |
| `full` | 含事件图节点、引脚连接、UnLua 绑定 | 用户确认深入后 |

> **只需 UnLua 绑定信息时不要用 `full`**：改用 `get_unlua_binding`，输入仅 `blueprint_name`，返回精简的绑定字段，不夹带控件树/事件图。`full` 内的 `UNLUA BINDING` 段与 `get_unlua_binding` 同源（C++ 端 `FUnrealMCPCommonUtils::GetUnLuaBindingInfo`），后者额外暴露 `implements_unlua_interface` 与 `status` 三态。

---

## umg_batch operations 常见 op

调用前读 `umg_batch.json`；常见操作类型包括 `add_widget`、`set_widget_property`、`set_slot_property`、`remove_widget`、`reparent_widget` 等。大批量编辑时 `compile_save: true` 放在 batch 末尾。

---

## Flow 资产工具（另见 `flow-mcp` skill）

同 MCP 服务器 `user-unreal_mcp_server` 上还注册了 **8 个 `flow_*` 只读工具**，用于 FlowAsset / DialogueAsset 的读取、导出与 schema 查询。参数细节、递进披露与写入工具见 **`flow-mcp`** skill（`.skill/对话编辑器/flow-mcp/flow-mcp/`）及其 `reference/tool-reference.md`。

| 工具 | 类型 | 层级 | 说明 |
|------|------|------|------|
| `flow_read_asset_summary` | R | L1 | 资产总览：类型/路径/父类 + 节点数 + 类型分布 + 入口点 |
| `flow_read_nodes` | R | L2 | 节点列表：guid/类型/标题/输入输出 Pin（不含属性）；可选 `type_filter` |
| `flow_read_node_detail` | R | L3 | 单节点属性值 map + Pin；字段说明去 `flow_get_node_schema` 查 |
| `flow_export_asset` | R | — | 整个 FlowAsset 导出为 JSON；可选 `output_path` 写盘 |
| `flow_get_node_types` | R | L1 | 所有 UFlowNode 派生类型（含未加载蓝图） |
| `flow_get_supported_nodes` | R | L2 | 按 `asset_class` 过滤该资产类支持的节点类型 |
| `flow_get_node_schema` | R | L3 | 单个节点类型的扁平式 schema（七元组 fields + structs/enums/classes） |
| `flow_get_asset_schema` | R | L3 | 单个资产类型的扁平式 schema（与 node schema 对称） |

> Flow 域**写入**工具（创建资产、加节点、连线、改属性、`flow_batch` 等）见 `flow-mcp` skill；是否已在当前 MCP server 注册以 `mcps/user-unreal_mcp_server/tools/flow_*.json` 为准。
