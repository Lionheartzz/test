# Phase B：三维搜索续接与早期工程准入

基线 `36d65c92c00170427121829336495c1147c15b29`，分支 `codex/sqlite-domain-reset`。本轮仅整改 F3/F6；未实施 Phase C、修改工程库/存档或增加案例专属候选家族。

## F3：保留真正的搜索，而非重启前缀

- `manifold/drilling_planner.py::_PathSearch` 将原路径展开提取为一个标签的原子步骤；源窗口、加工动作、邻居顺序、壁厚/堵头/工具检查仍使用现有实现。默认手工 `_path/plan_net` 保留原一次性策略及裁剪预算。
- `manifold/routing_continuation.py::_NetSearch, AISearchContext` 由 AI `Session` 显式创建。每个依赖集保留实际路径 heap、seen/expanded、分页 cursor、坐标细分、终端顺序、部分树、加工 Features、路径和序列计数器。预算停在下一标签展开之前，不丢弃已弹出的树任务。
- 有效部分连接立即进入下一终端的树搜索，同时保留父路径的真实未展开队列。候选输出批次不再触发路径堆丢弃、forbidden 列表重启或固定“四个路径解”截断；所有工作仍受原标签额度约束。
- 依赖键包含完整源 Design、显式 Net members（schema 序列化会排除此派生字段）、Block、规则/默认值、工程定义、工具、闭合库及实际保留加工体。冻结输入副本，几何改变使用不同状态；恢复完全相同输入可以继续原前沿。
- 相同依赖可共享 Phase A 已分离的完整钻孔几何事实；路径前沿、visited、端点条件和连接树不共享。输出候选是独立 Feature 副本，外部编辑不会污染搜索缓存。
- `joint_routes.coordinate` 显式传入 AI 续接上下文。`detail.labels` 只表示本次新增展开，`cumulative_labels` 表示累计真实展开，接入现有精化额度计数。没有增加标签、组合或完整 Exact 预算。

## E3：真实布局 38

使用原源 Design、原保留六网加工孔、同一目标 Net 和工程库；没有识图、变换输入或完整 Generate。

| 比较项 | 原审查 | 整改后真实复验 |
|---|---|---|
| 两次 128 标签 | 两次相同的 128 状态前缀 | 新增 `[128,128]`，累计 `[128,256]` |
| 第一批/第二批 | 重复前缀 128/128 | 各 128 个不同状态，批次间交集为 0 |
| 与连续 256 比较 | 无真实续接 | 全部逐标签轨迹一致 |
| 可用加工候选 | 两批均为 0 | 两种搜索均保留 86 个解析候选；完整 Feature 参数及稳定 ID 一致 |
| 输出批次 | 无前沿可继续 | 零新增标签排空剩余候选缓存，全部 86 个均可取回，无候选因交付批次丢失 |
| 路径解批次 | 四个解后重建/丢队列 | 实际单路径保留 86 个解，未丢弃其待展开 heap |

连续参考使用独立的搜索对象/队列/visited，仅复用相同依赖下的几何缓存；参考新增钻孔几何计算为 0，仍真实执行 256 个搜索标签。另有冷缓存的小型生产算法检查，验证 16+16+32 与连续 64 的轨迹/候选一致。

这 86 个是 **解析候选，不是局部 CAD 或完整制造通过**。未把有界搜索结果解释为物理可行性或不可行性证明。

完整真实轨迹、候选计数和耗时：`output/runtime-checks/phase-b-20261013/final/e3*.json`。早期诊断试验也保留，交付结论采用 `final/` 下定稿的结果。

## F6：部分 core 在搜索期间获得准确的局部状态

- `ai_design/local_admission.py::LocalAdmission` 调用既有 `_verify_route_candidate` 和真实 CAD/流体图检查，明确记录 ANALYTIC_CLEAR、LOCAL_EXACT_ADMISSIBLE、LOCAL_EXACT_REJECTED、CAD_EVALUATION_ERROR。CAD 错误的物理连通性为未知，保留实体对、操作、原因、形状状态与重试条件。
- `route_catalog.Session.admit_core`、`joint_routes.coordinate` 在有价值的部分组合上选择性准入，`layout_search.screen/joint_state.capture/rank` 分开记录解析覆盖和已局部准入覆盖。未检查状态不能成为已确认的局部结果。
- CAD/真实规则拒绝的原候选和切削数据仍在目录/证据中；只有当前不可准入的候选退出确认 core。搜索继续原前沿，其他有效路线不被清空。
- 只有可证明依赖“同一源与自身流体实体”的失败证据才影响后续选择。涉及其他 Net 的冲突保持条件化；去掉阻挡加工体后可以重新准入，不能变成无条件候选封禁。
- 准入缓存使用完整依赖键；缓存命中不重复 CAD。显式 retry 使用新的 CAD 错误缓存。搜索候选保留按依赖关联的准入记录；修改源/路线/端点/闭合/保留加工体后不能继承不匹配的批准。
- 局部检查额度为会话内 `max(8, 2 × Net 数)`，只评估选中的 core；耗尽时保持 ANALYTIC_CLEAR/pending。完整 Design 的 Exact/BRep/STEP 门禁与原预算不变。

### E6：真实布局 45

原六网解析 core 通过实际 `coordinate` 调用进入局部检查：MA、MB、SHUTTLE_OUTPUT、T、T_DC 五条路线取得 LOCAL_EXACT_ADMISSIBLE；P 候选进入 CAD_EVALUATION_ERROR。

错误实体对：`CV_9622e55cd4ee3586de17:P ↔ R-5c62e091-4`。操作：`routing.fluid_intersection.result`；原因：`INVALID_TOPOLOGY`。没有将其写成已证明物理断开。

局部检查用 `prune=False` 保留被审查的实际完整孔集；另按生产默认 `prune=True` 复核该失败候选，得到相同 CAD 错误。五条合法路线保留；原 P 几何和错误证据未删除。相同输入再查命中缓存，显式新缓存 retry 也经过真实 CAD。

独立的真实负例证明：连通/开口规则拒绝会记录为 LOCAL_EXACT_REJECTED；跨 Net 冲突不能污染成无条件失败；额度不足仍是未检查。记录拒绝后，原三维前沿继续新增标签，并保留原候选与几何计算缓存。

## 验证与边界

- Phase B 聚焦检查：真实搜索分批/缓存/失效/候选保留、E6 准入和错误重试、条件化冲突与继续前沿。
- Phase A E1/E2/E4/E5 聚焦回归通过；E4 再次经过真实 Exact、单实体 BRep 和 STEP。另验证现有上下文恢复、反馈调用与默认手工路由。
- 保存/重载/独立工作进程 Validate/Build/显式编辑和 Reroute、Manual Preview/Optimize 隔离及 Store/API 检查通过。守卫只禁止不应调用的入口，没有 mock CAD 成功结果。
- 原始源 Design、SQLite、九个存档及两个 AI task，共 13 个文件 SHA-256 前后与原运行保护清单一致。没有增加项目持久化字段；Model、Save/Reload、Preview、Validate、Build 不创建 AI 续接上下文。
- 没有运行付费 AI、完整复杂 Generate、T-10A、prove、完整无关测试、Vite 或浏览器自动化。未执行复杂全网生产 BRep/STEP 验收，未宣称该工程已制造通过。

复验入口：`.venv/Scripts/python.exe -B scripts/check-phase-b.py --search`；本机完整证据位于 `output/runtime-checks/phase-b-20261013/`，可携带摘要位于 `docs/engineering/phase-b-correctness-evidence.json`。

Phase B 无剩余功能 blocker。原复杂工程的 CAD 错误候选仍待后续路线选择/工程处理；本轮完成的是可靠续接与及时、准确的局部准入，未实施 Phase C。
