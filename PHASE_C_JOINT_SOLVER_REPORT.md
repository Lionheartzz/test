# Phase C — 联合事务续接、资源和晚期 CAD 准入

日期：2026-10-14。起点：4baa9f2ee8fb46c85ed577894f1f79e20ad9161b，分支 codex/sqlite-domain-reset。保留 Phase A/B、JointSolver、GeometryState、AISearchContext、LocalAdmission 和原工程门禁。

**控制层修复取得真实验证；复杂工程仍未完整可制造，Phase C 仍有功能 blocker。** 最终正常 Generate 达到 7/8 解析兼容，晚期 CAD 后保留 5 条真实局部准入路线。完整 Design 的 Exact/BRep/STEP 未执行，manufacturing_ready=false。

## 根因和实际修复

| 已确认问题 | 修复及源码 |
|---|---|
| 历史 completed 使后续 advance() 提前退出并重复交付旧结果 | joint_solver.RepairTransaction.take_completed()/advance()：完成档案与交付游标分离，只对本批新增完成结果停止；其他安排与未完成队列继续保留。 |
| 零标签阻止已生成候选的配对；重试重复计样本 | 同函数：先执行 pending/缓冲候选；配对重试不消耗新标签、新样本；真正生成的样本只计一次。 |
| 两条新路线完成小释放组后，没有向第三条缺失 Net 交接 | joint_routes.coordinate()：CONTINUE_COMPLETED_PARTIAL 把实际新路线作为更大条件事务的父状态，继续每条缺失 Net；全部外部保留加工仍参与筛查。 |
| 资源需要同时非零，旧 fragment 与事务割裂 | RefinementSchedule、coordinate、RepairTransaction：依据实际可执行工作分配资源，优先有进展的深分支，停滞后降低优先级；保存条件化 fragment 迭代器，用原 probe 额度继续加工替代方案。 |
| 收尾批次数与 Net 数量绑定 | joint_layout.optimize()：布局结束后按原资源账本和真实进展终止，不按 Net 数量截断条件树；零工作状态标记 idle，防止空循环。 |
| 早期用完 CAD；拒绝后换首选却不继续检查 | Session、LocalAdmission、admit_final_cores()：普通筛查不花新 CAD 额度；半数额度服务选中的深 core，余量服务实际最终首选。拒绝引起排序改变时继续准入，直到首选稳定或额度用尽。依赖缓存和未知错误分类保留。 |

另更新 joint_state.capture() 的真实事务进展、layout_search.screen() 的资源调用及 generation.py 的进度消息。没有修改共享 Router、CAD/Validation 规则、SQLite 或工程定义。

## 通用真实见证

三 Net 的旧加工网络均独立通过生产 CAD 准入，但两两互相阻挡。相同输入和总预算下：

| 控制器 | 兼容覆盖 | 新标签 | 样本 | 结果 |
|---|---:|---:|---:|---|
| 完成组未向后续 Net 交接 | 2/3 | 512 | 32 | 30 个局部完成安排，仍无全网方案 |
| 修复后的实际 coordinate() | 3/3 | 96 | 6 | 2 次条件交接，三条路线均在旧池之外 |

真实 Exact：**250 PASS / 0 WARNING / 0 FAIL**；BRep 有效/1 solid；STEP 往返有效/1 solid，体积差约 3.26e-9 mm³。见 partial-handoff/test_completed_partial_groups_0/controller-exact/acceptance.json。

另验证：32+32+32 标签真实续接；历史完成结果不重复交付且不阻止其他分支；零标签/零新样本仍能完成 pending 配对；只有 probes 时执行真实加工替代；晚期首选断开被 CAD 拒绝后，重新排序的合法首选取得实际准入。没有模拟 CAD 成功结果。

## 最终正常复杂 Generate

源码冻结清单：output/runtime-checks/phase-c-closure-20261013/final-source-hashes.json。最终运行 normal-generate-final-verified/，复用原审核源，经正常 generation → initialization → joint_layout → shared Router。未 monkeypatch 主算法，未重新识图，未调用付费 AI。

| 指标 | 最终实测 |
|---|---:|
| 总耗时 | 3764.484 s，约 62.7 分钟 |
| 评价布局 / 独立实际几何 | 48 / 48 |
| 通过源布局筛查 | 45 |
| 尺寸 / 安装姿态组合 | 14 / 22 |
| 最高解析兼容覆盖 | **7/8**，布局 33 后期精化从 5 提升至 7 |
| 最大条件父分支 | 4 条新路线 |
| 几何上下文 / 联合事务 / 完成安排 | 46 / 57 / 5 |
| 真实三维上下文 / 新增标签 | 12 / 928 |
| 局部 CAD 调用 | 15/16，最终保留五条全部 LOCAL_EXACT_ADMISSIBLE |
| 完整 Design Exact / BRep / STEP | 0 次 / 未执行 / 未执行 |

最终保留 A_DC、MA、MB、SHUTTLE_OUTPUT、T_DC；B_DC、P、T 仍 unresolved。五条路线的局部证据均保留对应 dependency 和 retained_nets，不能把这些局部检查当成最终五网或八网 Design 的完整验证。流量未知时仍为 null，不伪造流量要求。

## 剩余 blocker 的具体证据

1. **T 的全网协调未闭合。** 布局 33 有 12 条独立 source-clear T 候选，仍不能插入七网安排。实际 cross_net_wall 包括 R-8e428e23-1 ↔ R-e632b709-3（T_DC/T）、R-309be2fb-4 ↔ R-e632b709-3（B_DC/T）。事务已尝试在四条新路线后规划 T；仍有未展开工作，不能证明物理无解。
2. **B_DC 有真实直接接触不足。** 整体流体图连通，但 R-309be2fb-7 ↔ R-309be2fb-9 的直接交集仅 0.03131770974415805 mm³，低于原规则 0.1 mm³。因此拒绝，没有用其他连通路径豁免这个接触。
3. **P 是 CAD 无法判断。** routing.fluid_intersection.result 对 CV_beb0668eb32018773fa3:P ↔ R-5c62e091-4 返回 INVALID_TOPOLOGY；两输入有效，共同实体无效。保留 CAD_EVALUATION_ERROR、physical connectivity=null，不是物理断开证明。
4. **资源协调仍有系统限制。** 总额未提高：2048 标签/2000 状态/8000 配对/512 probes/128 样本；用了 928/1688/1307/260/128。样本先耗尽，仍余 1120 标签、312 状态、6693 配对、252 probes，以及 173 个 pending jobs、103 个延后布局、49 个动作生成器。pending 配对可脱离样本继续，但需要新候选的条件树仍受样本准入依赖约束；现有样本流与协调枚举尚不能稳定把独立合法路线转成完整工程方案。它不是旧 completed 提前退出，也不是已证明没有加工走廊。

因此不能声明 Phase C 无 blocker；没有复杂工程零 FAIL、有效生产 BRep 或 STEP 的结论。

## 验证、隔离和交付

聚焦验证覆盖本轮事务/交接/资源/晚期 CAD、Phase A 的 E1/E2/E4/E5、Phase B 续接与 E6 分类、Store/API、Manual Model。新控制器真实钻孔经 Save Draft/Reload 保留；新工作进程禁止搜索，Validate/Build 明确拒绝缺失路线；显式 Reroute 只搜索被释放 Net，源位置与保留加工不变。未运行 T-10A、prove、广泛套件、浏览器、Vite 或付费 AI。

13 个保护文件逐项 SHA-256 不变：SQLite、原始 source-only Design、9 个存档、2 个 AI task。源移动权限没有扩散到 Model、Preview、Validate、Build 或 Save/Reload。

失败、两次早期中止、暴露晚期准入遗漏的完整运行（2802.391 s）及最终运行分别保留，没有把中止或旧源码运行当最终验收。最终机器证据：docs/engineering/phase-c-closure-evidence.json；完整原始记录与可导入部分 Draft：output/runtime-checks/phase-c-closure-20261013/。源码哈希与最终运行一致。

代码、报告、测试统一提交。提交 SHA、远端 HEAD、最终工作树状态见提交后生成的 output/runtime-checks/phase-c-closure-20261013/delivery.json 和最终回复。本报告所属提交可用 git log -1 --format=%H -- PHASE_C_JOINT_SOLVER_REPORT.md 解析。
