---
name: "schedule"
description: "需求排期调度工具，基于优先级的贪心算法生成甘特图。Invoke when user asks about schedule, 排期, 甘特图, or project planning."
---

# 需求排期调度工具

基于优先级的贪心调度算法，自动分配资源并生成甘特图可视化。

## 触发条件

- 用户提到"排期"、"排期工具"、"甘特图"
- 用户需要进行项目计划安排
- 用户询问需求工期估算

## 工具位置

```
G:\EM\.skill\工具类\排期工具\schedule_tool\
├── schedule.py        # 主程序
├── config.json        # 配置文件（模板+人员）
├── data.json          # 需求数据
└── requirements.txt   # 依赖
```

## 使用方法

### 1. 准备数据文件 (data.json)

```json
{
  "deadline": "2025-06-09",
  "tasks": {
    "S01-核心战斗系统": {
      "template": "S级需求",
      "version": "1.0",
      "priority": 100
    },
    "A01-用户登录系统": {
      "template": "A级需求",
      "version": "1.0",
      "priority": 95
    }
  }
}
```

### 2. 运行排期

```bash
cd G:\EM\.skill\工具类\排期工具\schedule_tool
python schedule.py --data data.json
```

### 3. 常用参数

| 参数 | 说明 |
|------|------|
| `--data, -d` | 数据文件路径（必需） |
| `--config, -c` | 配置文件路径（默认 config.json） |
| `--deadline` | 截止日期，反推开始时间 |
| `--buffer, -b` | 缓冲比例（如 0.2 表示20%） |
| `--output, -o` | CSV输出路径 |

### 4. 输出文件

运行后生成：
- `schedule_result.csv` - 排期结果表格
- `schedule_gantt_by_person.png` - 按人员维度的甘特图
- `schedule_gantt_by_task.png` - 按需求维度的甘特图

## 配置说明

### 需求模板 (config.json)

支持 S/A/B/C 四个级别的需求模板，包含：
- 工序流程及依赖关系
- 各工序默认工期
- 角色人员配置

### 工序流程

```
系统策划 → 交互策划 → GUI设计 → GUI蓝图 → 客户端程序 → 验收 → QA测试
                    ↘ 服务器程序 ↗
```

### 优先级规则

- 数值越大优先级越高
- 同优先级按版本号排序
- 高优先级需求优先分配资源

## 依赖安装

```bash
pip install matplotlib pandas numpy plotly
```
