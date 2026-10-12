# AI Layout / Routing 核心修正

起始及审查 HEAD：`a55aa0de8ddde931aa0afc69b087232fa2617106`，`codex/sqlite-domain-reset`，起始工作树干净。

## 根因及修复

| 已确认根因 | 源码及实际修复 |
|---|---|
| `_catalogs()` 在 32 次解析尝试／8 个 clear 候选时永久结束，且未调用公共分支、安全混合入口策略。`simple_routes()` 在截断前还会急切构造双平面组合。 | 原位置 `layout_planning.py:96/129` 保持手工默认；AI `route_catalog.py::Catalog/Session` 改为惰性策略流、失败入口修复及跨 Net 重分配。每布局仍为 **32 × Net 数**总采样：24×N 初筛、8×N 冲突修复；8 是活跃批次，已筛查的延后几何可进入组合搜索。 |
| `terminal_branch_candidates()` 将第二高度追加到 `primary`，随后 face-window 分支只读 `primary[:3]`，不同加工层没有机会生成。 | `branch_candidates.py:124/150`：仅 AI 显式 `diverse=True`，交错真实源高度／入口／分支顺序，继续流受上述总采样预算限制。手工仍走原十二候选顺序。 |
| 失败记录只含钻孔 ID；反馈主要换面／普通排布。两个 Net 共用同组多口元件时，独占元件集合为空，无法形成调整。 | `route_feedback.py::obstruction_witnesses/measured_actions` 保存完整失败钻孔，测量加工、安装、堵头及跨网切削边界，生成有明确轴／距离／冲突位置的位移、必要尺寸和允许换面。共用元件可分别调整；所有源定义及 Net 语义不变，调整后重新生成、筛查路线。 |
| `pack_topology()` 给前置元件选一次局部最优；后置 Port 放不下就失败。 | `design_space.py:254`：有限联合 beam 保留早期不同安排，晚到的真实跨面加工可淘汰前置选择。总探测额度仍为 512×可移动元件数，并记录未解决／回退证据。 |
| 布局按宽泛家族轮转，失败反馈滞后，部分路线每次重新开始。 | `joint_layout.py:81`：每小批布局反馈，优先实测冲突动作；`Session` 复用终端未改变的路线并重新检查其他障碍。兼容性提升到初批之外的部分路线优先占复用槽。逐布局落盘，异常不会再丢掉全部历史。 |
| 实际运行又暴露浅钻孔 `depth < plug_length`：绑定闭合定义后原始 Feature 不合 schema，反馈反序列化中止全轮。 | AI 候选阶段明确拒绝 `invalid_machining`；诊断读取不会将已拒绝的无效 Feature 当成路线，也不会中止其他候选。未改闭合定义或降低啮合要求。 |

## 同源关键结果

已逐字段确认新旧初始 Design 相同。原位置和 310×245×230 mm 不变时：

- A_DC：**0 → 7**，B_DC：**0 → 8** 个解析 source-clear 候选。
- 八个 Net 均有解析候选；总采样 **256**，没有把每网 32 次简单放大。
- 最后代码的同源诊断耗时 **16.453 s**。这些候选仍是 `NOT_EXACT_VERIFIED`。

复杂案例首次处理第 14 个布局时因上述真实浅堵头候选中止；保留了异常证据。修正后只做一次 **12 布局的有界复查**，耗时 **359.672 s**，8 个实测反馈布局、2 个尺寸布局、1 个换面布局及初始布局。实际出现按冲突计算的 ±8.01 mm 元件调整，以及每布局最多 64 个保留候选的重新筛查。

选中布局可保留 **6/8 Net** 的解析兼容部分路线（A_DC、MA、P、SHUTTLE_OUTPUT、T、T_DC）；MB、B_DC 尚不能加入。组合搜索实际提升了初批之外的候选，选中池分别有 9–19 个 clear 选择；31 个协调状态、679 次配对筛查后为 `retained_pools_incompatible`，未触达 1000／4000 截止。因此此处不是笼统的“搜索预算不足”。

## 仍存在的 blocker

完整八阀仍为 **UNRESOLVED_LAYOUT**，没有完整 Exact 尝试、验证计数或 BRep／STEP 接纳。

选中未解决组合的实际解析冲突包括 MA/MB `R-1d09f6fa-2 ↔ R-f0055891-1`、MB/T_DC `R-1d09f6fa-AX2 ↔ R-8e428e23-3`，以及 B_DC 与 MA、T_DC、A_DC、SHUTTLE_OUTPUT 的钻孔冲突。P/T_DC 在该选中组合中未再报告间距冲突；这不是 Exact 串油清除证明。

剩余缺陷在于**联合加工入口／分支走廊的协调能力**：已有单网 source-clear 几何，局部换层和源位移仍不足以同时避开其他完整外表面加工孔。部分布局仍会失去 A_DC 的 source-clear 入口，说明单体改善会影响同元件的其他液压窗口。没有证明空间无解；仍有 33 个布局及 14 个动作生成器未评估。不能用这些解析候选宣称制造通过。

## 隔离及针对性验证

新行为仅由新 AI Generate 路径启用；共享 `simple_routes(include_detours=True)`、`terminal_branch_candidates(diverse=False)` 默认不变。没有新增 Model、Preview、Validate、Build、Save/Reload 或手工 Reroute/Optimize 的布局调用，没有使用 `origin.method` 授权移动。

只运行 `tests/test_ai_routing_core.py`：**9 项通过**，覆盖联合回退、实测位移、总预算重分配、共享默认隔离、真实 Exact 连通性拒绝、移动障碍后的复筛、共用元件／锁定边界、无效堵头候选和提升候选复用。最后的复用优先槽改动单独验证；未为它重复完整复杂搜索。静态语法及 diff 检查通过。

全部原存档、源 Design 和 SQLite 的 SHA-256 未变。未运行 T-10A、prove、完整套件、浏览器、Vite、Store/API、材料或 Drawing 测试，未调用付费 AI。

简明机器证据：`docs/engineering/ai-layout-routing-core-evidence.json`。原始逐布局证据：`output/runtime-checks/ai-routing-core-20261012/eight-valve-corrected/`。提交／远端及工作树状态记录于本机同级 `delivery.json`，并在交付回复中给出。
