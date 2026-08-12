# Unreal Engine Package 格式参考文档

当调试解析失败或为新的属性类型添加支持时，请阅读本文件。

> ⚠️ **重要**：以下版本号均基于 UE4.27 引擎源码验证（`ObjectVersion.h`、`ObjectResource.cpp`、`PropertyTag.cpp`）。
> 如需确认其他 UE 版本的版本号，请查阅对应引擎源码中的 `ObjectVersion.h`。

---

## 文件整体布局

```
Offset  Size  Field
0       4     Magic = 0x9E2A83C1
4       4     LegacyFileVersion (负整数)
8       4     LegacyUE3Version  (仅当 LegacyFileVersion != -4 时存在)
12      4     FileVersionUE4
16      4     FileVersionUE5    (仅当 LegacyFileVersion == -8 时存在)
...          CustomVersions 数组、TotalHeaderSize、FolderName、PackageFlags
...          NameCount + NameOffset
...          ExportCount + ExportOffset
...          ImportCount + ImportOffset
```

## LegacyFileVersion 值含义

| 值 | 含义 |
|-------|---------|
| -2    | 新增自定义版本数组 |
| -3    | 新增地图包标志 |
| -4    | 不含 LegacyUE3Version 字段 |
| -5    | 新增创建前序列化机制 |
| -6    | 新增批量数据偏移 |
| -7    | 将批量数据写入摘要 |
| -8    | **UE5** — 新增 FileVersionUE5 字段 |

## FileVersionUE4 关键版本号

> 以下版本号从 UE4.27 引擎源码 `ObjectVersion.h` 中提取，起始值为 214。

| 版本号 | 常量名 | 新增特性 |
|---------|---------|---------|
| 322     | VER_UE4_ADD_PACKAGEFLAGS_TO_EXPORT | Export 表中新增 PackageFlags |
| 364     | VER_UE4_LOAD_FOR_EDITOR_GAME | bNotAlwaysLoadedForEditorGame 标志 |
| 441     | VER_UE4_STRUCT_GUID_IN_PROPERTY_TAG | StructProperty 新增 StructGuid |
| 459     | VER_UE4_GATHERABLE_TEXT_DATA | 可收集文本数据 |
| 484     | VER_UE4_COOKED_ASSETS_IN_EDITOR_SUPPORT | bIsAsset 标志 |
| 503     | VER_UE4_PROPERTY_GUID_IN_PROPERTY_TAG | FPropertyTag 新增 HasPropertyGuid + PropertyGuid |
| 506     | VER_UE4_PRELOAD_DEPENDENCIES_IN_COOKED_EXPORTS | Export 依赖项 |
| 507     | VER_UE4_TemplateIndex_IN_COOKED_EXPORTS | Export 中新增 TemplateIndex |
| 509     | VER_UE4_PROPERTY_TAG_SET_MAP_SUPPORT | SetProperty/MapProperty 标签支持 |
| 510     | VER_UE4_64BIT_EXPORTMAP_SERIALSIZES | Export 表 SerialSize/Offset 为 int64 |
| 516     | VER_UE4_NAME_HASHES_SERIALIZED | LocalizationId + 新的名称哈希算法 |
| 519     | VER_UE4_NON_OUTER_PACKAGE_IMPORT | Import 表新增 PackageName 字段 |

## FileVersionUE5 关键版本号

| 版本号 | 新增特性 |
|---------|---------|
| 518     | SoftObjectPaths 表 |
| 519     | 大世界坐标（Large World Coordinates，使用 double 精度向量） |
| 522     | 数据资源（Data resources） |

## FName 格式（名称表中）

```
int32  Length     （正数 = UTF-8，负数 = UTF-16 字符数）
byte[] String     （以 null 结尾，UTF-8 时为 abs(Length) 个字节）
uint16 CaseHash   （UE4.26 起新增）
uint16 NonCaseHash
```

## FObjectImport（导入表中每条记录）

```
FName   ClassPackage    （例如 "/Script/Engine"）
FName   ClassName       （例如 "StaticMeshActor"）
int32   OuterIndex      （负数 = 导入项，正数 = 导出项，0 = 包本身）
FName   ObjectName      （例如 "BP_MyActor"）
FName   PackageName     （仅 FileVersionUE4 >= 519 时存在，VER_UE4_NON_OUTER_PACKAGE_IMPORT）
```

> ⚠️ **踩坑记录**：`PackageName` 字段在 UE4.27 (FileVersionUE4=522) 中存在。如果遗漏此字段，
> Import 表解析将全部偏移，导致后续 Export 表的类名解析错误。

## FObjectExport（导出表中每条记录）

```
int32   ClassIndex         （负数 = 导入项，0 = UClass）
int32   SuperIndex
int32   TemplateIndex      （FileVersionUE4 >= 507 时存在）
int32   OuterIndex
FName   ObjectName
uint32  SaveFlags
int64   SerialSize         （FileVersionUE4 >= 510 时为 int64，否则 int32）
int64   SerialOffset       （FileVersionUE4 >= 510 时为 int64，否则 int32）
int32   bForcedExport      （bool 序列化为 uint32，4字节）
int32   bNotForClient      （bool 序列化为 uint32，4字节）
int32   bNotForServer      （bool 序列化为 uint32，4字节）
FGuid   PackageGuid        （⚠️ 始终存在！16字节，虽已废弃但仍序列化）
uint32  PackageFlags       （⚠️ 始终序列化！无条件存在，不受版本号控制）
int32   bNotAlwaysLoadedForEditorGame  （>= 364 时存在，bool 序列化为 uint32）
int32   bIsAsset           （>= 484 时存在，bool 序列化为 uint32）
int32   FirstExportDependency  （⚠️ int32 不是 int64！>= 506 时存在）
int32   SerializationBeforeSerializationDependencies
int32   CreateBeforeSerializationDependencies
int32   SerializationBeforeCreateDependencies
int32   CreateBeforeCreateDependencies
```

> ⚠️ **踩坑记录**：
> 1. `TemplateIndex` 的版本号是 **507**（`VER_UE4_TemplateIndex_IN_COOKED_EXPORTS`），
>    不是某些文档记录的 508。
> 2. `PackageGuid` (FGuid, 16字节) **始终序列化**，不存在版本条件移除。
>    某些文档记录在 ver >= 511 时移除是错误的。
> 3. `PackageFlags` (uint32) **始终序列化**，没有版本号条件。
>    某些文档记录仅在 ver >= 322 时存在是错误的。
> 4. `FirstExportDependency` 是 **int32**（4字节），不是 int64（8字节）。
>    错误地读取为 int64 会导致后续所有 Export 记录偏移。
> 5. `bForcedExport`、`bNotForClient`、`bNotForServer`、`bNotAlwaysLoadedForEditorGame`、
>    `bIsAsset` 都是 bool 类型，但通过 `FArchive::SerializeBool` 序列化为 **uint32**（4字节），
>    不是 1 字节。

## FProperty 标签序列化格式

Export Payload 中每个属性的结构如下：

```
FName   PropertyName       （"None" 表示属性列表结束）
FName   PropertyType       （例如 "FloatProperty"、"StructProperty"）
int32   PropertySize       （值的字节数，BoolProperty 时为 0）
int32   ArrayIndex         （标量类型为 0）

[各类型的额外头部字段（仅当 PropertyType.GetNumber() == 0 时读取）：]
  StructProperty:   FName StructName
                    FGuid StructGuid (16字节, 仅 FileVersionUE4 >= 441)
  BoolProperty:     uint8 BoolVal    ← ⚠️ 值存在 Tag 头中！PropertySize=0
  ByteProperty:     FName EnumTypeName（原始字节时为 "None"）
  EnumProperty:     FName EnumTypeName
  ArrayProperty:    FName InnerType (仅 FileVersionUE4 >= 282)
  SetProperty:      FName InnerType (仅 FileVersionUE4 >= 509)
  MapProperty:      FName KeyType + FName ValueType (仅 FileVersionUE4 >= 509)

uint8   HasPropertyGuid    （仅 FileVersionUE4 >= 503 时存在）
[若 HasPropertyGuid == 1，则有 16 字节 PropertyGuid]

[值数据：PropertySize 字节]
  BoolProperty 无值数据！
  其他类型按 PropertySize 字节读取
```

> ⚠️ **踩坑记录**：
> 1. **BoolProperty** 的值（1字节 BoolVal）存储在 Tag 头部中，**不在值数据区域**。
>    PropertySize 为 0，读取值数据时跳过。如果错误地从值数据区域读取 1 字节，
>    会导致后续所有属性偏移错位。
> 2. **StructProperty** 在 UE4 中**没有** `HasSerializeMetaData` 字段！
>    这是 UE5 才引入的。UE4 的 StructProperty 额外头部仅为
>    `FName StructName + FGuid StructGuid (ver>=441)`。
>    如果错误地多读 1 字节 HasSerializeMetaData，会导致所有属性值解析错误
>    （出现 1.8e-38 等极小浮点值）。

## 类名解析规则

当通过 Export 的 `ClassIndex` 查找类名时：

| ClassIndex 值 | 含义 | 类名来源 |
|---|---|---|
| 0 | UClass | 返回 "UClass" |
| < 0 (指向 Import) | Import 的 class_name == "Class" | 返回 Import 的 **object_name**（实际类名） |
| < 0 (指向 Import) | Import 的 class_name != "Class" | 返回 Import 的 class_name |
| > 0 (指向 Export) | — | 返回 Export 的 object_name |

> ⚠️ **踩坑记录**：当 Import 的 class_name 为 "Class" 时，说明该 Import 是一个 UClass 元类引用。
> 此时实际的对象类名应该取 Import 的 `object_name`（如 "NavMeshBoundsVolume"、"Brush" 等），
> 而非 class_name ("Class")。否则所有 Export 的类名都会显示为 "Class"。

## 常见结构体内存布局

### FVector（UE4 / 未启用大世界坐标）
```
float X, float Y, float Z   → 12 字节
```

### FVector（UE5 启用大世界坐标，FileVersionUE5 >= 519）
```
double X, double Y, double Z  → 24 字节
```

### FRotator
```
float Pitch, float Yaw, float Roll  → 12 字节
```

### FQuat（UE4）
```
float X, float Y, float Z, float W  → 16 字节
```

### FQuat（UE5 大世界坐标）
```
double X, double Y, double Z, double W  → 32 字节
```

### FTransform
```
FQuat  Rotation
FVector Translation
FVector Scale3D
```
UE4 共 40 字节；UE5 启用大世界坐标时共 80 字节

### FLinearColor
```
float R, float G, float B, float A  → 16 字节
```

### FSoftObjectPath
```
FString AssetPathName
FString SubPathString
```

---

## Actor Transform 的属性路径说明

在典型的关卡 Actor 中，Transform 数据存储在 **RootComponent** 子 Export 上，而非 Actor Export 本身。Actor Export 会有一个名为 `RootComponent` 的 ObjectProperty，指向对应的组件 Export。该组件 Export 包含以下属性：

- `RelativeLocation`（StructProperty → Vector）
- `RelativeRotation`（StructProperty → Rotator）
- `RelativeScale3D`（StructProperty → Vector）

若 `bAbsoluteLocation/Rotation/Scale` 为 true，则 "Relative"（相对）变为 "Absolute"（绝对世界空间）坐标。

---

## 常见解析失败原因及排查方法

| 症状 | 可能原因 | 排查方法 |
|---|---|---|
| Import 表名称全部偏移 | 缺少 PackageName 字段 (ver>=519) | 检查 FileVersionUE4，添加 PackageName 读取 |
| Export 表偏移错误 | TemplateIndex 版本号错误 (应为507) | 对照源码 ObjectVersion.h 确认版本号 |
| Export 表偏移错误 | PackageGuid 读取条件错误 | PackageGuid 始终存在，无条件读取16字节 |
| Export 表偏移错误 | PackageFlags 读取条件错误 | PackageFlags 始终存在，无条件读取4字节 |
| Export 表偏移错误 | FirstExportDependency 读取为 int64 | 应为 int32（4字节），检查源码 ObjectResource.h |
| 属性值出现极小/极大浮点数 | FPropertyTag 偏移错误 | 检查 HasSerializeMetaData（UE4中不存在） |
| BoolProperty 后续属性错位 | BoolProperty 值在Tag头而非值数据 | BoolProperty PropertySize=0，不从值数据读取 |
| 所有类名显示为 "Class" | 类名解析逻辑错误 | Import class_name=="Class" 时取 object_name |
| UE 版本判断错误 | LegacyFileVersion 不匹配 | 打印 FileVersionUE4 对照版本号表 |
| 压缩包无法解析 | Cook 后资源使用 zlib/Oodle 压缩 | 检查 PackageFlags & PKG_StoreCompressed |
| 加密包无法解析 | 发行版游戏加密资源 | 需要 AES 密钥解密 |
