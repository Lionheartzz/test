# 单工作设计工程规划与加工闭环整改

基线 `767cbc2c6d476d632bbb3d6c54057ed33c6b4651`；分支 `codex/sqlite-domain-reset`。

**控制流已整改；复杂工程仍未达到完整设计验收。** 本次没有运行完整复杂 Generate。
提交与远端身份在发布后写入 `output/runtime-checks/single-work-20261014/delivery.json`，最终答复同时给出真实 SHA；提交内不写自引用 SHA。

## 生产调用链

修改前：Generate → plan_new → 多布局 optimize（48）→ Controller 返回已拒绝工艺 → screen → Session.prepare → 全 Net Catalog / 深搜。
修改后：Generate → plan_new → optimize → 一个 WorkDesign / EngineeringPlan → 工艺约束求坐标 → 完整生产钻孔 → production machining precheck → 同一设计的测量修复事务 → LocalAdmission → 完整方案才进入 Exact/BRep/STEP。
正常路径不调用 initial_candidates、pack_topology、pop_diverse、screen 或 Session.prepare；旧工具显式保留。layout_limit 兼容参数不再控制布局。
源码：`single_design.py` 主控制；`joint_layout.py::optimize` 调用和接纳；`engineering_decisions.py` 清除拒绝工艺外泄；`route_catalog.py` 对显式工艺设禁止目录扩展门禁。

## 真实复杂输入：初始工程计算

源布局为 **357.322706 × 102.022706 × 113.967867 mm**，源安装门禁通过。尺寸同时保留了轴向安装堵头与源停深的必要空间；工艺域仍有矛盾，不证明全部钻孔走廊可制造。
同面圆形间距使用 Ri+Rj+Gij；非圆形使用旋转后的切削和实际边界投影，并以生产 CAD 安装/边界实体复核。压力壁厚、流量和工具沿用生产逻辑，未知值留为 UNKNOWN。
相对面仅在实际投影重叠时叠加深度；通用见证分别算出 42 mm（分离）与 82 mm（重叠）。移动遇到对面源时，根据真实背壁计算尺寸增长，不按固定比例放大。

| 元件 | 面 / 旋转 | U / V (mm) | 实际加工深度 / 壁厚 (mm) | 面内投影支持 |
|---|---|---|---|---|
| RDDA relief valve (top, T-10A) | top / 0° | 15.875000 / 15.875000 | 51.800000 / 0.000000 | {'0': [-15.875, 15.875], '1': [-15.875, 15.875]} |
| RDDA relief valve (middle, T-10A) | top / 0° | 49.625000 / 15.875000 | 51.800000 / 0.000000 | {'0': [-15.875, 15.875], '1': [-15.875, 15.875]} |
| CBCG counterbalance valve (left, T-11A) | top / 0° | 83.375000 / 15.875000 | 76.430000 / 0.000000 | {'0': [-15.875, 15.875], '1': [-15.875, 15.875]} |
| CBCG counterbalance valve (right, T-11A) | top / 0° | 117.125000 / 15.875000 | 76.430000 / 0.000000 | {'0': [-15.875, 15.875], '1': [-15.875, 15.875]} |
| DSCS shuttle valve (T-31A) | top / 0° | 150.875000 / 15.875000 | 97.100000 / 0.000000 | {'0': [-15.875, 15.875], '1': [-15.875, 15.875]} |
| 4-way directional control valve AH4D102a/f | top / 0° | 219.761353 / 51.011353 | 28.240000 / 0.000000 | {'0': [-51.01135282409776, 51.01135282409776], '1': [-51.01135282409776, 51.01135282409776]} |
| RBAA relief valve (T-3A) | top / 0° | 291.822706 / 19.050000 | 59.810000 / 0.000000 | {'0': [-19.05, 19.05], '1': [-19.05, 19.05]} |
| LRHC logic valve (T-17A) | top / 0° | 335.097706 / 22.225000 | 93.890000 / 0.000000 | {'0': [-22.225, 22.225], '1': [-22.225, 22.225]} |
| PORT_6d31ed2bd8add71e5a63 | left / 0° | 9.525000 / 9.525000 | 17.723197 / 0.000000 | {'1': [-9.524999999999999, 9.524999999999999], '2': [-9.524999999999999, 9.524999999999999]} |
| PORT_2ff53e755aecdd3ecd26 | right / 0° | 9.525000 / 9.525000 | 17.723197 / 0.000000 | {'1': [-9.524999999999999, 9.524999999999999], '2': [-9.524999999999999, 9.524999999999999]} |
| PORT_ff005d98b5f75bf1aa24 | front / 0° | 29.983197 / 12.250000 | 19.360543 / 0.000000 | {'0': [-12.25, 12.250000000000004], '2': [-12.25, 12.25]} |
| PORT_27ddec688c9b93eac4f8 | back / 0° | 12.250000 / 12.250000 | 19.360543 / 0.000000 | {'0': [-12.25, 12.25], '2': [-12.25, 12.25]} |

元件优先顺序、Net 超图耦合分组、全部同面中心距公式/数值/元件对、每个元件的约束和各 Block 维度的有向约束，完整存于伴随 JSON 的 `initial_calculation`。不能从此表推断未检查的阀体高度或压力资格。

## 每条 Net 的工艺计划

以下是当前工艺意图和已实例化加工孔，不是合格走廊。交汇坐标在工艺约束矛盾时仅用于诊断；不送往昂贵搜索。完整外表面入口、深度、钻尖、闭合 ID、啮合和包络均在 JSON `drillings/operations`。

| Net | 主轴 / 层轴 / 入口 | 诊断交汇坐标 (mm) | 孔数 | 前检结果 |
|---|---|---|---|---|
| A_DC | X / Z / negative | (140.209088, 20.884088, 66.555367) | 9 | {'plug_cut': 4, 'source_protected': 8} |
| P | X / Z / negative | (194.947419, 28.412118, 45.526911) | 9 | {'installation_access': 1, 'plug_cut': 2, 'source_protected': 4} |
| T | X / Z / negative | (213.056804, 43.765902, 43.545245) | 8 | {'plug_cut': 4} |
| SHUTTLE_OUTPUT | X / Z / negative | (221.348853, 17.4625, 57.439117) | 6 | {'installation_access': 1, 'plug_cut': 2, 'source_protected': 4} |
| MA | X / Z / negative | (40.21875, 14.2875, 49.45215) | 11 | {'cross_net_wall': 4, 'installation_access': 2, 'plug_cut': 13, 'source_protected': 3} |
| MB | X / Z / negative | (131.986926, 14.2875, 49.45215) | 11 | {'cross_net_wall': 2, 'installation_access': 1, 'plug_cut': 8, 'source_protected': 7} |
| T_DC | X / Z / negative | (265.529529, 23.518176, 87.062867) | 5 | {'plug_cut': 2, 'source_protected': 8} |
| B_DC | X / — / negative | (145.359088, 20.884088, 78.265367) | 9 | {'installation_access': 3, 'plug_cut': 8, 'source_protected': 13} |

## 两项已知违规及局部修复

| 原证据 | 同输入生产复现 | 局部事务 | 最终状态 |
|---|---|---|---|
| 源保护侵入 | CV_6bbcdb6cce3a4c816cb3 ↔ R-702e7749-4；524.2981254966872 mm³ | 重建不同入口并用完整源/堵头/第三方检查；测量分离不等式回传源和走廊变量 | 新工艺仍违规，已回退，原违规保留 |
| 堵头/切削 | R-e632b709-3 ↔ R-e632b709-8；66.39930264676538 mm³ | 先确认哪一侧实际安装堵头侵入另一侧完整切削体，再建占用/切削分离约束；不是比较两个堵头 | 新工艺仍违规，已回退，原违规保留 |

每个事务的原规则、轴、完整边界、壁厚/间隙、所需距离、受影响 Net、重建后的全部失败及回退结果见 JSON `cases.*.repair_records`。局部改入口成功的通用见证只重建 N，另一网 OTHER 的实际孔和全部源位置不变。
源移动会扩展到共享刚体全部窗口及扫掠区域相交的第三方路线；Block 变化使全部受尺寸影响的孔失效并重新加工。冻结/非拥有变量始终受域约束，不通过 origin 授权。

## 尚存的具体工程 blocker

1. 当前统一逃逸顺序要求 T_DC→P、P→T、T→T_DC 在同一 Y 方向各相隔 11.1 mm，形成正权环。已切换受矛盾影响的直接/平面工艺，仍没有满足这一工艺域的共同坐标。此为当前单交汇/统一逃逸层表达缺口，不是物理无解，也不是搜索额度结论。
2. 已修复另一项 Planner/Router 不一致：孤立源轴向可用，不代表只按源深度计算的 Block 可容纳安装堵头。现在厚度包含源停深偏移、真实啮合及完整圆柱半径；AI 显式轴向工艺传递实际绑定的闭合定义，默认 Manual 调用不变。当前 P 已实例化 9 个真实孔；仍被 source_protected、installation_access、plug_cut 拒绝。具体规则和实体在 `cases.precheck.final_failures.P`。
3. 对这些已拒绝工艺，入口改变也产生新的真实违规，分离域仍矛盾；未找到可提交的修复。因此保留源合法 Draft，不转入下一布局、全网目录或深搜。
4. 共享刚体三网见证在本次独立进程内停于生产 hydraulic.opening 运算，上限安全停止，分类 UNKNOWN。没有出现可用于证明物理违规的结果；没有把该检查写作 CAD PASS。旧共享刚体接纳记录保留，当前独立进程重复性仍是 CAD 运算 blocker。

旧布局的 MA/MB/P 样例同时有 source_protected、installation_access、plug_cut；T 原计划只有 plug_cut。旧目录只保存少量拒绝样例，不能据此宣称所有合法入口均已检查；摘要和原证据路径都在 JSON `previous_failed_pools`。

## 时间、缓存与真实工作量

| 有界任务 | 含启动耗时 (s) | 编译 | 坐标求解 | 实体生成 | 前检 | 局部修复 |
|---|---|---|---|---|---|---|
| facts | 3.828 | 0.157 | 0.063 | 0.000 | 0.000 | 0.000 |
| precheck | 7.594 | 0.156 | 0.062 | 0.093 | 4.016 | 0.000 |
| source | 3.407 | 0.141 | 0.031 | 0.000 | 0.078 | 0.906 |
| plug | 3.109 | 0.141 | 0.016 | 0.000 | 0.078 | 0.641 |

表中总耗时为 supervisor 统计的子进程生命周期，外层诊断 CLI 的 Python 启动另计。阶段时间为包围时间，父子阶段和 Boolean 计时可能重叠，不能相加作独占 CPU 时间。Router 的真实工艺实例化计入实体生成；目录调用、深搜标签、全局布局队列均为 0。CAD Boolean/几何/源包络次数和时间、CPU、缓存字典命中/未命中见 JSON；字典命中不是“节省的 CAD 次数”。
旧第一布局完整目录筛查 49.156 s；本次一个主设计前检 4.016 s。两者布局及工作量不同，不能称为等价工作提速或完整设计性能通过。安全上限仍是 600/120/90 s，诊断用更短 25/20/2 s；明确拒绝不会继续消耗通用搜索。

## 真实 CAD 和隔离验证

- test_directional_entry_repair_0: EXACT_FEASIBLE，{'PASS': 112, 'WARNING': 0, 'FAIL': 0}，BRep {'valid': True, 'solids': 1}，STEP PASS。
- test_inadequate_direct_contact0: EXACT_FEASIBLE，{'PASS': 93, 'WARNING': 0, 'FAIL': 0}，BRep {'valid': True, 'solids': 1}，STEP PASS。
- test_normal_chain_is_one_work_0: EXACT_FEASIBLE，{'PASS': 93, 'WARNING': 0, 'FAIL': 0}，BRep {'valid': True, 'solids': 1}，STEP PASS。
- test_three_net_fixed_source_de0: EXACT_FEASIBLE，{'PASS': 157, 'WARNING': 0, 'FAIL': 0}，BRep {'valid': True, 'solids': 1}，STEP PASS。
- test_source_profile_axial_inte0: EXACT_FEASIBLE，{'PASS': 152, 'WARNING': 0, 'FAIL': 0}，BRep {'valid': True, 'solids': 1}，STEP PASS。
- 源轴向停深见证、直接交汇不足后的实际轴线修复，也用生产 Exact 验证；未放宽直接接触规则。
- 正常调用链检查以禁止入口探针证明没有进入旧布局/目录/三维搜索；CAD 结果由真实生产接口生成。
- 部分路线用既有 Save Draft 持久化并在新进程重载；Validate/Build 对尚未完成路线保持明确拒绝，未隐式搜索或移动源。普通 Save 的原有拒绝语义保留。
- Manual Preview / Optimize、Store/API 版本冲突与路径守卫、原有取消及时间上限均有聚焦检查；默认 Router 操作记录开启/关闭生成相同几何。
- 13 个保护文件哈希前后一致，包括 SQLite、原始复杂源和原项目/AI 任务；数据库 SHA-256 `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`。完整清单在 JSON。
- 未运行 T-10A、prove、全量套件、浏览器、Vite、付费 AI 或新的完整复杂 Generate。

机器可读证据：`docs/engineering/single-layout-engineering-evidence.json`；全部原始运行证据继续保留在 `output/runtime-checks/single-work-20261014/`。

**交付不包含复杂工程制造通过声明。原始工程和 Library 保持不变；没有继续开始下一轮长 Generate。**
