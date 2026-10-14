# Engineering Layout Planner：现有实现、取消记录与失败分析

基线 `12409be9e0866f34ccab66a68cb532e5cd6a3836`；分支 `codex/sqlite-domain-reset`。

**本次不是完整制造验收，也不能声明 Rev2 已完成收口。** 用户要求停止后，复杂运行已退出；8 个源布局均有记录，峰值解析兼容 4/8，完整 Exact/BRep/STEP 均未执行，manufacturing_ready=false。此后没有再次执行复杂 Generate，仅做限时源快照复核和聚焦检查。

## 已保留的实际实现

正常调用链已接入 `generation → plan_new → optimize → EngineeringDecisionController`。新增 `EngineeringPlan` 从实际源切削、刚性窗口、Net 超图、工具/闭合定义及显式 LayoutDomain 编译事实；`CorridorPlanner` 先选择共轴、对齐窗口或正交分支工艺，再由 `PlacementSolver` 用共享刚体坐标、Block 和交汇变量的差分约束反求位置/尺寸。

`EngineeringDecisionController` 处理工艺、入口、刚体姿态、源分离及尺寸的条件分支；真实钻孔由生产 `propose / simple_routes / axial_route / MachiningSpace` 实现。JointSolver、RepairTransaction、AISearchContext、LocalAdmission、Exact 和原工程阈值保留。旧排布器仅作为表达缺口的回退。

实际修正还包括窗口等式矛盾传播、软脚手架坐标释放、源定义支持的深侧入口、换面时保留工艺选择，以及替代展开缓存包含完整约束依赖。最后一项在同一真实输入中由“20 个分支，新约束下错误变成 0”修复为 20→20；没有提高布局或搜索数字。

这仍是有限工艺语言和条件充分域。**数学域可解不等于完整外表面加工可行。** 当前复杂失败表明，分支/交汇预留尚未把所有完整钻孔、其他源保护体和安装堵头的关系闭合。

## 当前复杂运行及真实性能

证据目录：`output/runtime-checks/engineering-planner-20261014/complex-frozen-final/`。原 8 个 `layouts/*.json`、初始源 Design、审核输入、进度 JSONL、源码冻结清单、部分路线及事务诊断全部保留。`cancelled-evidence.json` 汇集已落盘内容；原文件未覆盖或删除。

离线脚本直接调用生成函数，没有注册 UI jobs 的取消事件。本次使用终端执行会话的 Ctrl-C 中断退出；不能声称调用了 UI cancel API。新增监督器后，正常 UI 的现有取消事件可终止独立 AI 工作进程，见后面的真实验证。

最后落盘进度为 **2159.937 秒**，不是精确进程退出时间。退出前 OS 观察到进程 CPU 2451.62 秒；这是最后观察值，不是最终 CPU 或独占 CAD 时间。

| 布局 | screen 秒（含 Router/协调/局部几何） | 完成的深度精化秒 | 已保留解析 Net 数 |
|---:|---:|---:|---:|
| 0 | 49.156 | 550.094 | 4 |
| 1 | 48.141 | — | 2 |
| 2 | 46.110 | — | 2 |
| 3 | 44.453 | — | 2 |
| 4 | 43.203 | — | 4 |
| 5 | 46.203 | — | 4 |
| 6 | 50.734 | — | 4 |
| 7 | 55.235 | 未完成的当前精化 | 3 |

8 个布局有不同的实际源位置/姿态，Block 有 3 组尺寸：169.103×300.503×215.776、169.103×300.503×221.708、169.103×321.553×215.776 mm。源布局变化确实发生，但未解决完整加工空间。

普通 screen 合计 383.235 秒，加已完成精化为 933.329 秒；余下至少 1226.608 秒包含工程域求解、源/加工实例筛查、未完成精化及 I/O，现有证据无法准确分摊。原脚本没有持久化进程内 timing/cache，故**独占 Router/CAD 时间、原运行缓存命中和退出时完整内存前沿不可恢复**，机器证据用 null/unknown，不补造数值。

第一次精化实际由 2/8→4/8，完成 512 个新标签。其后日志最后报告当前事务展开 64 标签，但未完成批次的总账不完整；不能将可见进度当成完整批次统计。最后完成批次的剩余额度为 labels=1536、states=1837、pairs=7977、probes=384、samples=118，仅代表该检查点，不能冒充退出时余额。已落盘的 pending/continuation/transaction 记录及完整路径哈希保留；未落盘的队列未知。

## 为什么仍然只有 4/8

在这些布局中，B_DC/T_DC 有普通 source-clear 候选；A_DC/SHUTTLE_OUTPUT 由共享三维精化补出可兼容路线。MA、MB、P、T 没有保留 source-clear 路线。因此当前阻塞并不只是“四条合法路线无法与另外四条组合”，还有尚未建立的真实源接入。

控制层的具体未闭环位置是 `EngineeringDecisionController.next_candidate()`：已检测到计划加工失败后，仍可返回 `SOURCE_DOMAIN_SOLVED_ROUTING_PENDING`；`optimize → screen → Session.prepare` 随后在该源布局上展开普通目录和深度 Router。保留有效源 Draft 是正确的产品行为，但不能据此认为其加工计划值得持续精化。现有条件反馈没有把重复源侵入/堵头冲突转化为足够有效的提前中止或工艺改选。两次明确违规复核只需约 0.1 秒 Router screen，而完整布局 screen 仍需 44–55 秒，第一次精化又用了 550 秒；尚未证明无效搜索已减少。

| 类别 | 实际证据 | 判断 |
|---|---|---|
| 真正的加工方案违规 | Planner 的 A_DC：`CV_6bbcdb6cce3a4c816cb3 ↔ R-702e7749-4`，生产窄相位重查交体积 **524.298125497 mm³** | 保护源几何侵入，Router 正确拒绝；不是 CAD 数值错误。 |
| 真正的堵头/孔违规 | Planner 的 T：`R-e632b709-3 ↔ R-e632b709-8`，实际堵头占用与切削交体积 **66.399302647 mm³** | 同一 Net 的方案也不安全；整体连通不能豁免。 |
| 多项实际占用冲突 | P 的计划记录含安装入口、源保护及堵头交集；布局 4–6 的 B_DC 计划还侵犯外部端口及源体 | 选定工艺域的边界/交汇预留没有覆盖全部实际实体关系。 |
| Planner/Router 表达缺口 | 源位置和交汇点满足选定差分域，外表面至终点的完整加工却仍被上述规则拒绝 | 已证明的是约束不充分。缺少完整原始工艺意图/操作区间的历史落盘，不能断言所有问题都是 Router 忽略了约束；通用见证也不能排除真实复杂场景的表达差异。 |
| CAD 数值错误 | 已落盘的这些 core 均为 ANALYTIC_CLEAR，没有此轮 CAD_EVALUATION_ERROR 记录 | 不能把物理交集归咎于 INVALID_TOPOLOGY；未落盘的内部调用仍未知。旧 E6 CAD 错误分类继续保留。 |
| 尚未探索 | 有限工艺、源姿态及三维前沿仍有 pending；原始完整意图和全部内存队列未保存 | 未证明其他工艺不存在，不能称物理无解，也不能只写“预算不足”。 |

两次复核直接使用已保存源 Design 和计划钻孔，通过生产 `route_obstructions` / 局部 Exact 实体；均设置总计 10 秒、单布局 6 秒、深度 1 秒上限，实际分别 2.437 / 2.454 秒完成。Router screen 为 0.094 / 0.109 秒；布尔交集各约 0.031 秒。缓存字典 lookup 为 568/41、434/40（hit/miss），仅属于这两次复核，不是旧复杂运行的缓存统计。

## 新增 AI-only 耗时上限与安全退出

`generation.generate` 使用 `execution.py / execution_worker.py` 的专用 ProcessJob。默认总计 **600 秒**、单布局累计活动时间 **120 秒**、深度路由累计 **90 秒**；可在 GenerationOptions 中调低或设定有限上限。历史 None/0 总时限采用有限默认值。布局切换按活动时间分账，回到同一布局不会重置已消耗时间。

独立父进程每 50 ms 监控取消和时间；先写取消原因并给予 1 秒协作退出，若原生 CAD 未返回则停止所属完整进程树，ProcessJob 退出等待最多 5 秒。到期是计算未完成，不是工程无解。检查点保存最后源布局/真实部分钻孔及约束证据，status=incomplete_draft/cancelled、validation=null、manufacturing_ready=false；输入尚未编译出 Design 时保留输入，不虚构草稿。

新增耐久的 timing/progress、每布局用时、三维标签/前沿、事务 pending、缓存 lookup 和进程 CPU/内存记录。初始草稿标识不会因快速进度覆盖而丢失。完整结果只由父进程按现有乐观版本规则发布一次；不会写入现有 Model 项目。

Manual 的 Preview/Validate/Build/Save/Reload/Reroute/Optimize 没有进入该监督器，共享 CAD Executor 的原时限/所有权语义未改。源加工定义、工程 Library、SQLite 和原项目未改。

## 聚焦验证与保护

- 保留的规划器通用证明：名称/顺序、共享刚体多窗口、实际换面、换入口、深侧接入、三网互斥及直接开口不足；通用见证真实 Exact/BRep/STEP 通过，均为明确 QA 几何，不是厂家认证。
- 当前相关聚焦 25 项通过；执行器/取消/默认 Router/Manual/Store/API 复验 10 项通过；最后执行器 5 项通过（有重叠，不汇总成制造 PASS 数）。真实 native 工作触发单布局上限且进程树停止；正常 Generate 超时只发布一个未接纳草稿；现有 jobs.cancel 事件停止真实工作进程并保留草稿。四条依赖弃用提示不是工程 WARNING。
- 另以总计 12 秒上限执行一个微型通用见证，确认新的 AI 工作进程能够调用嵌套生产 CAD 进程并取得真实 Exact、单实体 BRep 和 STEP PASS；这是进程兼容证明，不是复杂工程制造验收。
- 原 Phase A/B 聚焦证据保留；没有运行 T-10A、prove、全套 Python/JS、浏览器、Vite、付费 AI 或新的复杂 Generate。
- 13 个保护文件（SQLite、源 Design、九个存档、两个 AI task）SHA-256 前后一致。保存/独立进程重载与 Validate/Build 的真实钻孔持久化证明保留。仅可选 Router 操作区间记录参数增加，默认几何逐项比对不变。
- 此前 174.688、1684.235、1966.578 秒的三次中止也完整保留，不计为验收成功；当前用户取消是第四次未完成记录。无完整复杂制造验收。

**尚存 blocker：完整外表面钻孔与源保护/堵头关系尚未进入足够强的规划约束；MA/MB/P/T 接入仍未解决；未证明有效走廊和无效搜索量已有实质改善。因此不满足再次完整复杂回归的条件。** 旧回归脚本已拒绝自动完整重跑；本次到提交现有实现和事实报告为止。

机器证据：`docs/engineering/engineering-layout-planner-evidence.json`；完整运行及限时复核：`output/runtime-checks/engineering-planner-20261014/`。最终提交、远端 HEAD、工作树和最终保护哈希由交付 `delivery.json` 及最终回复记录。
