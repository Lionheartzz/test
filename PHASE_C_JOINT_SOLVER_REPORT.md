# Phase C — AI 联合布局与加工求解控制层

起始 HEAD：`af4a5bd03bdf760a5f9782fa217e6fdb261aa382`。保留 Phase A/B；未修改共享 Router、CAD/Validation 门禁、SQLite 或已有项目。

## 已确认根因与整改

1. **F7：单网可行被误用作替代入口不再重要的证明。** `layout_search.screen()` 以前只传递清晰池为空的 Net 的源障碍。现在 Catalog 保留全部实际拒绝的加工安排，内部反馈使用完整记录，公共诊断只保留精简样例。复用原始布局 45：八网各有清晰路线，旧反馈为 0，当前生产反馈恢复 61 条实际加工障碍；这证明信息恢复，不代表其中某个入口已被证明是完整解必需入口。
2. **F8：释放组没有相互条件化的新加工搜索。** 旧深度阶段仅对 missing Net 调用 `plan_net()`，释放的其他 Net 仍使用旧池。新增 `joint_solver.RepairTransaction`，保存多个 Net 的加工分支；子分支针对父分支刚生成的完整真实钻孔及全部外部保留路线继续规划。不同附接顺序、失败证据、未展开工作均保留。
3. **覆盖/成本排序越权成为剪枝。** 移除兼容 core 的 best−1/固定数量淘汰与活跃几何上下文 LRU 丢弃。完整实际几何相同才合并；保留的冲突剪枝只来自同一依赖下的实际加工违规。当前覆盖、孔长和体积用于选择结果，不证明另一空间被支配。反馈父状态按已取得的展开机会调度，深度资源首先给尚未评价的不同空间。
4. **旧 fragment 阶段抢占新的联合阶段。** 首次复杂运行暴露深度额度进入旧单网 fragment 阶段后才调用联合续接的顺序问题。该运行被中止并保留全部证据，没有作为完整回归。最终调度把显式深度额度交给联合续接前沿；旧 fragment/core 保留为延后工作。未提高布局、标签、配对或 Exact 总额度。
5. **完整 Exact 结果必须更新同一个活跃状态。** 完整拒绝发生后，新的 assessment 以前可能只更新在布局记录中，后续动作却读到状态内旧的解析 assessment。现在 `record_state()` 按该布局自己的 dependency 同步结果，支持被检查布局不是当前布局的情况。真实相交钻孔被生产 Exact 拒绝后，拒绝事实进入正确状态并产生几何反馈；CAD 失败不会变成虚假的物理通过。

源码：`manifold/ai_design/joint_solver.py`、`joint_routes.py`、`route_catalog.py`、`layout_search.py`、`joint_layout.py`、`joint_state.py`、`layout_resources.py`、`route_feedback.py`、`initialization.py`、`generation.py`。

## 联合状态、条件约束与共同修复

`Session` 持有一个新 Generate 专属 `JointSolver`。每个 `GeometryState` 保存完整源 Design、Net 实际端点、工程定义/工具 Catalog、硬锁定域、兼容 core、真实加工条件、源障碍、局部准入与联合修复事务。布局反馈直接使用这个状态；序列化摘要不承担活跃求解状态的恢复职责。

依赖包含 Block、所有源姿态/定义、端点、工程规则、工具及闭合库、锁定域。每条条件约束进一步绑定两条具体路线的全部参数和实际 Feature 身份。仅针对相同依赖、相同加工安排复用安全/违规事实。源或工程条件改变后进入新的几何状态；原状态前沿仍保留，可在完全相同依赖返回时继续。

真实加工违规可剪除同一安排；`search_budget`、尚未检查与 `CAD_EVALUATION_ERROR` 不生成物理禁止条件。配对额度不足的候选进入待检查队列，后续重新检查。CAD 错误保留实体、操作、原因和可重试条件，不能证明空间不可行。

冲突约束传给刚性多窗口姿态、联合平移、安装面及测量尺寸反馈。移动量仍由完整加工边界、壁厚和安装保护决定，变化后全源及所有受影响 Net 重新筛查。共享 Cavity 始终是一个刚性 Feature；不会按 Net 复制或独立平移其窗口。源位置不动的联合钻孔事务优先执行，必要的布局变化产生新的联合状态。

Phase B 的 `AISearchContext` 是唯一三维续接器；事务不重建路径堆、连接树或 visited。`LocalAdmission` 是唯一局部 CAD 准入层。局部通过只表示相应准入事实，完整组合仍须经过现有 Exact、Validation、BRep、STEP。

## 通用见证与必要聚焦验证

- 双网旧加工互相阻挡：生产 `joint_routes.coordinate()` 共同释放后，两网均产生旧池之外的新路线。实际兼容 core 从 1 条退让到 0 条再达到 2 条；64 个新标签，后规划者使用前规划者的新钻孔作为保留障碍。真实结果：**143 PASS / 0 WARNING / 0 FAIL**，BRep 有效/1 solid，STEP 有效/1 solid，体积差 `1.6298145055770874e-9 mm³`。
- 共享刚性多窗口源：通用三个 Net、两个多窗口源的生产姿态动作同时改变多个 Feature，所有六个实际窗口及第三方 Net 一起重新计算；显式锁定始终保留。
- source-clear Net 的受阻替代入口仍进入真实源障碍反馈并生成可复核布局动作；旧 F7 过滤条件不再存在。
- 三维事务分批继续真实未完成路径；保留旧轨迹前缀并展开新标签。配对未检查候选保留并在真实配对额度恢复后接纳。
- 改变源位置、Block 或实际路线后，原条件约束不再适用；返回原依赖仍可复用原状态。
- 原布局 45 的 P 路线仍真实返回 `INVALID_TOPOLOGY`，记录为 CAD 无法判断，物理连通性为 null；其他合法局部路线保留。真实几何违规仍被拒绝。
- Phase A/B、保存/重载/新工作进程、Manual Model 与对应 Store/API 的必要聚焦检查通过。未执行 T-10A、prove、广泛套件、浏览器、Vite 或付费 AI。

详细结果及失败尝试保留于 `output/runtime-checks/phase-c-20261013/`。源码/运行输入哈希见 `final-code-hashes.json`；通用完整 CAD 见 `controller-r2/test_two_nets_need_new_conditi0/joint-exact/acceptance.json`。

## 正常复杂 Generate

最终运行：`scripts/evaluate_ai_generation.py`，复用原已审核 source-only Design，经 `generation.prepare/candidate → initialization → joint_layout → screen → shared Router`，没有 monkeypatch 或付费识图。

最终实测结果见 `docs/engineering/phase-c-joint-solver-evidence.json` 和本报告下方的运行结果。首次中止运行位于 `normal-generate/interrupted.json`；最终完整运行位于 `normal-generate-final/`。二者分别报告，不能把中止运行算作完整成功。

最终结果：**`SOURCE_LAYOUT_READY_ROUTING_PENDING`，仍存在复杂工程功能 blocker，不能声明整套 AI 自主设计已经解决。**

| 指标 | 实测 |
|---|---:|
| 完整 Generate 耗时 | 4412.297 s（约 73.5 分钟） |
| 已评价 / 独立实际几何布局 | 48 / 48 |
| 通过源布局筛查 | 45 |
| 尺寸 / 安装姿态组合 | 18 / 22 |
| 最佳兼容覆盖 | 6/8 |
| 深度精化布局索引 | 3、6、14、18 |
| 新三维标签 / 真实续接批次 | 2048 / 4 |
| 联合修复事务 / 三维上下文 | 44 / 60 |
| 完整 Exact 尝试 | 0/2 |
| 延后布局 / 未展开动作生成器 | 121 / 49 |
| manufacturing_ready | false |

两次深度精化把同一候选从 5/8 推进至 6/8。实际出现先生成 B_DC 的新路线、再针对它生成 MB 新路线、随后针对两者规划第三条 Net 的条件分支；这与旧 F8 的单网深度调用不同。最大条件分支已有两条新路线，但第三条尚未形成完整安排。共享源联合姿态、测量分离、安装面变化和尺寸变化均实际执行，例如宽度由 245 增至 300.6684424761103 mm，也评价了其他三个尺寸同时变化的布局。

条件约束记录覆盖 `cross_net_wall`、`installation_access`、`plug_cut`，同一依赖下用于禁止已检查的具体冲突安排，并驱动相关源动作。记录 5182 项安全/违规条件，其中违规规则实例分别为 3770、161、212；这些是搜索中的条件事实数量，不能当作最终设计的 FAIL 数。

选中布局保留 A_DC、MA、MB、P、SHUTTLE_OUTPUT、T；**B_DC、T_DC 仍未解决**。选中 core 没有当前依赖下的局部 Exact 准入，其状态为 `ANALYTIC_CLEAR`，不是工程已验证。完整 Exact/BRep/STEP **未执行**，没有零 FAIL 或制造批准结论。

剩余系统限制与证据：

- **搜索未覆盖：** 四个精化布局仍有 48、60、45、49 个待处理事务作业。部分 3D 条件分支只展开 32/64 个标签，大的冲突连通分量尚未取得展开机会；已有两条新路线的安排未完成第三条。不能据此证明没有合法加工走廊。
- **资源种类仍未充分协同：** 标签用完时仍剩 1065 个组合状态、7366 次配对、512 次旧 fragment 探测、88 个样本额度。此次整改优先保护真实联合续接，推迟独立 fragment；它没有证明剩余资源已被最优分配，更没有通过提高额度把问题隐藏。
- **局部 CAD 调度仍有限：** 现有 16 次局部准入分配消耗在早期几何，后续更好的 core 保持待验证。完整 Exact 的两次额度不能等同于任意数量局部 CAD 调用，未擅自换算或增加。
- **约束表达是具体加工安排的条件 nogood 与测量修复，非完整连续坐标域求解。** 未展开的姿态/连接树/加工安排仍可能改变结论。当前证据不足以把失败归因于缺失源数据、CAD 运算错误或已证明的硬约束冲突；主要类别是未覆盖的联合搜索和资源协调限制。

此前 1291.75 s 的摘要运行使用更早的底层判断，不能视为相同正确性条件的性能对照。本次 4412.297 s 未取得更高的全局覆盖，**没有性能改善或复杂工程收口的主张**。

复杂回归执行时算法被冻结；随后仅补齐完整 Exact 结果同步和对应诊断字段。该回归没有完整 Exact 尝试，因而未执行这个同步分支；另用真实生产 Exact 拒绝反例及优化器接受路径集中验证。执行与交付源码哈希分别记录，不把冻结回归说成对未执行分支的验证。

## 隔离与边界

求解权限来自当前新 Generate 的显式 owned Features/锁定域。Manual Model、Preview、Reroute/Optimize、Validate、Build、Save/Reload 不创建 `JointSolver`。CAD worker 对完整候选只调用原 Exact 接纳函数，不取得源移动权限。AI Draft 进入 Model 后，实际 Features 按原格式保存；候选 ID 不存储路线。

源布局检查通过而完整路由未完成时，状态为 `SOURCE_LAYOUT_READY_ROUTING_PENDING`；保留选中的源布局与实际兼容部分钻孔，缺失 Net 明确 unresolved。这个 Draft 不具有制造批准；源布局不可行与尚未找到路线分别报告。

受保护文件以原 13 文件清单逐项 SHA-256 比较：工程 DB、原始源 Design、9 个存档、2 个 AI task。前后结果记录于机器证据；不修改上述文件。

提交与远端确认记录在 `output/runtime-checks/phase-c-20261013/delivery.json`；本报告所属提交可通过 `git log -1 --format=%H -- PHASE_C_JOINT_SOLVER_REPORT.md` 精确解析。最终回复给出实际 SHA 与远端 HEAD。
