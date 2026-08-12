范围分为两类：

- **直接通用**：基本不依赖 EM 项目的类名、表结构或目录。
- **配置后通用**：能力可跨项目复用，但需要调整项目路径、引擎版本、插件、Commandlet、平台账号或仓库配置。

未收录强绑定 EM 业务系统的 NPC、活动、红点、设置、副本、大秘境、DNA、任务配表等 Skill。

## 使用注意

1. 本目录是独立归档，不会被 `.skill/可视化Skill分发.bat` 自动扫描；需要分发时，应选择具体包含 `SKILL.md` 的目录。
2. 带有 UE、TAPD、飞书或 SVN 能力的 Skill 通常需要先修改路径和认证配置。
3. `unreal-mcp-toolkit`、蓝图导出及关卡导出类 Skill 依赖项目插件或自定义 Commandlet，不能只复制文档就直接运行。
4. 部分 Skill 文档仍保留原 `.skill/...` 示例路径。这些是复制件，不应反向修改原权威源；迁移到新项目时应统一替换为新项目配置。
5. `tapd-detail-reader` 自带 Playwright 依赖，其中包含两个依赖库内部的 `SKILL.md`，不计入本归档的主技能数量。

## 01 通用研发流程

均为直接通用；Git 相关技能仅适用于 Git 项目。

| Skill | 简要描述 |
|---|---|
| `brainstorming` | 开发前澄清目标、约束和设计方案。 |
| `writing-plans` | 将需求整理为可执行的分步实施计划。 |
| `executing-plans` | 按既有计划执行并设置检查点。 |
| `systematic-debugging` | 基于证据定位 Bug 根因。 |
| `test-driven-development` | 以失败测试驱动功能或修复实现。 |
| `verification-before-completion` | 交付前运行验证，避免无证据宣称完成。 |
| `requesting-code-review` | 在合并或交付前组织代码审查。 |
| `receiving-code-review` | 严谨核实并处理代码审查意见。 |
| `dispatching-parallel-agents` | 拆分可独立并行执行的任务。 |
| `subagent-driven-development` | 使用子 Agent 执行计划中的独立任务。 |
| `using-git-worktrees` | 使用 Git Worktree 创建隔离工作区。 |
| `finishing-a-development-branch` | 测试通过后完成合并、PR 或清理。 |
| `writing-skills` | 创建、编辑和验证 Skill。 |
| `using-superpowers` | Superpowers 技能的入口与路由规范。 |

## 02 测试与办公

| Skill | 通用性 | 简要描述 |
|---|---|---|
| `testcase-reviewer` | 直接通用 | 用黑盒方法评审测试用例及异常、边界、多端场景。 |
| `excel-editing-checklist` | 直接通用 | 安全编辑 Excel，并检查格式和 OOXML 完整性。 |
| `xlsx-dir-merge-checker` | 配置后通用 | 对比两个配表目录，检查未合并内容及 SVN 来源。 |
| `macro-helper` | 直接通用 | 生成、解释和调试 Excel VBA 宏。 |
| `xlsm-vba-editor` | 直接通用 | 检查和修改 `.xlsm` 中的 VBA 代码。 |
| `schedule-tool` | 直接通用 | 根据优先级和资源生成排期、甘特图。 |
| `log-analyzer` | 直接通用 | 从 UE 日志中提取错误、警告和崩溃信息。 |

## 03 UE 蓝图与资产工具

本类大多需要配置引擎、`.uproject`、导出目录或安装对应插件。

| Skill | 简要描述 |
|---|---|
| `blueprint-export` | 将蓝图导出为包含变量、组件、节点和连接的 JSON。 |
| `blueprint-export-commandlet` | 通过自定义 Commandlet 导出蓝图和 UMG 结构。 |
| `export-assets-t3d` | 使用 UE Commandlet 将资产导出为 T3D。 |
| `t3d-exporter` | 将 T3D 蓝图数据转换为结构化 JSON。 |
| `t3d-json-reader` | 查询 T3D JSON 中的控件、变量、函数和动画。 |
| `ue-blueprint-analyzer` | 编排“T3D 导出、转 JSON、数据查询”全流程。 |
| `ue-mastermind-export` | 使用 UnrealMastermind 导出完整蓝图逻辑。 |
| `unreal-mcp-toolkit` | 通过 Unreal MCP 读写蓝图、UMG、关卡和 Flow 资产。 |
| `umap-analyzer` | 不启动编辑器，解析 `.umap` 对象和属性。 |
| `export-umap-json` | 用 ExportUmapInfo Commandlet 导出 WC 关卡与 Actor。 |
| `foot-animation-analysis` | 分析脚步接触区间并生成或回写 Alpha 曲线。 |
| `check-scene-full` | 检查关卡边界、合批、反射、贴花和图层等规范。 |
| `check-scene-memory` | 统计关卡 Mesh、Texture、Material 内存和三角面开销。 |

## 04 UE 工程开发

| Skill | 简要描述 |
|---|---|
| `ue-build-debug` | UE 项目构建、编译错误排查和工程结构导航。 |
| `vscode-clangd-setup` | 为 UE C++ 工程配置 VSCode、clangd 和调试环境。 |
| `ue4-cpp-lua-interface` | UE C++、Lua/UnLua 与蓝图之间的接口设计规范。 |
| `blueprint-replication-check` | 检查 Replicated/RepNotify 变量和 MarkDirty 使用。 |
| `nav-build` | 配置、构建和排查 UE NavMesh。 |
| `nav-pathfinding` | 分析异步寻路、PathFollowing 和导航线程安全。 |

## 05 性能分析

| Skill | 简要描述 |
|---|---|
| `netprofile` | 解析网络性能数据，检查热点和冗余流量。 |
| `traceloader` | 将 UTrace 导出为帧数据和 Timing Events。 |
| `profile-analyst` | 从慢帧继续下钻到真实叶子成本与源码根因。 |
| `profile-expert` | 审查性能修复涉及的生命周期、异步和内存风险。 |

## 06 协作平台与版本管理

需要目标项目继续使用对应平台，并重新配置账号、项目 ID、仓库和提交模板。

| Skill | 简要描述 |
|---|---|
| `tapd-detail-reader` | 通过浏览器登录态读取 TAPD 详情页。 |
| `summarize-changes` | 汇总多次 SVN 提交的净改动、测试点和审查结论。 |
| `svn-commit` | 使用包含 TAPD 信息的规范消息执行 SVN 提交。 |
| `svn-diff-datas` | 查询 SVN 版本中的 Lua 数据变更并展开引用。 |
| `read-feishu` | 读取飞书文档、长截图和内嵌 PDF。 |
| `lark-mcp` | 管理用户令牌并代理飞书 MCP 请求。 |
| `tapd` | 调用 TAPD 项目管理能力，处理需求查询和创建。 |

## 07 工作流维护工具

均为直接通用。

| Skill | 简要描述 |
|---|---|
| `workflow-creator` | 按明确指令创建工作流文件和目录。 |
| `workflow-reviewer` | 审查工作流架构或执行日志的合规性。 |
| `workflow-scanner` | 扫描工作流 Wiki 引用死链并生成修复报告。 |

## 统计

- 分类：7 个
- 主技能包：54 个
- 主 `SKILL.md`：54 个
- 依赖库内附带的非主技能说明：2 个
