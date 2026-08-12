import subprocess
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from lark_mcp import UATManager, MCPProxy, DEFAULT_SERVER_URL

report_content = """| 字段 | 值 |
|------|-----|
| 文件 | demo.utrace |
| 采样时长 | ~41 分段（每分段约 100-130MB） |
| 分析时间 | 2026-04-15 |
| 分析阶段 | Phase 1 宏观概览 |

本次分析针对 **demo.utrace** 进行 GameThread 宏观概览，过滤条件：MaxDepth=4, MinDuration=10ms。

**整体评级：🔴 严重超标**

1. **最严重问题**：`UnSerialize [SerializeUtils:184]` 单次调用耗时 **182.33 ms**
2. **次要问题**：`func [ArchiveMgr:4]` 单次调用耗时 **96.71 ms**
3. **第三问题**：`TickableGameObjects Time` 峰值 **1819.20 ms**

---

## 分段收敛分析

| 分段 | Lua 调用次数 | Lua 总耗时 | Tick 调用次数 | Tick 总耗时 | 状态 |
|------|-------------|-----------|--------------|------------|------|
| Part 1 | 1172 | 359.28 ms | 68 | 1842.95 ms | ⚠️ 异常 |
| Part 2 | 312 | 79.00 ms | 132 | 57.99 ms | ⚠️ 需关注 |
| Part 3 | 0 | 0 ms | 21 | 5.08 ms | ✅ 正常 |
| Part 4-6 | 0 | 0 ms | 0 | 0 ms | ✅ 正常 |

**收敛结论**：数据在 Part 3 已收敛。

---

## 🔴 P0 优先级问题

### 问题 1：UnSerialize 反序列化耗时过高

| 属性 | 值 |
|------|-----|
| 函数 | `UnSerialize [SerializeUtils:184]` |
| 单次耗时 | 182.33 ms |
| 严重程度 | 🔴 极严重 |

**优化建议**：检查调用频率，添加缓存或分帧加载

### 问题 2：ArchiveMgr 模块耗时过高

| 函数 | 单次耗时 | 调用次数 | 优化建议 |
|------|----------|----------|----------|
| `func [ArchiveMgr:4]` | 96.71 ms | 1 | 确认是否为初始化 |
| `_TryAddRewardReddotCommon [ArchiveMgr:32]` | 12.86 ms | 4 | **添加 0.5s 缓存** |

### 问题 3：TickableGameObjects Time 峰值过高

| 属性 | 值 |
|------|-----|
| 峰值耗时 | 1819.20 ms |
| 平均耗时 | 606.42 ms |

**优化建议**：优化同屏对象数量和更新频率

---

## 优先级行动清单

| 优先级 | 问题描述 | 当前值 | 目标值 | 预估收益 | 建议操作 |
|--------|---------|--------|--------|---------|---------|
| P0 | `UnSerialize [SerializeUtils:184]` | 182.33 ms | ≤ 1 ms | -181 ms | 检查调用频率，添加缓存 |
| P0 | `ArchiveMgr:4` | 96.71 ms | ≤ 10 ms | -86 ms | 确认初始化操作 |
| P1 | `_TryAddRewardReddotCommon` | 12.86 ms/max | ≤ 5 ms | -8 ms | 添加 0.5s 缓存机制 |
| P1 | `TickableGameObjects Time` | 1819.20 ms | ≤ 500 ms | -1300 ms | 优化同屏对象数量 |

---

## 热点函数汇总（Top 9）

1. `UnSerialize [SerializeUtils:184]` - 182.33 ms
2. `func [ArchiveMgr:4]` - 96.71 ms
3. `_TryAddRewardReddotCommon [ArchiveMgr:32]` - 20.69 ms
4. `InitWikiRewardReddotNode [WikiEntry:233]` - 8.81 ms
5. `func [BattlePass:5]` - 4.98 ms
6. `func [MiscEnterWorldMgr:8]` - 4.03 ms
7. `func [CommonQuestActivity:8]` - 3.72 ms
8. `GetLeafNodeCacheDetail [ReddotManager:390]` - 3.24 ms
9. `_TryAddNewReddot [ArchiveMgr:63]` - 2.39 ms

---

*报告生成时间：2026-04-15 20:05*
*分析工具：utrace_flow workflow*
"""

title = "EM 性能分析报告 2026-04-15"

args = {
    "title": title,
    "markdown": report_content
}

print(f"[INFO] Creating Feishu doc: {title}")

uat_manager = UATManager()
uat_manager.load()

if not uat_manager.is_valid():
    print("[ERROR] UAT is invalid. Please run: python scripts/lark_mcp.py auth")
    sys.exit(1)

proxy = MCPProxy(DEFAULT_SERVER_URL, uat_manager)
result = proxy.handle_request("tools/call", {
    "name": "feishu_create_doc",
    "arguments": args
})

print("\n=== Result ===")
print(json.dumps(result, indent=2, ensure_ascii=False))