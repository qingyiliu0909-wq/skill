---
name: BlueprintExport-Commandlet
description: 通过 EMEditor 内置的 BlueprintExport Commandlet，把任意 UE 蓝图（含 UMG Widget 蓝图）导出为单个结构化 JSON，供其他工具做信息检查。当用户要"用 Commandlet 导出蓝图为 JSON""导出某个 WBP/蓝图的控件树/动画/类默认值""分析 UMG 控件节点信息"、或需要直读内存而非 T3D 文本解析的蓝图数据时使用。
---

# BlueprintExport Commandlet 导出蓝图为 JSON

用 EMEditor 的 `BlueprintExport` Commandlet 直接读取编辑器内存中的 `UBlueprint` 对象，导出为单个 JSON。相比 T3D 文本解析方案，字段更权威、类型更准确，一步出整包。

支持普通蓝图、**Widget 蓝图(WBP)**、动画蓝图等所有 `UBlueprint` 子类。

## 配置项

路径从 `{SKILLS_ROOT}/CONFIG.md` 读取（派生变量）：

| 变量 | 说明 |
|------|------|
| `{UE4_EDITOR_CMD}` | `UE4Editor-Cmd.exe` 路径 |
| `{UPROJECT_PATH}` | `EM.uproject` 路径 |
| `{EM_ROOT}` | 项目根，默认输出目录在 `{EM_ROOT}\Saved\BlueprintExport` |

## 命令格式

```powershell
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport -Path="<蓝图资产路径>" [-Output="<输出目录>"] [-Indent=true] -stdout -unattended -nopause -nosplash
```

> ⚠️ 必须带 `-stdout -unattended -nopause -nosplash`，否则终端无日志输出、且可能卡在交互弹窗。

**支持批量导出**：一次进程可导多个蓝图，启动开销（冷启动 3~5 分钟）只付一次，被所有导出任务复用（导出本身仅毫秒~几秒，慢的是编辑器启动）。路径来源三选一或叠加。

### 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `-Path` | 路径三选一 | **完整引擎内资产路径**（`/Game/...`，不是磁盘路径）。**支持逗号分隔多路径** `-Path="/Game/A,/Game/B"`；单路径即 N=1。缺 `/Game` 会自动补、`_C` 后缀会自动去，但**必须给到完整目录路径**——只给裸名（如 `BP_Foo`）或写错目录会明确报 `Blueprint not found`，不会去猜别处的同名蓝图 |
| `-PathList` | 路径三选一 | 文本清单文件路径，每行一个完整 `/Game/...`；空行与 `#` 开头行忽略。适合路径多、命令行过长时 |
| `-Dir` | 路径三选一 | 资产目录（`/Game/...`），扫描其下所有蓝图（含 Widget/Anim 等 `UBlueprint` 子类）。配合 `-Recursive` 递归子目录。目录拼错/无蓝图会记为 `[BAD SOURCE]` 并令退出码非 0 |
| `-Recursive` | 否 | 无值开关，仅对 `-Dir` 生效；不带则只扫 `-Dir` 当层 |
| `-Output` | 否 | 输出目录，默认 `{EM_ROOT}\Saved\BlueprintExport`。文件命名见下方「输出文件命名规则」 |
| `-Indent` | 否 | `true` 美化 / `false` 紧凑，默认 `true` |

> `-Path` / `-PathList` / `-Dir` 至少提供一个，可叠加使用（结果按规范包名去重合并，大小写无关）。批量导出单个失败不中断整批，末尾汇总 `success X / failed Y / total Z (bad sources: N)` 并逐条列出 `[FAILED]` 路径与 `[BAD SOURCE]` 无效来源；全部成功且无无效来源退出码 `0`，否则 `1`。

### 输出文件命名规则

**扁平命名**：每个蓝图输出到 `<输出目录>/<蓝图名>.json`（如 `BP_Battle` → `<输出目录>/BP_Battle.json`），全部平铺在输出目录、便于查找。

- **不区分同名蓝图**：不同目录的同名蓝图会落到同一文件、后者覆盖前者。本工具用于工具链少量导出，基本不遇同名、更不会同时导出同名，故不做区分。**确需同时导出同名蓝图**，分批用不同 `-Output` 目录。
- **定位输出**：读导出日志 `Successfully exported blueprint: <PackageName> -> <文件>`，或直接取 `<输出目录>/<蓝图名>.json`。

## 执行流程

```
- [ ] Step 1: 从 CONFIG.md 读取 {UE4_EDITOR_CMD} / {UPROJECT_PATH}
- [ ] Step 2: 确认目标蓝图的 /Game 资产路径存在
- [ ] Step 3: 执行命令(冷启动约 3~5 分钟，热启动约 1 分钟)
- [ ] Step 4: 校验退出码 + 日志
- [ ] Step 5: 读取输出 JSON
```

**Step 3 注意**：Commandlet 需加载工程资源，耗时较长，终端可能提前返回，需等 JSON 真正生成。

**Step 4 判定**（看日志关键行）：
- 成功：退出码 `0`，每个蓝图一行 `Successfully exported blueprint: <PackageName> -> <输出文件>`（据此定位实际输出文件）
- 部分失败：退出码 `1`，末尾汇总 `success X / failed Y / total Z (bad sources: N)`，逐条 `[FAILED] <路径>`（加载/导出失败）与 `[BAD SOURCE] <来源>`（如拼错的 `-Dir`）
- 资产不存在：日志 `Blueprint not found at exact path: <Path>` → 检查 `-Path` 是否为真实完整 `/Game` 资产路径（不支持裸名/写错目录）
- 退出码 `3` / `Critical error` / `Assertion failed` → 崩溃，读日志 `[Callstack]` 定位

## 输出 JSON 结构（version 2.1）

单文件，根节点首个字段为 **`_schema`**（结构说明区块，键=区块路径、值=对应内容说明，位于文件最上方，按蓝图类型动态——Widget 额外含 `widgetTree`/`animations` 说明；解析时可忽略此字段），随后是 `version` / `exportTime` / `sourceHash` / `assetType` / `description` / `blueprint`。`blueprint` 通用字段：`path`、`name`、`packageName`、`parentClass`、`blueprintType`、`implementedInterfaces`、`variables`、`components`、`graphs`、`events`、`comments`、`classDefaults`。

**2.1 相对 2.0 为纯增量**（旧字段全保留，旧消费者不受影响），新增一批稳定标识/指纹字段：

| 字段 | 位置 | 用途 |
|------|------|------|
| `sourceHash` | 根级 | 目标 `.uasset` 文件内容 MD5 指纹（变更检测用，非安全用途）；未保存的新资产不出现 |
| `packageName` | `blueprint` | 包长名 `/Game/.../BP_xxx` |
| `guid` | graph / node / variable | 稳定 GUID，供按 GUID 精确定位（不依赖会漂移的数组下标/本地化标题） |
| `classPath` / `position` | node | 节点 UClass 路径与画布落位 `{x,y}` |
| `semantic` | node（仅 CallFunction） | `{kind, functionName, ownerClass}`，稳定标识“调的是哪个函数” |
| `id` | pin | Pin 的稳定 PinId |
| `fromNodeGuid`/`fromPinId`/`toNodeGuid`/`toPinId` | connection | 连线的稳定 GUID 引用（旧 `fromNode`/`toNode` 数组下标保留兼容阅读，定位优先用 GUID） |

**Widget 蓝图额外包含 `widgetTree` 与 `animations`：**

```json
{
  "version": "2.1",
  "assetType": "WidgetBlueprint",
  "blueprint": {
    "blueprintType": "Widget",
    "widgetTree": {
      "totalWidgets": 11,
      "root": {
        "name": "Root",
        "widgetClass": "CanvasPanel",
        "isVariable": false,
        "slot": { "type": "CanvasPanelSlot", "properties": { } },
        "properties": { },
        "text": "龙卷风",
        "entryWidgetClass": "...",
        "children": [ ]
      }
    },
    "animations": {
      "totalAnimations": 1,
      "items": [
        { "name": "In", "startTime": 0.0, "endTime": 0.5, "length": 0.5,
          "tracks": [
            { "boundWidget": "Img_Bg", "trackType": "MovieSceneFloatTrack", "property": "RenderOpacity",
              "sections": [
                { "startTime": 0.0, "endTime": 0.5,
                  "channels": [
                    { "name": "Translation.X", "keys": [ { "time": 0.0, "value": 0.0, "interp": "Cubic" } ] }
                  ] }
              ] }
          ],
          "events": [ { "eventName": "...", "triggerTime": 0.5 } ] }
      ]
    },
    "classDefaults": {
      "generatedClass": "..._C",
      "overriddenDefaults": { }
    }
  }
}
```

### 字段速查

| 需求 | 字段路径 |
|------|----------|
| 控件层级 | `blueprint.widgetTree.root.children[]` |
| 控件类型 | `widgetTree...widgetClass`（`WBP_` 开头=嵌套子蓝图引用） |
| 是否暴露为变量 | `widgetTree...isVariable` |
| 控件被改属性 | `widgetTree...properties`（只含相对原型被覆盖的项） |
| 文本控件文案 | `widgetTree...text` |
| List/Tile 条目类 | `widgetTree...entryWidgetClass` |
| 布局/Slot | `widgetTree...slot.properties` |
| 动画列表/时长 | `blueprint.animations.items[].name` / `.length` |
| 动画轨道 | `animations.items[].tracks[].boundWidget` / `.property` |
| 轨道关键帧 | `tracks[].sections[].channels[].keys[]`（`time` 秒 / `value` / `interp`） |
| 动画事件触发时间 | `animations.items[].events[].triggerTime` |
| 类默认设置 | `blueprint.classDefaults.overriddenDefaults` |

## 解析输出 JSON（消费流程）

拿到 JSON 后按此流程提取信息：

```
- [ ] Step 1: 读文件(Read / jq / python json.load)
- [ ] Step 2: 看 root.assetType 与 blueprint.blueprintType 判断类型并分流
- [ ] Step 3: 按需求定位对应区块(见上方"字段速查")
- [ ] Step 4: widgetTree 需递归遍历 children 提取目标控件
- [ ] Step 5: 结合"解析约定"正确理解缺失字段/特殊值
```

**Step 2 分流**：
- `blueprintType == "Widget"` → 有 `widgetTree` / `animations`；做 UI 控件/动画分析。
- 其它（`Normal`/`Interface`/...）→ 无 `widgetTree`；看 `variables` / `graphs` / `components`。

**Step 4 递归遍历控件树**（伪代码）：

```python
def walk(node, depth=0):
    print("  "*depth, node["name"], node["widgetClass"], "var" if node["isVariable"] else "")
    for child in node.get("children", []):
        walk(child, depth+1)

walk(data["blueprint"]["widgetTree"]["root"])
```

常见解析任务：

| 任务 | 解析做法 |
|------|----------|
| 列出所有可绑定控件(变量) | 遍历 `widgetTree`，收集 `isVariable == true` 的 `name` |
| 找某类型控件 | 遍历 `widgetTree`，筛 `widgetClass == "TextBlock"` 等 |
| 列出嵌套子蓝图依赖 | 遍历 `widgetTree`，收集 `widgetClass` 以 `WBP_`/`_C` 结尾的项 |
| 提取所有文案 | 遍历 `widgetTree`，取存在的 `text` 字段 |
| 动画时长/轨道 | 读 `animations.items[]` 的 `length` 与 `tracks[].boundWidget`/`property` |
| 某轨道关键帧曲线 | 读 `tracks[].sections[].channels[].keys[]`（`time`/`value`/`interp`）；2DTransform 通道按 `name`(Translation.X/Y、Angle、Scale.X/Y) 区分 |
| 蓝图逻辑链路 | 用 `graphs[].connections`（`fromNode`/`toNode` 是 `nodes[].id`）还原节点连线 |
| 绑定的 Lua 模块 | 在 `graphs` 中找 `GetModuleName` 的 `K2Node_FunctionResult` 的 `ReturnValue` 默认值 |

### 解析约定（重要）

- **缺失即默认**：`properties` / `overriddenDefaults` 只含「被覆盖」的项；某属性不出现 = 用父类/原型默认值，不代表没有该属性。
- **`children` 缺失**：非容器控件(非 `UPanelWidget`)没有 `children` 字段；判断时用 `node.get("children", [])`。
- **`classDefaults` 中值为 `"None"`**：多为 BindWidget 控件变量，运行时绑定，CDO 阶段为空，属正常。
- **`widgetTree` 仅本蓝图自身树**：嵌套子蓝图(如 `WBP_Com_Bg_Dialog_C`)只给出类名，其内部控件需对该子蓝图**单独导出**。
- **节点连线**：`connections[].fromNode/toNode` 引用同一 graph 内 `nodes[].id`（数组下标），跨 graph 不连。
- **关键帧仅 float 通道**：`channels` 只导出基于浮点曲线的通道（RenderOpacity、2DTransform 的 Translation/Angle/Scale 等）；事件轨/材质轨等非 float 通道无 `keys`，事件时间见 `events[].triggerTime`。
- **单通道名为 `"None"`**：如 `RenderOpacity` 这类单通道轨道，通道 `name` 可能是 `"None"`（无具名元数据），以所在 track 的 `property` 为准即可。

## 关键设计

- **差异属性导出**：控件属性与类默认值只导出「相对原型/父类 CDO 被覆盖」的项，控制体积与噪声。
- **噪声过滤**：`IsPropertyFiltered` 集中维护过滤名单（默认屏蔽 `Slot`/`Slots`/`Parent`/`Content`/`bExpandedInDesigner`/`DisplayLabel`）。如需在导出中「打开」某字段，删除/注释名单对应行后重编译即可。

## 源码与重新编译

- Commandlet 实现：`Source/EMEditor/Private/Commandlet/BlueprintExportCommandlet.cpp`（头文件在 `Source/EMEditor/Public/Commandlet/`）。
- 改完 C++ 需重新构建 `EMEditor` 目标（按 `ue-build-debug` skill）：

```powershell
& "{UE_ROOT}\Engine\Build\BatchFiles\Build.bat" EMEditor Win64 Development "{UPROJECT_PATH}" -waitmutex
```

构建成功标志：`Rebuild All: 1 succeeded, 0 failed`。

## 示例

导出 UMG 弹窗到默认目录：

```powershell
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport -Path="/Game/UI/WBP/Common/Dialog/WBP_Com_Dialog" -stdout -unattended -nopause -nosplash
```

→ 输出 `{EM_ROOT}\Saved\BlueprintExport\WBP_Com_Dialog.json`

批量：逗号分隔多路径

```powershell
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport `
  -Path="/Game/BluePrints/Combat/BP_Battle,/Game/BluePrints/Common/Level/BP_Arrow" `
  -stdout -unattended -nopause -nosplash
```

批量：从清单文件（每行一个 `/Game/...`）

```powershell
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport `
  -PathList="{EM_ROOT}\Saved\bp_list.txt" `
  -stdout -unattended -nopause -nosplash
```

批量：按目录递归扫描

```powershell
& "{UE4_EDITOR_CMD}" "{UPROJECT_PATH}" -run=BlueprintExport `
  -Dir="/Game/BluePrints/Combat/PassiveEffect/DesignerBP/Player" -Recursive `
  -stdout -unattended -nopause -nosplash
```
