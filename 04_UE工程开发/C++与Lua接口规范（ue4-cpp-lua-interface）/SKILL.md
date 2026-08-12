---
name: ue4-cpp-lua-interface
description: UE4 C++ 与 Lua（蓝图）交互规范指南。触发场景：将 Lua 代码迁移到 C++、创建 C++/Lua 双向调用接口、修改 Interface 类函数声明、处理 BlueprintImplementableEvent 事件。
---

# UE4 C++ 与 Lua 交互规范

C++ 与 Lua 双向调用接口的声明和实现规范，确保跨语言函数调用正确工作。

## 使用方式

参考 `{SKILLS_ROOT}/CONFIG.md` 中的路径变量定位源码文件。

## 两种实现模式

### 模式 A：纯 C++ 实现

**使用场景**：功能完全在 C++ 中实现，Lua 仅作调用

**C++ 声明**：
```cpp
// 头文件 ({EM_ROOT}/Source/EM/Public/...)
class IMyInterface
{
public:
    // 纯 C++ 实现：UFUNCTION() + virtual
    UFUNCTION()
    virtual void MyFunction(int32 Param1, FString Param2);
};
```

**C++ 实现**：
```cpp
// 源文件 ({EM_ROOT}/Source/EM/Private/...)
void IMyInterface::MyFunction(int32 Param1, FString Param2)
{
    // 纯 C++ 实现逻辑
    UE_LOG(LogTemp, Log, TEXT("Param1: %d, Param2: %s"), Param1, *Param2);
}
```

**Lua 调用**：
```lua
-- Lua 直接调用，无变化
self:MyFunction(100, "test")
```

### 模式 B：Lua 实现，C++ 包装

**使用场景**：功能在 Lua 中实现，C++ 提供调用入口

**C++ 声明**：
```cpp
// 头文件
class IMyInterface
{
public:
    // C++ 包装函数（无 UFUNCTION 宏）
    void MyFunction(int32 Param1, FString Param2);
    
    // Lua 实现入口（BlueprintImplementableEvent）
    UFUNCTION(BlueprintImplementableEvent, Category = "EM")
    void MyFunction_Lua(int32 Param1, FString Param2);
};
```

**C++ 包装实现**：
```cpp
// 源文件
void IMyInterface::MyFunction(int32 Param1, FString Param2)
{
    // 转调 Lua 实现
    this->Execute_MyFunction_Lua(this->_getUObject(), Param1, Param2);
}
```

**Lua 实现**：
```lua
-- ({EM_ROOT}/Content/Script/...)
function Component:MyFunction_Lua(Param1, Param2)
    -- Lua 实现逻辑
    print("Param1:", Param1, "Param2:", Param2)
end
```

**Lua 调用**：
```lua
-- 调用 C++ 包装，实际执行 Lua 逻辑
self:MyFunction(100, "test")
```

## 决策表

| 需求场景 | C++ 声明 | Lua 声明 | 实现位置 |
|----------|----------|----------|----------|
| **纯 C++ 实现** | `UFUNCTION() virtual void Func();` | 无 | C++ |
| **Lua 实现** | `void Func();` + `UFUNCTION(BlueprintImplementableEvent) void Func_Lua();` | `function Component:Func_Lua(...)` | Lua |

## 关键区别

| 函数类型 | UFUNCTION | virtual | 内部实现 |
|----------|-----------|---------|----------|
| 纯 C++ 实现 | ✅ `UFUNCTION()` | ✅ | 纯 C++ 逻辑 |
| C++ 包装函数 | ❌ | ❌ | 调用 `Execute_xxx_Lua` |
| Lua 实现函数 | ✅ `BlueprintImplementableEvent` | ❌ | Lua 逻辑 |

## 命名规范

| 场景 | C++ 函数名 | Lua 函数名 |
|------|-----------|-----------|
| 纯 C++ 实现 | `Func()` | 无 |
| Lua 实现（C++ 包装） | `Func()` | `Func_Lua()` |

## 迁移 Lua 到 C++ 的完整步骤

**场景：将 Lua 函数迁移到纯 C++ 实现**

### 步骤 1：头文件声明

```cpp
// ({EM_ROOT}/Source/EM/Public/Combat/MyInterface.h)
class IMyInterface
{
public:
    UFUNCTION()
    virtual void MyFunction(int32 Param);
};
```

### 步骤 2：C++ 实现

```cpp
// ({EM_ROOT}/Source/EM/Private/Combat/MyInterface.cpp)
void IMyInterface::MyFunction(int32 Param)
{
    // 将原 Lua 逻辑翻译为 C++
    if (Param > 0)
    {
        // ... C++ 实现
    }
}
```

### 步骤 3：Lua 调用（保持不变）

```lua
-- 调用方式不变
self:MyFunction(100)
```

### 步骤 4：清理（可选）

如原先是 Lua 实现模式，删除：
- C++ 中的 `_Lua` 函数声明
- Lua 中的 `Func_Lua` 实现

## 新增 C++/Lua 接口的完整示例

### 新增纯 C++ 实现函数

**C++ 头文件**：
```cpp
// IStaticCreatorInterface.h
class IStaticCreatorInterface
{
public:
    UFUNCTION()
    virtual void ASSS();
};
```

**C++ 源文件**：
```cpp
// IStaticCreatorInterface.cpp
void IStaticCreatorInterface::ASSS()
{
    UE_LOG(LogTemp, Log, TEXT("ASSS called from C++"));
}
```

**Lua 调用**：
```lua
self:ASSS()  -- 输出: ASSS called from C++
```

### 新增 Lua 实现函数

**C++ 头文件**：
```cpp
class IStaticCreatorInterface
{
public:
    // C++ 包装
    void DestoryOneStaticActorAll(EDeathReason DeathReason, EDestroyReason DestroyReason);
    
    // Lua 实现入口
    UFUNCTION(BlueprintImplementableEvent, Category = "EM")
    void DestoryOneStaticActorAll_Lua(EDeathReason DeathReason, EDestroyReason DestroyReason);
};
```

**C++ 源文件**：
```cpp
void IStaticCreatorInterface::DestoryOneStaticActorAll(
    EDeathReason DeathReason, 
    EDestroyReason DestroyReason)
{
    this->Execute_DestoryOneStaticActorAll_Lua(
        this->_getUObject(), 
        DeathReason, 
        DestroyReason);
}
```

**Lua 实现**：
```lua
function Component:DestoryOneStaticActorAll_Lua(DeathReason, DestroyReason)
    -- Lua 实现逻辑
    self:DoSomething(DeathReason, DestroyReason)
end
```

**Lua 调用**：
```lua
self:DestoryOneStaticActorAll(reason, destroyReason)
```

## 常见错误

### 错误 1：纯 C++ 函数缺少 virtual

```cpp
// ❌ 错误
UFUNCTION()
void MyFunction();  // 缺少 virtual，Lua 无法正确调用

// ✅ 正确
UFUNCTION()
virtual void MyFunction();
```

### 错误 2：Lua 实现函数命名不一致

```cpp
// ❌ 错误 - C++ 和 Lua 函数名不匹配
void MyFunction();  // 包装函数
UFUNCTION(BlueprintImplementableEvent)
void MyFunc_Lua();  // Lua 函数名不一致

// ✅ 正确
void MyFunction();  // 包装函数
UFUNCTION(BlueprintImplementableEvent)
void MyFunction_Lua();  // 必须加 _Lua 后缀
```

### 错误 3：C++ 包装函数加 UFUNCTION

```cpp
// ❌ 错误
UFUNCTION()  // 包装函数不应加 UFUNCTION
void MyFunction();

// ✅ 正确
void MyFunction();  // 无 UFUNCTION
```

### 错误 4：Execute_ 调用参数错误

```cpp
// ❌ 错误 - 缺少 this->_getUObject()
void MyFunction()
{
    this->Execute_MyFunction_Lua();  // 缺少 UObject 参数
}

// ✅ 正确
void MyFunction()
{
    this->Execute_MyFunction_Lua(this->_getUObject());
}
```

## 快速决策流程

```
需要新增函数？
│
├─ 纯 C++ 实现？
│  └─ UFUNCTION() + virtual + C++ 实现
│
└─ Lua 实现？
   ├─ C++ 包装：void Func() 【无 UFUNCTION】
   └─ Lua 入口：UFUNCTION(BlueprintImplementableEvent) void Func_Lua()
```

## 文件路径规范

| 类型 | 路径模板 | 示例 |
|------|----------|------|
| C++ 头文件 | `{EM_ROOT}/Source/EM/Public/**/*.h` | `Public/Combat/MyInterface.h` |
| C++ 源文件 | `{EM_ROOT}/Source/EM/Private/**/*.cpp` | `Private/Combat/MyInterface.cpp` |
| Lua 脚本 | `{EM_ROOT}/Content/Script/**/*.lua` | `Script/BluePrints/BP_XXX_C.lua` |

## 总结口诀

- **纯 C++**：`UFUNCTION() + virtual`，Lua 直接调用
- **Lua 实现**：C++ 包装（无宏）+ `_Lua` 入口（BlueprintImplementableEvent）
