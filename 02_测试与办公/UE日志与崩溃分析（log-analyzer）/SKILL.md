---
name: "log-analyzer"
description: "Analyzes UE log files to extract key errors, warnings and crash info. Invoke when user asks to analyze log, 分析日志, 日志分析, or 闪退分析."
---

# 日志分析器

分析 UE（Unreal Engine）日志文件，自动提取关键错误、警告和崩溃信息，汇总问题并指出具体位置。

## 触发条件

当用户提到以下关键词时激活此 Skill：
- 分析日志 / 分析log / 日志分析
- 闪退分析 / 崩溃分析
- log文件分析
- 排查问题 / 排查闪退

## 分析流程

### 第一步：获取日志基本信息

1. 读取日志文件，获取总行数
2. 提取设备信息（设备型号、操作系统、内存大小等）
3. 提取场景加载路径（LogLoad: LoadMap、LogNet: Browse）

### 第二步：分类搜索关键问题

按优先级从高到低，使用 Grep 工具搜索以下关键模式：

#### P0 - 致命问题（必搜）
```
Pattern: (Low Memory Warning|MemoryWarning|Free Memory Now|jetsam|OOM|out of memory)
Pattern: (Crash|Fatal|Assert|Exception|Access violation|SIGSEGV|SIGABRT)
Pattern: (LogMetal: Error|fence waits|incorrect fence)
```

#### P1 - 严重错误
```
Pattern: (LogStreaming: Error: Couldn't find file)
Pattern: (LogMaterial: Error|uncooked shader map|invalid ShaderMap)
Pattern: (LogScript: Error)
```

#### P2 - 警告问题
```
Pattern: (LogScript: Warning: Attempted to insert an item into array.*out of bounds)
Pattern: (LogPrimitiveComponent: Warning: CreateDynamicMaterialInstance.*Material index.*is invalid)
Pattern: (LogSkinnedMeshComp: Warning:.*No SkeletalMesh)
Pattern: (LogGameMode: Warning:.*No GameStateClass|FindPlayerStart: PATHS NOT DEFINED)
Pattern: (LogNiagara: Warning:.*WorldInit never happened)
```

#### P3 - 资源缺失
```
Pattern: (not find file from external disk)
```

#### P4 - 其他错误
```
Pattern: (LogHttpListener: Error|LogNet: Error)
Pattern: (Failed to compile Material Instance)
Pattern: (Missing Dependency)
```

### 第三步：分析日志终止原因

1. 读取日志最后 50 行，判断日志是否突然终止
2. 如果突然终止（无正常退出日志），检查终止前是否有 Low Memory Warning
3. 如果有 Low Memory Warning，对比启动时内存和当前可用内存，计算内存消耗量

### 第四步：汇总输出

输出格式如下：

---

## 日志分析报告

### 📱 设备信息
| 项目 | 值 |
|------|-----|
| 设备 | (从 LogInit: OS 行提取) |
| 系统 | (从 LogInit: OS 行提取) |
| 总内存 | (从 Memory total 行提取) |
| 启动可用内存 | (从 Free Memory at startup 行提取) |
| 低内存设备 | (从 EMIsLowMemoryDevice 行提取) |

### 🗺️ 场景加载路径
按时间顺序列出所有场景切换：
- `时间` → `场景名`

### 🔴 P0 致命问题
列出所有致命问题，每条包含：
- **问题**：简要描述
- **位置**：行号
- **详情**：关键日志原文

### 🟠 P1 严重错误
按错误类型分组汇总：
- **错误类型**：如"资源文件缺失"
- **数量**：N 个
- **涉及资源**：列出关键资源路径
- **位置**：行号范围

### 🟡 P2 警告问题
按警告类型分组汇总：
- **警告类型**
- **出现次数**
- **关键位置**：行号

### 🔵 P3 资源缺失
统计缺失的外部磁盘文件数量，列出关键的缺失文件路径。

### 💥 崩溃/闪退分析
- 日志是否突然终止：是/否
- 终止前最后时间戳
- 终止前最后操作
- 可能原因（优先级排序）

### 📊 问题统计
| 优先级 | 类型 | 数量 |
|--------|------|------|
| P0 | 致命 | N |
| P1 | 严重 | N |
| P2 | 警告 | N |
| P3 | 缺失 | N |

### 💡 建议解决方案
按优先级给出具体可操作的建议。

---

## 注意事项

1. 搜索时必须使用 `-n` 参数获取行号
2. 对于大量重复的同类错误（如资源缺失），只列出前 5 个具体路径，其余统计数量
3. 内存问题要特别关注：如果 Free Memory Now 低于 500MB，必须标记为 P0
4. Metal fence 错误在 iOS 上可能导致 GPU 崩溃，必须标记为 P0
5. uncooked shader map 错误意味着打包不完整，必须标记为 P1
6. 日志突然终止且无崩溃堆栈时，优先考虑 iOS Jetsam 杀进程（内存不足）
7. 所有行号引用使用 `[文件名:L行号](file:///路径#L行号)` 格式，方便跳转
