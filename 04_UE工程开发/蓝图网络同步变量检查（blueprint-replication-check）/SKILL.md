---
name: blueprint-replication-check
description: 分析蓝图及C++继承链中的Replicated/RepNotify同步变量，检查Lua和C++代码中修改时是否正确标脏（MarkDirty）。触发场景：排查网络同步问题、检查同步变量修改是否合规、分析蓝图继承链中的同步状态。
---

# Blueprint Replication Check - 蓝图同步变量检查工具

分析蓝图及其C++继承链中的所有同步变量，检查Lua和C++代码修改时是否正确标脏。

## 使用方式

执行前先从 `{SKILLS_ROOT}/CONFIG.md` 读取路径变量。

```bash
python "{SKILLS_ROOT}\blueprint-replication-check\scripts\analyze_blueprint.py" --blueprint <蓝图名> [选项]
```

## 参数说明

| 参数 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `--blueprint, -b` | ✅ | 蓝图名称，如 `BP_EnergySupply` | - |
| `--json-dir, -j` | ❌ | 蓝图JSON导出目录 | `D:\BlueprintExport_Skill` |
| `--lua-root, -l` | ❌ | Lua脚本根目录 | `{EM_ROOT}\Content\Script` |
| `--cpp-source, -c` | ❌ | C++源码目录 | `{EM_ROOT}\Source\EM` |
| `--output, -o` | ❌ | 输出报告路径 | 控制台输出 |

## 工作流程

1. **解析蓝图JSON** - 从 `--json-dir` 加载蓝图导出文件
2. **构建继承链** - 递归查找父类（蓝图 → C++基类 → ... → AActor）
3. **收集同步变量** - 提取所有 `Replicated` 和 `RepNotify` 变量
4. **检查Lua修改** - 在 `{EM_ROOT}\Content\Script` 查找对应Lua文件，检查 `self.VarName =` 是否调用 `MarkDirty`
5. **检查C++修改** - 在 `{EM_ROOT}\Source\EM` 查找C++源文件，检查变量修改是否调用 `MARK_PROPERTY_DIRTY_FROM_NAME`
6. **生成报告** - 输出问题变量及修复建议

## 检测模式

### Lua代码检测

**问题模式：**
```lua
-- 直接赋值，未标脏
self.NowEnergy = 100
```

**正确模式：**
```lua
-- 先标脏再赋值
self:MarkDirty("NowEnergy")
self.NowEnergy = 100
```

### C++代码检测

**问题模式：**
```cpp
void AMyClass::SetValue(int Val)
{
    MyValue = Val;  // 缺少 MARK_PROPERTY_DIRTY_FROM_NAME
}
```

**正确模式：**
```cpp
void AMyClass::SetValue(int Val)
{
    MyValue = Val;
    MARK_PROPERTY_DIRTY_FROM_NAME(AMyClass, MyValue, this);
}

// 或使用封装函数
void AMyClass::SetValue(int Val)
{
    MyValue = Val;
    MarkDirty_MyValue();  // 函数内部调用 MARK_PROPERTY_DIRTY_FROM_NAME
}
```

## 输出报告

### 继承链示例
```markdown
## 继承链
- [BP] BP_EnergySupply (父类: EnergySupply)
- [C++] AEnergySupply (父类: ASupplyBase)
- [C++] ASupplyBase (父类: AMechanismBase)
- [C++] AMechanismBase (父类: ACombatItemBase)
- [C++] ACombatItemBase (父类: ASceneItemBase)
- [C++] ASceneItemBase (父类: AEMActor)
- [C++] AEMActor (父类: AActor)
```

### 同步变量列表示例
```markdown
| 变量名 | 类型 | 来源 | 同步方式 | Lua修改 | C++修改 | 标脏状态 | 风险 |
|--------|------|------|----------|---------|---------|----------|------|
| NowEnergy | float | [BP] BP_EnergySupply | Replicated | 6处 | 无 | Lua:未标脏 | [CRITICAL] |
| UnitType | FString | [C++] ASceneItemBase | Replicated | 无 | 6处 | C++:已标脏 | [MEDIUM] |
```

### 风险等级

| 等级 | 条件 | 说明 |
|------|------|------|
| [CRITICAL] | Replicated + 修改 + 未标脏 | 必定导致同步问题，需立即修复 |
| [HIGH] | RepNotify + 修改 + 未标脏 | 可能导致回调问题，建议修复 |
| [MEDIUM] | Replicated + 修改 + 已标脏 | 正常，但需确认逻辑正确性 |
| [LOW] | Replicated + 无修改 | 无风险 |

## 示例

```bash
# 分析单个蓝图
python "{SKILLS_ROOT}\blueprint-replication-check\scripts\analyze_blueprint.py" --blueprint BP_EnergySupply

# 输出到文件
python "{SKILLS_ROOT}\blueprint-replication-check\scripts\analyze_blueprint.py" --blueprint BP_SabotageTarget --output report.md

# 分析纯C++类（无蓝图）
python "{SKILLS_ROOT}\blueprint-replication-check\scripts\analyze_blueprint.py" --blueprint AEMGameState --json-dir "D:\NotExist"
```

## 修复建议模板

### Lua修复
```lua
-- 修改前
self.NowEnergy = newValue

-- 修改后
self:MarkDirty("NowEnergy")
self.NowEnergy = newValue
```

### C++修复
```cpp
// 修改前
void AMyClass::SetNowEnergy(float Val)
{
    NowEnergy = Val;
}

// 修改后 - 方式1：直接标脏
void AMyClass::SetNowEnergy(float Val)
{
    NowEnergy = Val;
    MARK_PROPERTY_DIRTY_FROM_NAME(AMyClass, NowEnergy, this);
}

// 修改后 - 方式2：封装标脏函数
void AMyClass::SetNowEnergy(float Val)
{
    NowEnergy = Val;
    MarkDirty_NowEnergy();
}

void AMyClass::MarkDirty_NowEnergy()
{
    MARK_PROPERTY_DIRTY_FROM_NAME(AMyClass, NowEnergy, this);
}
```

## 注意事项

1. **检测范围**：向前检查50行代码内的标脏调用
2. **命名约定**：支持 `MarkDirty_VarName`、`MarkVarNameAsDirty`、`MarkVarNameDirty` 等封装函数
3. **C++类名**：支持A/U前缀（如 `AEnergySupply` 会自动查找 `EnergySupply.h`）
4. **误报情况**：修改在Set函数中而标脏在调用处时可能误报，需人工确认
