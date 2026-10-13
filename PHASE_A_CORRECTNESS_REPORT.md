# Phase A 底层正确性整改

起点：`05b10c39e3712f2edf348c7e9e2e257614d4b172`，分支 `codex/sqlite-domain-reset`。范围仅 F1、F2、F4、F5；没有修改三维树续接、部分 core 准入或联合求解控制层。

## 修复与原反例复验

| 缺陷 | 实际源码位置 | 修复前 → 修复后 |
|---|---|---|
| F1 非等价状态合并 | `manifold/ai_design/coupled_layout.py::_beam_key, _forward_context, _actions` | 去重从 face/rotation 改为完整 Design、已放置集合及锁定约束。E1 QA 原来 26 个坐标只留一个且与锁定 B 冲突；现在前向检查始终包含完全锁定/非生成所有的源，48 个合法展开对应 48 个状态键，原宽度内保留 4 个不同坐标且均源安全。真实布局 38 的轴对称组：57 个展开对应 57 个键，保留 4 个不同位置。|
| F2 端点依赖缓存 | `manifold/routing_space.py::MachiningSpace.operations` | 同一完整钻孔只缓存工具/源加工检查；每次 attach 后按实际保留孔的闭合重新检查本次端点。E2 占用→可用返回 `[0,1]`，可用→占用返回 `[1,0]`，均与新空间实例一致；两种顺序均仅生成一个几何缓存项。|
| F4 任意短孔门槛 | `manifold/routing_space.py::operations, narrow_window_seeds` | 删除无工程依据的 8/10 mm 常量门槛；保留正深度、实体内范围、实际刀具含钻尖可达性、真实闭合/啮合、端点占用、壁厚及源保护检查。先绑定真实闭合再检查啮合，避免 schema 的旧 8 mm 默认值成为另一道隐含门槛。原 E4 7.5 mm 孔从 0 个动作变为 1 个；11.5 mm 对照仍为 1 个。|
| F5 粗包络与实体不一致 | `manifold/routing.py::_cuts_too_close, _plug_cut_overlap, route_obstructions`；`manifold/machining_predicates.py` | 外包只证明分离；可能接近的有限圆柱/锥面/环槽使用局部 Exact 距离/交体积，安装区使用生产包络，堵头使用真实生产占用形状。E5 3.535533906 mm 实体间隙在 3 mm 规则下不再误拒，4 mm 规则仍拒绝；0.005325172 mm³ 堵头交集由漏检变为检出。|

局部判定明确区分 SAFE、VIOLATION、EXACT_REQUIRED；后者必须得到真实 CAD 测量。零间隙的切削隔离比较实体交体积，正壁厚比较实际距离。使用既有 `1e-6` CAD 容差，未降低任何工程阈值。CAD 无效/空输入不会被当成零交体积或安全。缓存保存完整世界几何的测量，不保存可跨阈值复用的 PASS；形状与测量缓存有界。

安装粗筛同时纠正了 external-port definition 的源包络读取；不再用 Feature 默认包络替代源定义。thread-only 占位端口沿用生产语义：没有虚构安装包络，其实际 tap 切削仍受源/堵头/跨 Net 检查及最终未解决加工规则约束。

E1 原合法坐标布局重新通过生产 Exact：83 PASS / 0 WARNING / 0 FAIL，有效单实体 BRep，STEP PASS。E4 两种深度分别通过 42 PASS / 0 WARNING / 0 FAIL，有效单实体 BRep，STEP 体积差均为 0。它们只证明这两项反例整改，不代表复杂全网设计通过。

## 真实违规仍拒绝

使用原布局 45 的实际 Feature 参数、源定义和拒绝记录，不生成新布局或路线：

| 原规则 / 实际 Feature 对 | 已有 Exact 量值 | 整改后 |
|---|---:|---|
| installation_access：`R-5c62e091-4 / R-702e7749-8` | 1.202795737 mm，要求 2 mm | 拒绝 |
| cross_net_wall：`R-702e7749-5 / R-e632b709-1` | 7.637553738 mm³ | 拒绝 |
| cross_net_wall：`R-309be2fb-5 / R-f0055891-2` | 198.522533613 mm³ | 拒绝 |
| cross_net_wall：`R-309be2fb-8 / R-e632b709-2` | 199.760369153 mm³ | 拒绝 |
| plug_cut：`PORT_66b53e3529902591f922 / R-1d09f6fa-2` | 534.462721596 mm³ | 拒绝 |
| source_protected：`CV_9479468e4dd71c7470a2 / R-1d09f6fa-3` | 987.980317184 mm³ | 拒绝 |

## 聚焦验证与隔离

- 新增生产算法反例验证覆盖：布局坐标/尺寸/约束/接口依赖、锁定障碍、本次端点正反顺序及保留闭合、7.5 mm 孔、工具/面/壁厚/闭合/源保护/出界拒绝、有限端面、真实擦边堵头、锥面/环槽、无效 CAD、external-port 源安装区。
- 既有聚焦验证：刚性共享窗口布局与锁定、多组耦合、四项真实堵头筛查、缓存与无缓存/几何改变一致性。
- 既有 Save/Reload 验证：真实生成孔保存，独立工作进程重载、Validate/Build（搜索入口禁止调用），再编辑/保存与显式 Reroute。
- 既有 Manual Model 验证：Preview/Optimize 不进入 AI 自动布局，源位置和 Block 不变；Store/API 修订与请求保护检查通过。没有生产算法结果 mock；隔离测试只重定向临时文件并禁止不应调用的入口。
- 最终聚焦结果：27 项反例/几何/布局/缓存检查通过；4 项持久化/Manual/Store/API 检查通过；六个修改 Python 文件语法检查及 `git diff --check` 通过。原 E1/E4 另由复验脚本直接通过生产 Exact/BRep/STEP。
- 初次扩大到整个旧 `test_route_plug_screen.py` 时，两个旧 mock 测试因 lambda 不接受 `port_approaches` 失败。在独立提取的原 baseline 中重现同样两项 TypeError；未修改这些旧测试，也未将它们计为通过。其余真实几何测试已单独通过。
- 没有运行 T-10A、prove、完整 Python/JS、Vite、浏览器或复杂 Generate，也没有付费 AI 调用。

13 个受保护文件（SQLite、原源 Design、九个存档、两个 AI task）SHA-256 前后与原运行清单一致；原审查所用 50 个源/逐布局证据文件哈希也未改变。实际 CAD 输出、完整日志和保护清单保留在 `output/runtime-checks/phase-a-20261013/`，没有提交 CAD 或数据库。

复验命令：`.venv/Scripts/python.exe -B scripts/check-phase-a.py`，需要本机既有审查/运行证据；新结果写入独立 Phase A 目录。可携带摘要：`docs/engineering/phase-a-correctness-evidence.json`。

Phase A 无剩余正确性 blocker。Beam 仍是有界搜索，未声称所有合法布局均被保留；没有声称复杂八网工程已可制造。Phase B/C 的已知限制仍待单独授权整改，本轮到此停止。
