---
name: profile-expert
description: Use when a source-mapped Unreal performance problem or first fix needs expert review of engine/Lua runtime contracts, async races, memory ownership, lifecycle safety, shared-framework impact, production hardening, or an irreducible architecture risk decision.
---

# Profile Expert

## 核心目标

接管 Analyst 已归因的问题，把初版处理推进成可实施、可回滚、可验证的方案。专家的价值是解除卡点和降低风险，不是把问题驳回、增加文档字段或为每项凑候选。

## 接管输入

读取任务根 `reports/working/performance_problem_queue.md` 和 `reports/working/profile_analyst_report.md`，再核对其引用的 artifact 与源码。若根因链不闭合，不代填假设：直接给 Analyst 一项能区分关键分支的源码调查、导出、埋点或最小实验，并把该卡 owner 改回 `analyst`。

## 专家处理程序

1. 复核直接成本是否与用户症状处于同一操作链，确认 self/inclusive、构建配置和样本边界。
2. 阅读修改点上下游源码，列出必须保持的同步顺序、返回值、输入/焦点、网络、持久化、资源所有权、对象回收和生命周期契约。
3. 判断 Analyst 初版方案能否直接收敛：
   - 安全且命中成本：补齐实现细节、失败路径、回滚和验证后批准设计；只有运行时复测达标后才标记修复已验证。
   - 方向正确但存在竞态/生命周期缺口：直接重写关键结构，使用 repo 已验证 API 加入 request serial、generation、weak/validity check、取消、超时或 flush 等必要防线。
   - 缺少安全能力：优先设计范围最窄的局部 adapter、受控原型或诊断开关；先证明契约，再决定是否改共享框架。
   - 实验结果不足或根因不稳：把精确判别实验交还 Analyst，不写成正式修复。
4. 搜索 repo 的相邻实现、引擎封装和失败处理。不得凭经验虚构 API，也不得因为“专家身份”跳过源码和数据验证。
5. 用户允许修改时实施已批准的最小方案并复测；只读时给出可评审 patch、明确未验证边界和执行顺序。
6. 复测不达标或产生新尖刺时，更新同一问题卡并选择：调整方案、退回 Analyst 继续归因，或升级架构决策。不得把失败原型包装成已解决。

## 生产级方案契约

在 `reports/working/profile_expert_report.md` 按问题输出：

1. `专家裁决`：`design_approved / prototype_required / verified_fix / return_to_analyst / user_architecture_decision`。`design_approved` 表示可实施但尚未完成运行时复测；`verified_fix` 必须已有同场景修改前后数据和功能门禁结果。
2. `复核后的根因`：数据、调用链、源码和配置边界。
3. `必须保持的契约`：业务与引擎运行时不变量。
4. `最终改法`：文件、函数、状态字段、调用顺序和关键代码；简单删除不强行包装成架构方案。
5. `防错闭环`：只列该方案真实需要的存活校验、串行号、取消、失败、回收、持久化或线程边界。
6. `风险与回滚`：可观察失败、影响范围、开关或还原路径。
7. `验证结果/计划`：修改前后数据、功能分支、内存/总延迟等相关副作用。
8. `下一动作与 owner`：继续实施、交还 Analyst 或请求用户决策。

更新同一 `performance_problem_queue.md`，不要另建一套 solution finding/schema。

`prototype_required` 默认由 Analyst 实施和采集，owner 改回 `analyst`；只有原型本身需要专家编写共享 adapter 时才由 Expert 持有。原型失败后记录结果与被否定机制，再由 Analyst 继续归因或重新交 Expert，不能原样重跑。

## 技术卡点赋能

Analyst 不知道怎么解时，专家必须先尝试以下路径：

- 找到已有异步、调度、池化、生命周期或资源管理 API 的真实调用样例。至少引用一个真实调用点，并核实参数、返回/回调、owner、线程和取消/失败语义；缺任一关键契约时只能作为原型假设。
- 把共享框架改动缩成一个调用方 adapter 或单页面原型。
- 用埋点/断言/开关把未知契约变成可观测结果。
- 将大改拆成可回滚的行为保持步骤，并定义每步性能与功能门禁。
- 若缺数据，设计能在一次采集内区分候选机制的实验，而不是泛化补采清单。

专家可以重写初版方案，但不能无证据承诺 Production-ready，也不能默认添加全局缓存、兼容层或公共 wrapper。

## 架构风险升级门槛

只有同时满足以下条件，才能标记 `user_architecture_decision`：

- 直接根因和用户影响已由数据、调用链及源码证实。
- 局部删除、时机迁移、adapter、受控原型和防御性实现均无法保持关键契约。
- 可行改动必须触及共享生命周期、渲染/线程管线、全局资源所有权或持久化一致性。
- 已说明不改的代价、改动范围、主要失败模式、分阶段路线和所需验证成本。

“风险较高”“缺少万全之策”或“需要更多数据”本身不足以升级；先把可执行的解题路径交回 Analyst。

## 禁止的专家假象

- 用更复杂代码掩盖根因尚未闭合。
- 不查 repo 就手写不存在的引擎 API、回调或生命周期。
- 对简单局部修复强加缓存、adapter、兼容层或公共框架改造。
- 把所有风险都升级给用户，或把所有草案都宣称可直接合入。
- 只评审文档，不接管技术卡点、实验设计和复测决策。
