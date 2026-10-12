# 全网联合钻孔协调修正

起始 HEAD：`b526cc21aa4d5df208701105e0707fcafb565f8b`；分支 `codex/sqlite-domain-reset`，起始干净。

## 根因与修改

- 原完整组合搜索在一个 Net 暂时无选项时终止分支；Session 只复用单网候选，无法从已知兼容组合继续插入。新增 AI 专属 `joint_routes.extend/improve`，保留部分组合、延期阻塞 Net，并按真实冲突孔释放、回退和重新插入相关 Net。共享 `routing.select_route_combination` 默认不变。
- 数量相同的不同兼容组合曾被丢弃。例如插入新 Net、释放其阻挡 Net 后仍为 6/8，这个中间状态必须保留，才能针对**新插入路线**重排被释放的 Net。现在缓存组合级钻孔及清晰配对证据，并按源几何／定义／工程条件指纹失效；变更终端的旧路线不能直接复用。
- `route_from_variant` 内部移除了可变兄弟路线，入口选择看不到第三条 Net。AI 临时只读障碍副本现在保留所有外部预约孔；入口、堵头、全深度、刀尖及壁厚均按真实加工体筛查。副本状态不会写入 Project。
- 入口翻转、交汇点／层位事件与受阻钻孔的局部分支树重建，均复用共享 `MachiningSpace.operations`；每条支路是实际外表面钻孔。已知重复几何在调度前跳过。所有候选仍为解析状态，完整方案必须通过原 Exact 连通性、生产 BRep 和 STEP 门禁。

修改文件：`ai_design/layout_search.py`、`route_catalog.py`、新增 `joint_routes.py`；另有固定布局重放脚本及三个协调／一个隔离检查。没有改 AI Analysis、初始布局、材料、共享 Router 接受规则、SQLite 或手工 Model。

## 实际结果

直接读取此前最终评估中的真实 6/8 组合（逐布局旧快照当时仅有 5/8，未混用）。同一 **310×245×230 mm** 源布局上，得到 **7/8 解析兼容 Net**：A_DC、B_DC、MA、P、SHUTTLE_OUTPUT、T、T_DC；44 个真实钻孔。该次重放 314.891 s，781 状态／2459 配对／40 个新增候选。

随后直接恢复这 7 条路线复查：仍保留 **7/8**，346.985 s，1000 状态／2557 配对／60 个新增候选，70 个走廊批次仍待探索。没有提高 1000／4000 组合预算或手工默认预算。后期源保护、特征数及浅层搜索分级守卫通过静态及聚焦检查，没有为这些守卫重复完整长运行。

**未找到完整 8/8，因此没有完整生产 Exact／BRep／STEP 接纳。** 7/8 只表示当前解析加工兼容关系，不等于精确液压连通性或制造批准；`connection_verified` 未被提升。

## 剩余 MB 阻挡

对当前保留 7 条路线，单独检验全部 **20 个已有 source-clear MB 候选**，可直接插入数量为 **0**。最接近的方案仍被以下实体阻挡：

- MA：`R-1d09f6fa-1 ↔ R-f0055891-3 / R-f0055891-AX3`，及 `R-1d09f6fa-3 ↔ R-f0055891-1 / R-f0055891-6`。
- T_DC：`R-1d09f6fa-AX2 ↔ R-8e428e23-2`。

这些是保守加工实体间距失败，不伪报 Exact 串油体积。继续插入 MB 需要同时改变 MA／T_DC 的相关加工入口或分支通道；本轮局部与成组替代仍未找到全网兼容解。未证明固定空间物理无解，也未将剩余问题笼统归为预算不足。

## 隔离与证据

Block、Cavity、Port 坐标和源定义均未变；原存档与活跃数据库 SHA-256 前后相同。仅新 AI Generate 使用新协调器；Model／Reroute／Optimize／Preview／Validate／Build／Save／Reload 没有新增调用，也不使用 `origin.method` 授权。

仅四项聚焦检查、语法及 diff 检查通过；未运行 T-10A、prove、完整回归、无关 CAD 或 AI Analysis。

简明证据：`docs/engineering/joint-net-coordination-evidence.json`。完整可重放钻孔及候选池在 `output/runtime-checks/joint-net-20261012-machining-bypass/`、`joint-net-20261012-seven-core/`。最终提交／远端／干净状态由实际 Git 查询交付。
