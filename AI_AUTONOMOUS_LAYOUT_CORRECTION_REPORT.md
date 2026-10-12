# AI 自主初始设计修正

起始 HEAD：`fdcc881eb10204de1af8618237621b104b5d1d94`；分支 `codex/sqlite-domain-reset`，修改前工作树干净。

## 修改前核实的根因

以下行号均指起始 HEAD，在实施修改前记录：

| 位置 | 已核实行为 | 后果 |
|---|---|---|
| `manifold/ai_design/generation.py:382`、`:438`、`:497` | `_scaffold_faces → packing → circle_layout` 必须先成功，之后才有完整的 Design/Net 和联合搜索 | 未固定的初始面安排可以提前中止生成；搜索没有机会改变面/尺寸 |
| `manifold/ai_design/generation.py:333` | 调用 `initial_placement` 是进入 `layout_plan` 前的强制步骤 | 旧排布方法仍是自主设计的可行性门禁 |
| `manifold/draft_defaults.py:56`、`:119` | 材料建议还混合调用按初始面排布的 `propose_dimensions` | 一个临时排布的失败可能被归为材料/包络不合格 |
| `manifold/ai_design/design_space.py:33`、`manifold/layout_planning.py:212` | AI 域复用 shared `_permissions` 的全局 grow 布尔值；固定 mounting 会使其为 False | 固定安装孔不必要地冻结不影响孔实体的其他尺寸轴 |
| `manifold/ai_design/design_space.py:278` | 主要尺寸提案为 `size + lane`，缩减仅按现有面/坐标边界 | 缺少由源加工深度、不同面组合及固定加工推导的直接尺寸提案 |
| `manifold/ai_design/joint_layout.py:101`、`:127` | 所有候选共享一个按 topology_cost 排序的 heap；只给失败接口安排通用 action 迭代器 | 已生成的近似布局可挤掉尺寸、换面或连接组家族；失败原因没有转为具体动作 |
| `manifold/ai_design/layout_search.py:251` | 没有完整组合时 `route_features` 为空 | 解析安全的部分 Net/失败钻孔证据未成为可用反馈 |
| `manifold/ai_design/joint_layout.py:209` | Exact 结果按 score 比较，没有独立的 acceptance-first 条件 | 可行性等级需要成为显式不变量，而非间接依赖 score |
| `manifold/ai_design/generation.py:658` | 无论是否 Exact 可行都写 `status=draft` | 前端可能显示成功式 Draft 标题，尽管 message 说明未解决 |

## 实施

- `generation.py::candidate` 先编译真实组件/接口/Net。原 `_scaffold_faces`、`packing`、`circle_layout`、`initial_placement` 不再位于该生成调用链上。已有工具函数保留兼容，实际生成入口测试令这些旧门禁抛错，仍完成了真实 Exact/STEP 验收。
- 新增 `initialization.py:15` 的完整源加工范围计算，包括 source cuts、深度、刀尖、安装包络及当前真实壁厚。`:33`、`:78`、`:90` 分别生成构造性面排布尺寸、已放置加工的紧致尺寸，以及尺寸/排布联合提案。圆形排布密度不再是初始可行性证明；不同面组合和两个面内排列方向都可进入搜索。
- `draft_defaults.py` 增加仅新 AI 显式调用的 `defer_layout=True`，把材料事实/强度解析与临时排布拆开。默认 False 的手动行为不变，新增回归覆盖默认路径及显式 opt-in。
- `design_space.py:30` 按世界位姿和完整加工锁定尺寸轴：固定负向面位置、through 深度等会锁相应轴；盲顶部 mounting 保留 Z，同时允许无关 X/Y 改变。父子/非正交、固定 stock、engraving/Block modifier 等仍保守保护。Model 的 shared `_permissions` 原实现未变。
- `design_space.py:121` 用实际源窗口对齐调度可直钻的相对位置，再考虑距离。新联合移动用例曾真实出现 `plug_engagement` FAIL：另一切削体进入堵头啮合区 `0.26684 mm³`。修正后自动得到一条真实钻孔、零堵头的四终端网络；没有改动堵头规则或其严重性。
- `joint_layout.py:139` 按尺寸、换面、连接组、单体及失败反馈进行多样性调度，保留几何去重和延后队列。对无加工差异的轴对称源剖面避免重复旋转。Exact 可行结果单独组成优先集合，Rejected 结果不能覆盖它。
- `layout_search.py` 保存部分兼容路由、失败规则、源阻挡身份和钻孔对；`initialization.py:147` 将这些信息转为相关 Net 的协调换面/重排及源范围尺寸提案。不是重复提交同一固定几何。
- 原 48 布局/最多 2 Exact 默认预算保留。共享 Router 预算及接受标准不变，两个 3D scout 合计至多分配 2048 标签，未增加墙钟截止时间。诊断区分支持尺寸范围与用户显式 envelope；只对有测量依据的硬矛盾给出证明。
- 未 Exact 接受的生成包使用 `incomplete_draft`。未编译的硬坐标/旋转要求保留具体 intent ID、目标和值并阻止重排。已有进度、取消、初始 Draft 快照和显式交付路径保持。

## 真实比较

机器证据：`docs/engineering/ai-autonomous-layout-acceptance.json`；完整 CAD/STEP、规则及原始失败：`output/runtime-checks/autonomous-ai-20261012/`。九个 QA 场景的初始 Design 均从实际结果恢复并通过原 source revision 校验；JSON 还包含可重建的选中 Design 和所用定义。

下列合计深度是生成钻孔的圆柱钻深总和，包括加工入口，不是去重后的管网中心线长度。所有成功行均经过真实连通性、源保护、壁厚、工具/堵头、生产 BRep 与 STEP 门禁。QA 是明确的物理测试剖面，未写入生产库，也不代表厂家批准。

| 场景 | 初始 → 最终 Block / mm | 实际移动或约束 | 钻孔 / 堵头 | 合计钻深 / mm | PASS / WARNING / FAIL | BRep / STEP |
|---|---|---|---:|---:|---|---|
| A：过小，完整生成入口 | 10×10×10 → 51.6×51.6×62.61 | 旧排布函数被禁止调用；使用现有 runtime 测试定义完成生成 | 2 / 0 | 57.455 | 85 / 3 / 0 | 有效，各 1 solid |
| A：源空间不足 | 40×40×40 → 54.02×40×40 | 四 Cavity 沿 X 移动，固定 Port U/V 不变 | 2 / 0 | 96.040 | 139 / 0 / 0 | 有效，各 1 solid |
| B：材料缩减 | 140×140×140 → 140×39×59 | Port 的位置和面不变 | 1 / 0 | 128.000 | 42 / 0 / 0 | 有效，各 1 solid |
| D：位置可放置但难以连接 | 140×110×90 → 同尺寸 | 两 Cavity 平移对齐；初始解析 8 钻孔降到实际 4 | 4 / 2 | 149.000 | 203 / 0 / 0 | 有效，各 1 solid |
| E：Port 不便面 | 140×110×90 → 同尺寸 | Port left → front，U/V 80/40 → 70/72；固定 Cavity 不动 | 1 / 0 | 34.000 | 41 / 0 / 0 | 有效，各 1 solid |
| C/F：三源重合，必须联合移动 | 120×80×70 → 同尺寸 | 三 Cavity 一起移到 X≈25.333/43.343/61.353；单动一个仍留下另外两个重合 | 1 / 0 | 65.353 | 76 / 0 / 0 | 有效，各 1 solid |
| G：硬高度 | 80×80×30 → 同尺寸 | 深 40 mm 的源从 top → left，未扩大禁止的 Z | 1 / 0 | 37.922 | 43 / 0 / 0 | 有效，各 1 solid |
| H：明确固定 | 100×80×90 → 同尺寸 | 全部源 U/V、面、旋转和三尺寸均保持 | 1 / 0 | 88.000 | 44 / 0 / 0 | 有效，各 1 solid |
| I：固定 mounting | 40×40×40 → 52.27×40×40 | 固定顶部安装孔参数及世界位姿不变，只有自由 X 增长 | 2 / 0 | 92.540 | 155 / 0 / 0 | 有效，各 1 solid |
| K：可行与拒绝共存 | 100×100×100 → 同尺寸 | 源窗口旋转 90°；后续候选真实连通性拒绝，仍保留已通过候选 | 2 / 0 | 84.000 | 82 / 0 / 0 | 有效，各 1 solid |

上述十个成功场景的 STEP 体积差最大 `1.1641532182693481e-10 mm³`，均小于已有 `0.01 mm³` 门禁。完整生成入口的 3 个 WARNING 是实际未解决工程事实，详情保留在 JSON；不会把未知工作压力/流量、材料资格或 QA 定义当作制造认证。QA 场景的 `manufacturing_ready` 原值逐项保存，0 FAIL 不等于厂家或压力批准。

另有明确失败案例：CV 源加工深度 40 mm + 壁厚 2 mm 需要 Z≥42 mm，用户同时要求 top 面及 Z≤30 mm。记录为 `PROVEN_HARD_CONSTRAINT_CONFLICT`，不改尺寸/面、不执行完整 CAD，不报通过。自由旋转和软件尺寸上限不能被随意当作用户硬矛盾。

## J：手动隔离及持久化

真实 Save/Reload 后，独立进程禁止 Router 重搜及 AI 初始化/布局入口，再执行 Validate、Build：151 PASS / 0 WARNING / 0 FAIL，8 个完整 Features 的身份、加工、Net 和连接声明保持。显式编辑、冻结、再保存及显式 Reroute 的既有回归通过。

另有真实 Preview/Optimize 检查：即使 `origin.method='ai-assisted'`，禁止 AI 布局入口仍可正常工作，源 Feature 参数和 Block 完全保持。仅显式路由操作可以修改允许修改的钻孔。普通 Model、打开项目和存储路径没有新增自动布局调用。

## L：八阀压力案例及技术限制

没有付费 AI、重新识图或改动原项目。使用现有审核 source-only 拓扑，生成独立 owned IDs。起始 310×245×230 是软起点。

本轮 **48 布局，189 变换，47 重复，5 个源布局拒绝**，用时 **654.640 s**；实际调度包含 19 个尺寸类、19 个换面类、9 个反馈类。一个实际重排把 12 个接口移动至 **116.47×371.66×116.36 mm** 的不同面安排。96 个布局及 52 个动作生成器仍延后。没有完整路由组合，**0 完整 Exact CAD 尝试**，状态 `UNRESOLVED_LAYOUT / UNRESOLVED_SEARCH_OR_ENGINEERING`；没有本轮新 BRep/STEP/完整验证计数。

| 剩余部分 | 本轮证据 | 工程结论 |
|---|---|---|
| A_DC | 四终端：C4:port3、C6:a_A、C5:port2、C3:port2。43 个源布局通过筛查的状态中，解析 source-clear 候选始终 0；记录 source_protected、installation_access、plug_cut 拒绝 | 当前路线生成/接纳未找到同时满足这四个源窗口与完整入口的方案，不能推断无物理走廊 |
| B_DC | 四终端：C4:port2、C6:b_B、C5:port4、C3:port3。source-clear 始终 0；同类源/安装/堵头限制，另有一次 tool_reach | 同时受源窗口/加工入口安排与工具可达限制，仍需找到可接纳的真实多终端钻孔网络 |
| MB | source-clear 范围 0–2；选中的后期布局仍有 MB-PORT/C1 等安装及堵头占用拒绝 | 一些布局有单网解析方案，尚未获得完整全网兼容组合 |
| T_DC / P | 有多条 T_DC 解析候选，保留的布局 34 出现 `cross_net_wall`：`R-5c62e091-5 ↔ R-8e428e23-1`，所属 P/T_DC | 这是解析加工间距见证；没有新 Exact 交叠体积证据，不伪称串油已消除 |
| 3D 展开 | 两轮 scout 分别 924/970 标签、16 协调状态；还有 5/8 个协调状态延后。第二轮 A_DC 的未展开坐标事件为 X/Y/Z=100/152/90 | 走廊展开、候选接纳和多网协调仍未完成，不是物理无解证明 |

原位保留 MA/P 的部分解析路由；后期分别保留 P/SHUTTLE_OUTPUT/T，以及 MA/P/SHUTTLE_OUTPUT/T。它们明确标为 `ANALYTIC_PARTIAL_NOT_EXACT`，不能被当作已验证的完整方案。

对比上一实现的 24 布局/653.234 s，本轮是在约相同观察时间内检查了 48 个更有差异的几何状态；这不是相同负载的性能基准，不宣称固定倍数提速。当前通用自动解决能力已由上表的真实工程案例证明，八阀仍未接受这一限制独立保留。

数据库 SHA-256 前后均为 `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`；原八阀存档均为 `d347a81a002b8f4cd1384359c4c77f71795b22571062940fedb2b1798d41823e`，全部 9 个现有存档及原 source 文件 hash 一致。未改 SQLite、原项目或手动加工。

## 验证及交付

- `acceptance2.log`：34 项通过，包含真实布局/CAD、生成入口、Store/API 和既有源放置检查。初次新增 C/F 的真实堵头侵入失败保留，并通过算法修正解决。
- `isolation-t10a.log`：19 项通过；一个新增诊断测试最初提供了不合法的 QA 安装包络，已改为满足 schema 的完整定义，单独重跑通过；没有绕过源验证。
- `generation-final.log`：19 项通过，包含未编译硬位置阻断和默认手动材料路径、取消/初始 Draft、实际进程交付。
- `authority-final.log`：3 项通过，覆盖硬深度矛盾、支持范围/显式限制区别和共享材料默认 opt-in。
- `manual-preview-optimize.log`：1 项通过；真实 Preview/Optimize 禁止进入 AI 布局，源/Block 不变。持久化子进程另有 151/0/0。
- 最后 `delivery-api2.log`：20 项通过；包括硬约束人类可读消息、生成状态、取消、真实工作进程及 Store/API。
- 相关 JS 3 项通过：未解决包显示 needs review，只有显式 Open 才交付到 Model；历史路由恢复保持显式。
- 真实 T-10A：607 PASS / 0 WARNING / 0 FAIL，四种设计优先级/Pareto 回归通过。
- `python -m manifold prove`：invalid 295/2/6，corrected 268/1/0，原始失败与修正证据均保留。
- 静态语法与 diff 检查通过。未运行浏览器、Vite、广泛审计或付费 AI；未宣称所有历史套件通过。

修改范围：AI `generation / design_space / joint_layout / layout_search`，新增 `initialization`，共享 `draft_defaults` 的显式 AI opt-in，以及聚焦 Python/JS、此报告和机器证据。Shared Router、Model 布局工具、验证规则、项目 schema、生产数据库和 Drawing 均未修改。

最终提交、远端 HEAD 和干净工作树通过实际 Git 查询交付，并记录在本机 `output/runtime-checks/autonomous-ai-20261012/delivery.json`；大型 CAD/原始诊断、活跃 DB 和原项目不提交。
