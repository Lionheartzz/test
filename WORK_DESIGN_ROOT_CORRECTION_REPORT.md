# 单工作设计工程布局根因整改

基线 `d49815ac26ecda1decd136f0f77cd25a23fc1a20`，分支 `codex/sqlite-domain-reset`。

**三个已确认的决策缺陷已整改；复杂工程仍未制造验收。** 本轮没有完整复杂 Generate、旧 Catalog、三维标签搜索、数据库修改或 CAD 规则放宽。

## 根因与实现

- 原 Top scaffold 被直接继承，`spacing()` 对同面所有元件施加单轴全排序，`groups()` 又把传递连通分量当成排列组。逐个最小化当前体积还会把前三个元件锁成条带。
- `design_space.py:69` 将未锁定 AI Cavity 的默认域设为 Top/Front/Back/Left/Right；硬 Bottom 优先，Port 的独立六面域不变。`generation.py` 的 scaffold 同步排除默认 Bottom。固定 U/V 保留安装坐标系，固定 Rotation、未拥有/受保护元件保持原权限。
- `engineering_plan.py:106` 从 Net 超图生成直接加权邻接：每个超边对源邻接贡献 `1/(源数量−1)`，多 Net 分别累加，窗口始终属于一个刚体。没有按名称或阀数量分支。
- `source_arrangement.py:17` 在一个 WorkDesign 上按硬约束、耦合和实际包络定位；从五面、真实投影边界和窗口对齐事件选择坐标，非圆安装轮廓使用旋转后投影。直接关联元件的面积完成量估计避免贪心条带；不是硬行数、面配额或全局布局组合。
- `single_design.py:133` 按实际分离投影保留二维关系；圆形使用 `Ri+Rj+Gij`，非圆形使用投影支持值与真实 wall/access gap。跨面种子约束只作用于本次构造的布局，不把原 Port scaffold 变成额外锁定。
- `corridor_planner.py:110` 比较真实窗口对齐位移、三主轴、两入口、正/负逃逸、源支持、实际闭合占用、完整外钻深度及工具能力；`single_design.py:53` 不再直接取未评价的 `choices[0]`。这些是工艺调度估计，随后必须经过 materialize 和生产完整加工检查。
- `single_design.py:290` 对真实最小正权环做条件约束传播并修改相关主轴/逃逸/轴向策略/平面等式。失败缓存包含整个 DecisionState；旧 Net 组合下的失败不能排除新组合下的同一工艺。仅选择的充分约束域被否定，不形成跨几何物理禁令。
- `single_design.py:517` 优先真实入口，再比较局部工艺轴/逃逸，最后使用测量分离量移动源/加工坐标。全部保留孔参与生产筛查。失败事务依赖完整保留切削体，回滚恢复 operations；`affected():491` 包含真实安装轮廓、外向高度及第三方扫掠关系。`circular()`/`source_conflicts()` 均使用待查 Target 的 Block。

## 新复杂源布局

下表是生产约束求解和源安装检查后的实际坐标；显示值四舍五入，JSON 保留完整精度。所有调整仅属于这次新的 AI-owned 工作值，未写回原项目。

| 元件 | Feature | 面 | U / mm | V / mm | Rotation |
|---|---|---|---:|---:|---:|
| RDDA relief valve (top, T-10A) | `CV_d801cc17353335611c26` | front | 144.667867 | 123.475000 | 0 |
| RDDA relief valve (middle, T-10A) | `CV_dd1233e37c21224f33b1` | top | 168.854220 | 140.447706 | 0 |
| CBCG counterbalance valve (left, T-11A) | `CV_e8794e1429030d0effc5` | front | 36.425000 | 89.725000 | 0 |
| CBCG counterbalance valve (right, T-11A) | `CV_7449bf25918d56b5a4fc` | left | 111.800000 | 105.075000 | 0 |
| DSCS shuttle valve (T-31A) | `CV_510aeef818a9e0c92d08` | front | 70.175000 | 55.975000 | 0 |
| 4-way directional control valve AH4D102a/f | `CV_6bbcdb6cce3a4c816cb3` | top | 99.967867 | 71.561353 | 0 |
| RBAA relief valve (T-3A) | `CV_815381a85b2940cd0140` | front | 148.627867 | 19.050000 | 0 |
| LRHC logic valve (T-17A) | `CV_2c444cf8c8f7333d939e` | left | 174.997706 | 64.975000 | 0 |
| MA external port | `PORT_6d31ed2bd8add71e5a63` | bottom | 94.400000 | 71.335000 | 0 |
| MB external port | `PORT_2ff53e755aecdd3ecd26` | right | 164.672706 | 78.775000 | 0 |
| P external port | `PORT_ff005d98b5f75bf1aa24` | top | 90.680000 | 170.572706 | 0 |
| T external port | `PORT_27ddec688c9b93eac4f8` | right | 167.397706 | 55.000000 | 0 |

选择原因逐项保存在 JSON 的 `decisions/HYPERGRAPH_SOURCE_ARRANGEMENT`：直接邻接权重、实际包络、允许面、投影面积和预计加工长度均可回查。侧面长 Cavity 的深度沿自身法向计算；Top 大安装轮廓与多窗口源按所有关联 Net 共同定位。Port 的 Bottom 属于其原有独立允许域，不代表 Cavity 默认开放 Bottom。

Block = **205.279220 × 217.772706 × 139.350000 mm**。
尺寸从源深度/安装投影、真实中心距、跨面分离、干线层、支路列、真实闭合占用和轴向安全停止区间联合传播，不是 Cavity 直径求和。实际紧约束：

- X：MA/MB 走廊的外端 14 mm 余量；MB 的来源轴向窗口区间也绑定该上界。
- Y：P 走廊外端 14 mm 余量。14 mm 来自已绑定闭合占用 10 mm + bore radius 4 mm；没有虚构压力 wall。
- Z：Front RDDA 的实际安装投影上支持 15.875 mm。对面深度只在实际横向投影重叠时相加。

这些空间仅证明当前工艺约束可表达，不证明其内的所有真实钻孔安全；压力、流量等 UNKNOWN 仍保留。

## 八条 Net 的当前工艺

| Net | 主轴 / 入口 | 逃逸 | 轴向来源窗口 | 真实孔数 | 前置结果 |
|---|---|---|---|---:|---|
| A_DC | X / positive | 正 | 径向窗口 | 9 | {'installation_access': 2, 'plug_cut': 2, 'source_protected': 3} |
| P | X / positive | 正 | CV_6bbcdb6cce3a4c816cb3:P, CV_2c444cf8c8f7333d939e:port1 | 9 | {'cross_net_wall': 2, 'installation_access': 1, 'plug_cut': 2} |
| T | Y / positive | 负 | 径向窗口 | 8 | {'installation_access': 1, 'plug_cut': 1, 'source_protected': 1} |
| SHUTTLE_OUTPUT | Y / negative | 负 | 径向窗口 | 5 | {'installation_access': 1, 'plug_cut': 1} |
| MA | Y / positive | 正 | CV_dd1233e37c21224f33b1:port1, CV_e8794e1429030d0effc5:port1 | 11 | 加工筛查清晰；连通性尚未 CAD 准入 |
| MB | Z / positive | 正 | CV_7449bf25918d56b5a4fc:port1, CV_d801cc17353335611c26:port1 | 10 | {'installation_access': 1, 'plug_cut': 1} |
| T_DC | X / negative | 负 | 径向窗口 | 5 | {'source_protected': 1} |
| B_DC | Y / negative | 负 | 径向窗口 | 9 | {'installation_access': 1, 'plug_cut': 1, 'source_protected': 1} |

所有表内路线均由生产 `propose/axial_route` 生成完整 Features，并绑定真实闭合定义。选轴先比较外钻深度、入口限制和窗口对齐；后续变更逐项携带实际 cycle 和条件依赖。没有把全部 Net 固定为 X/negative。

## 原 T_DC/P/T 正权环

原始真实数据复验得到 Y 上 `T_DC→P→T→T_DC`，每边 11.1 mm（闭合入口半径之和 + 既有 access gap）。首次针对性决策将 T_DC 主轴 X 改为 Y，原环消失；继续传播其他实际约束，最终整个原约束域求解成功。新的五面工作布局同样没有 process_gap。完整初始环、窗口成员、源 Cavity、每次工艺修改和最后的坐标域均保存。
这不是把 planar 设为 false 后退出，也没有恢复 Catalog。原布局工艺重算后的实际钻孔仍有违规，测试明确要求它们继续被生产门禁拒绝。

## 真实违规、局部修复与剩余 blocker

- 旧固定几何的 source_protected 524.2981254966872 mm³、plug_cut 66.39930264676538 mm³ 均按原输入复验，依然被拒绝。后者明确是 R-e632b709-8 的已安装堵头与 R-e632b709-3 完整加工体相交；没有用两个堵头的包络替换实际关系。
- 新布局的源安装检查通过，但七条 Net 的当前真实工艺仍不安全。具体失败对如下；完整孔参数和测量证据在 JSON/原始记录中。

| Net | 实际失败项 |
|---|---|
| T | installation_access / R-e632b709-2 / R-e632b709-4; plug_cut / R-e632b709-2 / R-e632b709-4; source_protected / CV_e8794e1429030d0effc5 / R-e632b709-6 |
| A_DC | installation_access / CV_6bbcdb6cce3a4c816cb3 / R-702e7749-8; installation_access / R-702e7749-2 / R-702e7749-3; plug_cut / CV_6bbcdb6cce3a4c816cb3 / R-702e7749-8; plug_cut / R-702e7749-2 / R-702e7749-3; source_protected / CV_6bbcdb6cce3a4c816cb3 / R-702e7749-8; source_protected / CV_7449bf25918d56b5a4fc / R-702e7749-4; source_protected / CV_dd1233e37c21224f33b1 / R-702e7749-1 |
| B_DC | installation_access / R-309be2fb-6 / R-309be2fb-7; plug_cut / R-309be2fb-6 / R-309be2fb-7; source_protected / CV_6bbcdb6cce3a4c816cb3 / R-309be2fb-3 |
| T_DC | source_protected / CV_510aeef818a9e0c92d08 / R-8e428e23-5 |
| P | cross_net_wall / PORT_27ddec688c9b93eac4f8 / R-5c62e091-AX0; cross_net_wall / PORT_6d31ed2bd8add71e5a63 / R-5c62e091-AX1; installation_access / R-5c62e091-6 / R-5c62e091-7; plug_cut / PORT_27ddec688c9b93eac4f8 / R-5c62e091-AX0; plug_cut / PORT_6d31ed2bd8add71e5a63 / R-5c62e091-AX1 |
| SHUTTLE_OUTPUT | installation_access / R-f623208d-4 / R-f623208d-5; plug_cut / R-f623208d-4 / R-f623208d-5 |
| MB | installation_access / R-1d09f6fa-6 / R-1d09f6fa-7; plug_cut / R-1d09f6fa-6 / R-1d09f6fa-7 |

仍未收口的机制：当前每 Net 仍用一个交汇点及所选外钻分支顺序。充分线性走廊域没有兑现所有第三方源保护、真实 Port 入口和每个分支的堵头/安装占用；生产筛查准确揭露了这一差异。局部入口/分离机制不能据此保证存在全网合法的多交汇安排。本轮未证明所支持的全部替代工艺均不可行，也未全面展开其他分支树。
已验证通用局部入口修复会保持源和 OTHER Net 不变，真实 Exact/BRep/STEP 接纳；相关源改变时，全部窗口、相关 Net 和经过安装/切削扫掠区的第三方路线重新检查，未变化路线保留。失败缓存完整依赖防止旧第三方孔阻止新的合法事务。
**复杂工程完整 Exact、BRep、STEP 没有执行，也没有制造通过声明。** 不能用符号无环或单 Net source-clear 代替连通性、直接开口或完整制造验收。

## CAD UNKNOWN 的独立判断

原固定最小几何被拆成六组真实正体积交集并保存 BRep。S0:w0/钻孔交集的质心截面约 0.031 s 返回；S1:w0/R-f42d38c6-1 的 323.9576661325285 mm³ 合法交集，在第一方向 Z 的实体/平面 Common 停滞。串行 Boolean、对原操作数先截面再求交、clean 后求交均在相同 8 s 隔离上限内未完成，保持 UNKNOWN。
因此不能归因于未生成通道或缺少源定义；停滞属于已定位的原生 CAD 运算。容差/退化曲线敏感是尚未确认的解释，未更改容差、平面、直接接触规则或共享 flow.py。独立操作记录和 BRep 全部保留在 `opening/`。
新位置/加工方向的共享刚体三 Net 见证通过生产 Exact（103/0/0、单实体、STEP 往返）；这证明该新几何可接纳，**不表示旧固定几何的原生运算问题已修复**。

## 实测时间与验收

| 工作阶段 | 调用数 | 秒 |
|---|---:|---:|
| single.compile | 1 | 0.172000 |
| single.net_associations | 6 | 0.000000 |
| single.face_placement | 1 | 2.593000 |
| single.process_decision | 2 | 0.048000 |
| single.coordinates | 499 | 9.238000 |
| single.materialization | 1 | 0.110000 |
| single.precheck | 1 | 1.047000 |
| single.source_envelopes | 22 | 0.217000 |

复杂快照本次私有进程总耗时 18.297 s；完整加工 materialize 仅一次，499 次是实际线性约束传播，不是 499 个布局、钻孔 Catalog 或三维标签。工程定义/原生 CAD 前置运算次数见 JSON；未碰到执行上限。

旧负例一次 local repair：源侵入 3.016 s；堵头 2.781 s。两者仍拒绝，不构造成功。生产默认 600/120/90 s 及取消/部分 Draft 保存机制未改。

| 真实通用见证 | Exact PASS/WARNING/FAIL | BRep / STEP |
|---|---|---|
| 仅入口局部修复 | 112/0/0 | valid / 1 solid / STEP PASS |
| 正常单工作两 Net | 93/0/0 | valid / 1 solid / STEP PASS |
| 共享刚体三 Net | 103/0/0 | valid / 1 solid / STEP PASS |
| 三方向 Net 工艺 | 157/0/0 | valid / 1 solid / STEP PASS |

聚焦验证覆盖五面真实加工、硬 Bottom/U/V/Rotation、二维面积定位、直接超图邻接、真实旧约束环、换面 Target、安装扫掠依赖、禁用入口、全部保留孔缓存依赖、原有真实 CAD 见证。Manual/API 验证覆盖 AI-origin Model 的 Preview/Optimize 不进入 AI 布局、部分 Draft 的 Save/Reload/Validate/Build、不隐式搜索，以及 Store 乐观 revision/API 守卫。
最终成功的聚焦日志为 final-validation.xml、manual-api.xml、repair-dependencies.xml；早期失败和所有原始运行目录原样保留。未运行 T-10A、prove、广泛套件、浏览器、Vite、付费 AI 或新的完整复杂 Generate。

## 隔离与交付

13 个保护文件 SHA-256 前后完全一致，包含原始复杂 Design、原工程/AI 存档和 SQLite；清单在 JSON。
数据库 SHA-256：`1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`。
共享 Router、CAD/Exact、工程安全阈值与项目 schema 未修改；自动面/位置/尺寸决策仅在显式新 Generate 的 WorkDesign 内执行。进入 Model 后仍按原有用户所有权工作。
代码和本报告统一提交到既有分支。最终 commit、远端 HEAD、工作树及再核对哈希记录在 `output/runtime-checks/single-work-root-correction-20261014/delivery.json`，并由本次最终回复确认。

机器可读交付：`docs/engineering/work-design-root-correction-evidence.json`；所有完整输入、计算表、路线和失败证据继续保留在本机运行目录。到此停止，不启动新的复杂 Generate。
