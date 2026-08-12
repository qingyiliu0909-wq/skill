---
name: umap-analyzer
description: 分析 Unreal Engine .umap（关卡地图）二进制文件。当用户上传或引用 .umap 文件，并希望检查对象属性（如 Actor 的 Transform（位置、旋转、缩放）、自定义 Blueprint 属性、组件配置或任何带标签的 UProperty 数据）时，使用此 Skill。该 Skill 解析原始二进制 Package 格式，提取 Export 对象，并将其转换为 JSON/CSV 进行结构化分析——无需 Unreal Editor。当用户提及 ".umap"、"关卡文件"、"UE 地图分析"、"actor transforms"、"地图对象检查" 或请求 "将地图数据导出为 CSV" 时触发。
---

# UMap Analyzer Skill

使用纯 Python（无外部依赖）解析和分析 Unreal Engine `.umap` 二进制文件。
提取 Actor 属性——包括 Transform、自定义 Blueprint 变量和组件数据——并将其导出为结构化的 JSON 或 CSV。

---

## 目录结构

```
umap-analyzer/
├── SKILL.md                      ← 本文件
├── scripts/
│   ├── umap_parser.py            ← 核心二进制解析器（UE Package 格式）
│   ├── umap_to_csv.py            ← 导出流水线：.umap → JSON → CSV
│   └── analyze_actors.py         ← 查询/筛选特定 Actor 属性
└── references/
    └── ue_package_format.md      ← UE 二进制格式参考（调试时阅读）
```

---

## 工作流程

### 第一步 — 理解需求

询问用户：
- 需要关注哪些 **Actor 类型或类**？（例如 `StaticMeshActor`、`BP_MyObject`）
- 需要提取哪些 **属性**？（Transform 始终包含；自定义属性请按名称列出）
- 输出格式：**JSON**（完整保真）还是 **CSV**（扁平表格，便于对比排序）？
- UE 版本？（UE4 与 UE5 的头部格式不同；UE5 使用 `LegacyFileVersion == -8`）

如果用户只说"分析这个 .umap"，则默认为：**所有 Actor，仅提取 Transform，CSV 输出**。

### 第二步 — 解析 .umap 文件

对上传的文件运行 `scripts/umap_parser.py`：

```bash
# 使用项目自带的 Python 解释器
& "ExportDatas/tools/py37/py37.exe" scripts/umap_parser.py <input.umap> --output actors.json

# 或使用系统 Python（如果可用）
python3 scripts/umap_parser.py <input.umap> --output actors.json
```

此步骤将生成一个包含所有 Export 对象及其属性的 JSON 数组。

### 第三步 — 转换为 CSV（可选，但推荐）

```bash
python3 scripts/umap_to_csv.py actors.json --output actors.csv \
    --props Transform,MyCustomProp,AnotherProp
```

### 第四步 — 分析并回应

加载 JSON/CSV，回答用户的具体问题：
- 按类汇总 Actor 数量
- 显示特定 Actor 的 Transform
- 标出异常值（Scale 为零、旋转为 NaN 等）
- 若提供两个文件，则对比两个地图的差异

---

## 关键技术说明

### UE Package 二进制格式

`.umap` 格式与 `.uasset` 完全相同——两者都是 **Unreal Package 文件**：

```
[PackageFileSummary]   ← 头部：版本号、各表偏移量、数量
[NameTable]            ← 本包中使用的所有 FName 字符串
[ImportTable]          ← 对外部包/对象的引用
[ExportTable]          ← 本包导出的每个对象的元数据
[ExportPayload]        ← 每个 Export 对象实际序列化的属性数据
```

**魔数：** `0x9E2A83C1`（文件偏移 0 处的小端序 uint32）

**版本检测：**
- `LegacyFileVersion == -6`：UE4（自定义版本引入前）
- `LegacyFileVersion == -7`：UE4（含自定义版本数组）
- `LegacyFileVersion == -8`：UE5（新增 `FileVersionUE5` 字段）

### FProperty 标签格式

Export Payload 中的属性以带标签的列表形式存储：

```
loop:
  PropertyName  (FName)      ← "None" = 属性列表结束
  PropertyType  (FName)      ← "StructProperty"、"FloatProperty" 等
  PropertySize  (int32)      ← 值的字节大小
  ArrayIndex    (int32)      ← 非数组时为 0

  [类型特定的额外头部字段（仅当 Type.GetNumber() == 0 时）：]
    StructProperty:  FName StructName + FGuid StructGuid (ver>=441)
    BoolProperty:    uint8 BoolVal  ← 值存在 Tag 头中！PropertySize=0
    ByteProperty:    FName EnumName
    EnumProperty:    FName EnumName
    ArrayProperty:   FName InnerType (ver>=282)
    SetProperty:     FName InnerType (ver>=509)
    MapProperty:     FName InnerType + FName ValueType (ver>=509)

  uint8 HasPropertyGuid (ver>=503)
  [若 HasPropertyGuid == 1，则有 16 字节 PropertyGuid]

  Value bytes (PropertySize bytes)  ← BoolProperty 无值数据！
```

### Transform 结构

数据存储于 `RootComponent.RelativeLocation/Rotation/Scale3D`，或直接作为 `ActorTransform`：

```
FTransform {
    Rotation:  FQuat   → 4 × float  (X, Y, Z, W)
    Translation: FVector → 3 × float
    Scale3D:   FVector → 3 × float
}
```

在带标签的属性形式中，可能看到：
- `RelativeLocation`（StructProperty → Vector）：3 个 float
- `RelativeRotation`（StructProperty → Rotator）：Pitch、Yaw、Roll 三个 float
- `RelativeScale3D`（StructProperty → Vector）：3 个 float

---

## ⚠️ UE4.27 版本踩坑总结

以下问题在 EM 项目（UE4.27, FileVersionUE4=522）中实际遇到并修复，后续使用时务必注意：

### 坑1：Import 表缺少 PackageName 字段

**现象**：Import 表解析后名称全部偏移，显示为 WorldGridMaterial 等错误名称。

**原因**：UE4.27 (FileVersionUE4=522 >= 519) 的 Import 表在 `ObjectName` 之后新增了 `PackageName` (FName) 字段。这是 `VER_UE4_NON_OUTER_PACKAGE_IMPORT = 519` 引入的。

**修复**：当 `FileVersionUE4 >= 519` 时，Import 表每条记录末尾多读一个 FName。

### 坑2：Export 表 TemplateIndex 版本号错误

**现象**：Export 表偏移错误，后续所有记录解析失败。

**原因**：旧版本文档记录 `TemplateIndex` 在 `ver >= 508` 时存在，但实际源码中是 `VER_UE4_TemplateIndex_IN_COOKED_EXPORTS = 507`。

**修复**：TemplateIndex 在 `FileVersionUE4 >= 507` 时存在。

### 坑3：Export 表 PackageGuid 始终存在

**现象**：Export 表偏移错误。

**原因**：旧版本文档记录 PackageGuid 在 `ver < 511` 时存在，之后移除。但实际源码中 PackageGuid 是 `FGuid`，虽然标记为废弃但**始终序列化**（16字节），不存在版本条件移除。

**修复**：PackageGuid (16 bytes) 在所有 UE4 版本中始终存在，无条件读取。

### 坑4：FPropertyTag 中 BoolProperty 值在 Tag 头中

**现象**：BoolProperty 解析后值错误，且后续属性偏移错位。

**原因**：BoolProperty 的值（1字节 BoolVal）存储在 Tag 头部中，**不在值数据区域**。PropertySize 为 0，不需要读取值数据。

**修复**：BoolProperty 在 Tag 头中读取 1 字节 BoolVal，值数据区域为 0 字节。

### 坑5：FPropertyTag 中 StructProperty 没有 HasSerializeMetaData

**现象**：所有属性值解析错误，出现 1.8e-38 等极小值或 -2.4e+29 等极大值。

**原因**：旧版本文档记录 StructProperty 在 StructGuid 之后有 1 字节 `HasSerializeMetaData` 标志。但实际 UE4.27 源码中**不存在此字段**，这是 UE5 才引入的。

**修复**：UE4 中 StructProperty 的额外头部仅为 `FName StructName + FGuid StructGuid (ver>=441)`，没有 HasSerializeMetaData。

### 坑6：类名解析 — Import 的 class_name 为 "Class" 时

**现象**：所有 Export 的 class_name 显示为 "Class" 而非实际类名。

**原因**：当 Export 的 class_index 指向一个 Import 条目，且该 Import 的 class_name 为 "Class" 时，说明该 Import 是一个 UClass 元类引用。此时实际的对象类名应该取 Import 的 `object_name`（如 "NavMeshBoundsVolume"、"Brush" 等），而非 class_name ("Class")。

**修复**：在 `resolve_class_name` 中，当 Import 的 class_name == "Class" 时，返回 Import 的 object_name。

### 坑7：Export 表 FirstExportDependency 是 int32 不是 int64

**现象**：Export 表偏移错误，后续所有记录解析失败，SerialSize 出现极大值。

**原因**：`FirstExportDependency` 字段类型在头文件中声明为 `int32`，但某些文档和实现错误地将其当作 `int64` 读取。多读 4 字节会导致后续 Export 记录全部偏移。

**修复**：`FirstExportDependency` 读取为 int32（4字节），不是 int64（8字节）。

### 坑8：Export 表 PackageFlags 是无条件序列化的

**现象**：Export 表偏移错误。

**原因**：某些文档记录 `PackageFlags` 仅在 `ver >= 322` 时序列化。但实际引擎源码中 `PackageFlags` 紧跟 `PackageGuid` 之后，**无条件序列化**，没有版本号条件。

**修复**：`PackageFlags` (uint32) 无条件读取，不需要版本号判断。

---

## 边缘情况处理

| 情况 | 处理方式 |
|---|---|
| 文件不以 `0x9E2A83C1` 开头 | 报错：不是有效的 UE Package 文件 |
| `LegacyFileVersion < -8` | 警告：更新的 UE5.x 格式，部分解析可能仍可工作 |
| Export 没有属性 | 该 Export 在 CSV 中出现，但属性列为空 |
| 压缩包 | 使用 `--decompress` 参数；注意：使用 zlib 压缩 |
| 设置了 `bFilterEditorOnly` 标志 | 部分仅编辑器使用的属性在打包（Cook）时会被剥离 |
| 属性值出现极小/极大浮点数 | 说明 FPropertyTag 解析偏移有误，检查坑4/坑5 |
| 类名全部显示为 "Class" | 检查类名解析逻辑，参考坑6 |
| Export 表偏移错误 | 检查坑2/坑3/坑7/坑8，对照源码验证字段类型和版本号 |
| SerialSize 出现极大值 | FirstExportDependency 被错误读取为 int64，参考坑7 |

---

## CSV 输出字段说明

| 列名 | 说明 |
|---|---|
| `ExportIndex` | Export 表中从 0 开始的索引 |
| `ExportName` | 对象名称（来自名称表） |
| `ClassName` | 类名称（通过导入表查找） |
| `OuterName` | 外部对象名称（Package/Level 层级结构） |
| `Loc_X/Y/Z` | 世界坐标位置 |
| `Rot_Pitch/Yaw/Roll` | 旋转角度（单位：度） |
| `Scale_X/Y/Z` | 缩放值 |
| `[CustomProp]` | 每个请求的自定义属性对应一列 |

---

## 脚本快速参考

```bash
# 完整流水线——解析 + CSV 导出
python3 scripts/umap_parser.py MyLevel.umap --output /tmp/actors.json
python3 scripts/umap_to_csv.py /tmp/actors.json --output /tmp/actors.csv

# 按类筛选
python3 scripts/umap_parser.py MyLevel.umap --class StaticMeshActor BP_MyActor

# 按属性筛选
python3 scripts/umap_to_csv.py actors.json --props RelativeLocation,RelativeRotation,MyScore

# 分析结果（打印汇总）
python3 scripts/analyze_actors.py actors.json --summary
python3 scripts/analyze_actors.py actors.json --find-actor "BP_MyActor_0"
```

---

## 何时阅读参考文档

在以下情况下阅读 `references/ue_package_format.md`：
- 调试某个特殊 UE 版本的解析失败问题
- 为新的属性类型添加支持
- Export 表的偏移量看起来不对（版本不匹配）
