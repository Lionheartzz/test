# Routing-aware layout and remaining cross-Net conflicts

起始 HEAD：`c22fa51aaeff539a9e87af075870b3a1b1f7ef81`。分支：`codex/sqlite-domain-reset`。起始工作区干净。

本次仅用存档、只读 SQLite、代码检查、静态语法检查和 diff-check。**没有生成新 CAD；不能宣称以下两组碰撞已经消除。** 最终提交与远端 SHA 在交付回复中给出。

## 真实案例与可确认归因

- 最新完整预览 trace：`output/cad-diagnostics/1051e44ed05943af98af1ad4b585272b.json`。
- 对应 Draft：`output/ai-design/343f91fdb98c435296b6e78322157433/generations/a3cc8888edfc4792a35f22290e262e81/authored-draft.json`。通过特征身份与位置关联；trace 没有 project_id。
- 保存的块为 255 × 170 × 115 mm，6061-T651 extruded bar / ASTM B221；8 cavities、4 ports、15 nets。工作压力和流量仍未知。
- 存档预览耗时 120.078 s，路由约 107 s。**该存档的 production_valid=true**；本次问题是跨 Net 液压接触，不能把它与旧案例的无效 BRep 混为一谈。
- 渐进修复：76/256 个状态、440/4,000 次新配对筛选，退出原因为 `bounded_neighbourhood_exhausted`。不是此阶段预算耗尽。
- 渐进修复保留池中，`MB_CBCG2_to_DSCS` 和 `T` 均为 0 个源安全候选。空池只证明当前候选覆盖不足，不证明任何布置都不可制造。

| Exact Net 接触 | 存档支持的特征归因 |
|---|---|
| MB_CBCG2_pilot ↔ MB_CBCG2_to_DSCS：6.73070475 mm³ | 唯一包围盒候选是 `CV_326c4259d011c3bddf7c:port1` ↔ `R-489f6472-1`。结合正的 Exact Net 交集且没有候选截断/检查错误，可唯一定位到这对；没有保存其单独 Boolean 体积。 |
| MB_CBCG2_to_DSCS ↔ T：417.42485778 mm³ | 四个原始候选对见下。解析排除 T 外部油口那一对；源坐标与现有 port-stem 方程进一步证明 T 接入直段侵入 C4 port2，指向 trace 中的 `R-e632b709-3`。逐对 Boolean 体积分摊没有保存。 |

第一组中的 cavity 是 C4 / CBCG / T-11A，定义 `cav_000ea3efc223ffbed29f`。它的 **port1 是 MB_CBCG2_pilot**，深度 69.245–76.43 mm；**port2 是 MB_CBCG2_to_DSCS**，深度 50.83–68.31 mm。问题是另一 Net 的钻孔进入了错误窗口，不是窗口身份可任意互换。

第二组原始候选为：

1. C4 `port2` ↔ `PORT_c98827167821177e0339`（T-PORT）。
2. C4 `port2` ↔ `R-e632b709-3`。
3. `R-489f6472-2` ↔ `R-e632b709-3`。
4. `R-489f6472-2` ↔ `R-e632b709-4`。

其中 1 可用保存的源尺寸解析排除：C4 port2 按真实切削轮廓裁剪后半径不超过 10 mm；T-PORT 为 Ø24.5 mm、12 mm 柱深、118° 钻尖。源坐标给出钻尖 Y=150.63945742 mm；包含整段柱孔和钻尖的支撑半空间与源窗口包络柱之间有 **0.39382850 mm 的正分离下界**。计算使用源轮廓、源位置和钻尖方程，没有构建 BRep；这不是 OCCT 距离，也不证明所需壁厚或整体制造合格。源油口仍可能占用某些路由入口空间。

真正的关键是 Router 的接入延长段：保存的条件没有压力/wall floor，现有 `port_stem()` 在 T-PORT 后采用 `12 + 24.5/2 + 8/2 = 28.25 mm` 的同轴转向深度，直段覆盖 Y=141.75–158 mm。点 **(170.70068489, 144.17636977, 58.47125) mm** 严格位于这个 Ø8 直段内部（距轴 2 mm），也严格位于 C4 port2 的真实源切削柱内部（局部深度 56.52875 mm；距 cavity 轴 7.42431511 mm，小于真实半径 9.295 mm）。这是保存源数据/既有策略的内部点证据，没有执行路由器或生成新 CAD。

所以 T 外部油口本身可不串油，但当前接入策略将它继续延伸后会串入 C4。C4 port2 对 T 生成钻孔的唯一存档候选是 `R-e632b709-3`；仍不能给出它或另外两个钻孔对各自的 Boolean 体积。仅更换同样接入直段之后的 XYZ 顺序/绕障平面无法消除这个必经段的冲突。需要移动可编辑油口/元件、增加合适的入口空间，或另行建立经过源几何验证的终端策略；本次不通过缩短保护范围来绕过它。

解析筛选已拒绝最终组合中的以下关系：

- `source_protected(C4, R-489f6472-1)`。
- `source_protected(C4, R-e632b709-3)`。
- `cross_net_wall(R-489f6472-2, R-e632b709-3)` 和 `cross_net_wall(R-489f6472-2, R-e632b709-4)`。

存档选中的 MB 支路是 `xyz:nearest:planes_0_238.601370`，T 是 `xyz:nearest:planes_1_120.047928`，pilot 是 `axial_1_0:xyz:nearest`。它们没有被误报成安全路线：相关 Net 已保留为未解决状态。最终钻孔坐标/单对交集没有保存，不能仅凭体积断言第二组的每个候选都相交。

## 选择/修复为什么停住

旧全局组合搜索遇到任一空池就返回，后续按 Net 名称依次选路线；在没有源安全候选时仍保留最少失败的提案。渐进修复的两个空池又无法提供替代。当前数据证明的是 **T 接入策略与当前油口/C4 布置直接冲突，以及两个保留候选池为空**，不是必须增加搜索预算；它没有证明必须扩大块或必须移动某个指定阀。

代码还存在一个候选保留缺口：原始路线含多余临时连接钻孔时，会在裁剪前因源保护失败被排除，因而没有机会在连通性裁剪后重新接受保护检查。本次修正这个缺口，但未通过新运行证明该案例因此获得可行路线。

## 共用路由修正

- 全局组合使用最少剩余兼容候选优先，逐层前向检查其他 Net 是否失去最后一个候选；仍按既有完整制造目标比较可行组合。
- 全局组合不成立时，使用源安全池建立联合回退种子：候选少的安全 Net 先选，空池 Net 最后选；候选与已选路线共同筛选，不再仅按名称独立回退。
- 空的原始安全池可以使用原本未花费的 **16 个 expanded-family 裁剪名额**，裁剪后必须重新通过源保护、壁厚、堵头、入口和连通性检查。没有放宽准入规则。
- 组合仍最多 1,000 状态/4,000 新配对筛选；渐进修复仍 256 状态/4,000 配对/beam 4；没有扩大 exact CAD 尝试预算或恢复墙钟截止时间。
- 诊断区分空的保留安全池、状态/配对预算、保留池不兼容、连通性失败。空池不被解释为“物理不可能”。实际失败几何继续保留为 stale/unresolved。
- incremental preview 继续保留未受影响路线；它与全局/authoritative 路径复用候选与组合逻辑。

## 共用布局规划与显式建议

新 `layout_planning.py` 复用普通 Router 的 `propose()`、源定义派生的 axial eligibility、`obstacle_safe_planes()`、闭合入口规范化和 `route_obstructions()`，不创建第二套 AI 路由引擎，也不在 Generate 调用 exact 裁剪、BRep 或 STEP。

- 初始尺寸为源窗口深度带内竞争的不同 Net 留出按实际孔径和既有 wall 计算的通道间距；不是固定百分比，也没有新增通用壁厚。
- 通道间距是规划偏好，不是新硬规则；遇到显式/继承尺寸限制时，可以回退到原来的源占位与 access gap，再保留路由疑问，而非据此宣称项目不可制造。
- 单 Draft 的初始布局最多比较 **4 个解析布置**，每 Net 最多保留 8 个解析通道样本、尝试 32 个样本。考虑源窗口、正交入口面、深度、刀具 reach、Plug/access、不同 Net 冲突和实际制造目标。这个小样本不是可制造性证明。
- Model → Hydraulic Nets 的 **Review layout alternatives** 调用只读 `/api/layout-proposals`，最多比较 **8 个解析布置**并返回最多 3 个改进建议。
- 建议包括同面未提交 cavity 交换、将外部油口对准实际所属窗口、增加按孔径/间距计算的加工通道并协调居中。尺寸增加以 mm 表达，显式 min/max 保持不变。
- 面板逐项列出旧/新 U/V、块尺寸、解析问题数量和将重算的未提交 Net。只有 **Apply to editable draft** 才应用，可 Undo；不自动保存、不替换 committed/frozen/manual 钻孔。应用会记录既有 Engineering Review 决策，而非要求额外文本确认。
- 与固定路线/手工钻孔关联的接口、parent 关系和特殊方向不自动移动；存在固定加工/路线时不扩大块。建议不能增加保留钻孔的解析冲突。明确应用后，共同重算可编辑路线提案；保留路线仍按原规则处理。
- 初始规划只作用于新建项目。项目 Load、Save、Validate、Build、Drawing 不调用初始重排。

## 后续 Exact 证据

Exact Review 仍报告原来的 Net 交集。仅针对已有碰撞，额外使用**已经裁进块内的液压节点**保存真实 feature-pair 交集体积，整次预览最多新增 64 个配对计算；不足时显式标记 attribution incomplete。没有新建第二个生产 BRep，不新增跨 Net 授权。

trace 保存源 revision、实际接触特征的加工坐标/定义 ID、逐对体积及搜索退出原因。包围盒候选仍明确标为 suspects。Exact 接触不会覆盖已知的空池/预算原因，也不会被当作正常可提交提案。

## 保护与本次检查

- SQLite SHA-256 前后：`1E3267BD6A6271CF819B5181ED52EAE55AB8B8B54A4A48CE45CC277175D7DAA2`。
- AI provider 配置 SHA-256 前后：`2585ED2E0E32FF5677CF0D3136FDD948F7A9C9CF951EB6683DF969CF742E190A`。
- 保留自动材料选择、未知压力/流量、可见预览进度、source protection、minimum wall、闭合/刀具、same-Net 合法连接、保存/验证/committed route 规则。未改 Stage 1、SQLite、源尺寸或 Drawing。
- 已做 Python AST、JS `node --check` 和 `git diff --check`；不导入执行新规划器。
- **未做测试、浏览器、Vite、CAD/prove/STEP、AI 调用或基准运行，未构建/重启服务。** 新候选数量、布局建议质量、时间和两组碰撞的消除仍需要后续真实 Exact Preview；不能给出新 0 FAIL 或制造通过结论。

修改文件：`manifold/layout_planning.py`、`layout.py`、`routing.py`、`geometry.py`、`cad_worker.py`、`server.py`；`web/workflows.js`、`web/main.js`；本报告。
