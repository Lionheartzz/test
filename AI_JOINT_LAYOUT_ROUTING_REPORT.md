# AI 自有候选：联合布局、尺寸与可制造路由

起始 HEAD：`18e6ec8eb825c75f22e45e6951da635198574fe3`。分支：`codex/sqlite-domain-reset`。

## 根因与修正

原生成路径把继承的 Block 尺寸当作锁定尺寸，把全局偏好面当作固定面；只比较少量解析布局，主要依赖列式布局和分支路由，不能发现移动源窗口后出现的直接钻孔。固定端口也没有在重排开始时作为障碍处理。

现在 `generation → layout_search.plan_new → joint_layout.optimize` 只对新生成、明确拥有的 Feature 集合搜索。初始排布先保留，之后按实际源窗口、完整源加工范围、安装包络、Net 邻接及余量生成坐标事件：单个接口移动、连接组重排、源窗口旋转、六面候选、插入加工走廊、尺寸增长并重排，以及回收无用材料。原列式排布仅作为一个可选起点。

解析评价复用共享 Router 的 simple/direct/axial/detour/port/tree 候选及全网组合筛查；必要时使用同一个 3D 钻孔规划器作一次有界细化，然后回到布局修改。只有完整钻孔网络才进入独立 Exact 工作进程；真实连通性、开口、源保护、壁厚、工具/闭合、生产 BRep 和 STEP 使用已有门禁。没有改 Router 的接受规则、源几何或 SQLite。

工程可行性优先。可行后保持现有设计优先级的堵头/钻孔/深度/包络次序；跨不同 Block 尺寸的比较在已满足壁厚门禁后，把材料体积放在额外壁厚质量余量之前。固定几何 Router 的四种目标未改动。

默认每次生成 48 个布局状态、最多 2 个 Exact 布局；最大值是计算预算，不是固定层数或方案能力假设。共享 Router 的已有预算不变，不设墙钟截止时间。延后的布局和未展开生成器有计数，失败不等于物理无解。

## 约束与所有权

- 硬约束：明确的 envelope、每个接口的必需面、工程师逐项选择、受保护/关联几何、手动/冻结/提交加工、显式固定坐标或旋转。
- 软偏好：新生成或继承的普通 Length/Width/Height、全局偏好面、非强制设计意图。不会转写成新的 envelope 上限。
- 固定面内 U/V 不会顺带锁死法向 Block 尺寸；显式全局坐标另行检查。未能可靠编译的源坐标要求保留为 blocking review，不猜测位置。
- 只有生成过程传入的 owned IDs 可以移动；`origin.method == ai-assisted` 不授予任何权限。已有父子、非正交、手动/冻结/提交条件进一步收紧所有权。
- Model、Preview、Reroute、Optimize Routes、Validate、Build、Save/Reload 不调用该搜索，也不获得尺寸/位置修改权。后续布局变化仍需要 Review/Apply。

初始 `authored-draft.json` 在优化前发布，通过现有 generation/project API 可读。取消后返回并登记这个可重新打开的 Draft。最终结果是独立 Design 值，不能覆盖已在 Model 打开的初始值。进度复用原工程作业/Exact executor；没有新计时器或假百分比。

## 真实 CAD 验收

机器可读证据：`docs/engineering/ai-joint-layout-acceptance.json`。完整本机证据：`output/runtime-checks/joint-ai-20261012/final-verification/`。

以下 QA 源剖面明确来自测试定义，不是假冒厂家数据，未写入工程主库。钻孔、连通性、Boolean、规则检查和 STEP 均真实运行；QA 定义的用例仅绕过跨进程传输以传入定义对象，不伪造规划或验收结果。

| 用例 | 实际选中变化 | 选中钻孔/堵头 | PASS/WARNING/FAIL | BRep / STEP |
|---|---|---:|---|---|
| 双网四 Cavity 重排 | 两 Cavity 移动；初始解析 8 钻孔降至实际 4 | 4 / 2 | 203 / 0 / 0 | 有效，各 1 solid |
| 功能 Port 移动 | 固定 Cavity/Block；Port 从 left 改到 front 并对齐真实窗口 | 1 / 0 | 41 / 0 / 0 | 有效，各 1 solid |
| 不足空间 | 40×40×40 → 54.02×40×40；四 Cavity 分离；固定 Port U/V 不变 | 2 / 0 | 139 / 0 / 0 | 有效，各 1 solid |
| 两个偏置窗口旋转 | 固定 Block/Ports；源窗口旋转 90° | 2 / 0 | 82 / 0 / 0 | 有效，各 1 solid |
| 硬高度限制 | 80×80×30 不变；深 40 mm 的 Cavity 从 top 改 back | 1 / 0 | 43 / 0 / 0 | 有效，各 1 solid |
| 回收无用材料 | 140×140×140 → 140×39×59，固定 Port U/V | 1 / 0 | 42 / 0 / 0 | 有效，各 1 solid |
| 实际独立 CAD 工进程 | 传递完整钻孔 Features，不使用内存候选身份 | 见 JSON | 151 / 0 / 0 | 有效，各 1 solid |

前六例 STEP 体积差最大 `1.1642e-10 mm³`；独立工作进程例 `4.3173e-5 mm³`，均小于既有 `0.01 mm³` 门禁。所有适用 connected_interface、circuit_connectivity、跨 Net 隔离、源保护、壁厚、闭合及工具检查无 FAIL。除完整 stock-only QA 例外，QA 源定义不具备生产制造批准，报告保留其 `manufacturing_ready=false`。

另验证受保护几何无权修改时保持原样且不标 Exact 通过；真实工作进程能返回连通性拒绝和缺失边，不会把工程拒绝当作传输错误。没有钻孔网络的解析候选不会被计作完整 CAD 尝试。

## 八阀真实来源候选

源为已有审核拓扑的 source-only Design，复制为新的 AI-owned IDs；原项目、源文件、工程库受 hash 保护。没有付费 AI、重新识图或改写原存档。

最终离线结果见 `output/runtime-checks/joint-ai-20261012/reviewed-eight-release/`，预算为 24 布局/最多 2 Exact，与对比运行一致。用时 **653.234 s**；24 布局、384 变换、105 重复变换、257 延后布局、27 未展开生成器。没有完整全网钻孔组合，所以 **0 完整 Exact CAD 尝试**，状态 **UNRESOLVED_LAYOUT**，validation/BRep/STEP 均未建立。没有新验证计数或制造批准。

候选 0 与拓扑重排候选 6 分别使用共享 3D scout 的 16 个协调状态、924/953 个标签，仍有 5 个协调状态待展开。后者移动 11 个接口，并非只把原排布等比放大。原位解析池的 MB、A_DC、B_DC、T_DC、SHUTTLE_OUTPUT 无 source-clear 保留方案。A_DC 首次搜索仍有 X/Y/Z 坐标事件 129/66/139 未展开，重排后为 124/66/124；T/T_DC 有解析候选待接纳。此证据支持“走廊展开及候选/协调预算受限”，不支持“物理无可用空间”或“固定加工/源数据必然无解”。没有借此盲目增加预算或虚构连接。

DB SHA-256 前后均为 `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`；原八阀存档前后均为 `d347a81a002b8f4cd1384359c4c77f71795b22571062940fedb2b1798d41823e`，全部 9 个现有存档及源文件 hash 不变。八阀仍未接受；通用联合优化器的真实通过证据与该限制分开报告。

此前 `reviewed-eight-final` 的对比运行实际评估了连通组、尺寸增长并重排、插入走廊、缩减材料及接口移动。一个送检重排同时移动了 11 个接口并改变多个面/旋转。但两个提交结果均没有完整路由网络，在连通性门禁被拒绝；没有建立完整生产 BRep 或 STEP，也没有新的完整验证计数。该过程的诊断错误已修正，原始失败证据仍保留。不能把它与上一提交固定八阀的 4206/38/21 混为同一次结果。

## 验证与限制

- 当前通用几何用例、真实 T-10A、Save/Reload/独立进程验证、手动/冻结保留：24 项通过；新增选择确认测试最初因测试输入缺 `nets` 失败，已修复并在后续聚焦检查通过。
- 最后生成/API/Store/真实拒绝传输检查：16 项通过，包含取消后的可打开初始 Draft、初始/最终独立值、明确约束错误、软尺寸/硬 envelope、面内/全局坐标区别及缓存等价性；未建立完整验证的候选计数保持 null，不显示假 0 FAIL。进度布局编号另有 1 项真实工作进程检查通过。
- 前一次完整聚焦集：35 项通过，包括旧生成偏好、显式固定变体和恢复接口。
- 四种优先级/增量预览检查：10 项通过、2 项失败。两项失败在起始 HEAD 独立 Python 副本、同一个 DB 上重跑原样复现（740 PASS / 0 WARNING / 4 FAIL），属于既有端口移动用例的 Exact 接受问题。局部依赖范围和未影响 Net 保留断言均通过；没有扩展本任务去重写 Router。
- T-10A：607 PASS / 0 WARNING / 0 FAIL；保持完整候选 Pareto 检查。
- `python -m manifold prove`：invalid 295/2/6，corrected 268/1/0，保留失败与修正证据。
- 相关 JS：9 项中 4 通过、5 失败；在起始 HEAD 的独立副本重跑得到完全相同失败。4 项为旧 DOM harness 缺 `addEventListener`，1 项为旧文案断言。本次无 JS/UI 修改，未运行 browser/Vite 或广泛测试。
- Count 预算下不证明全局最优或物理无解；没有足够证据的源位置、安装方向/体积、工程负载仍需 review。不得由 QA 0 FAIL 推导厂家或压力认证。

提交、远端 SHA 及最终干净工作树由交付时实际 Git 查询确认；大型诊断/CAD、活跃 DB 和原项目不进入提交。

## 修改文件

`manifold/ai_design/`：generation、generation_models、intent、jobs、layout_search，以及新增 design_space / joint_layout；共享层只涉及 layout 的可选操作内剖面缓存和软尺寸参数、draft_defaults 的显式 opt-in、cad_worker 的私有 AI Exact 操作。新增离线脚本 `scripts/evaluate_ai_layout.py`，调整两个既有 AI 测试并新增两个聚焦测试文件，交付本报告及机器可读验收 JSON。没有改 schema、工程数据库、手动 Router 或前端。
