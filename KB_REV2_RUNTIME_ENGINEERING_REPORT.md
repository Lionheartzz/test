# REV2 Runtime Engineering Integration — 2026-10-01

从 `c409151e37e35eb87f608242e5c5db51bba8c378`、`codex/sqlite-domain-reset` 实施。10 个研究材料中 7 个确定性准入，3 个保留研究状态；材料 API 由 2 项增至 9 项。当前 schema v4 生产库已备份并替换为验证过的重建库，未升级 schema，启动仍仅验证。

## 材料身份与默认值

| 研究身份 | Grade / state | 结果或原因 |
|---|---|---|
| MAT-1045 | 1045 / +N | Research-only: Source condition and standard applicability require confirmation |
| MAT-6061 | 6061 / T6 | Engineering: `material_rev2_7f08530fe19bb20f90b18d76` |
| MAT-6082 | 6082 / T6 | Engineering: `material_rev2_403994ca2fb74133a2883fe2` |
| MAT-7075 | 7075 / T6 | Research-only: Standard applicability or grade/state suffix is unresolved |
| MAT-C45 | C45 / +N | Engineering: `material_rev2_d70a417e2e0b608bf342c605` |
| MAT-S355 | S355 / As-rolled / normalized grade suffix-specific | Research-only: Standard applicability or grade/state suffix is unresolved |
| MAT-SS-304 | 304 / Annealed | Engineering: `material_rev2_42ed93ca999dba735f4f6102` |
| MAT-SS-304L | 304L / Annealed | Engineering: `material_rev2_32209f368ec7e842b1fe9882` |
| MAT-SS-316 | 316 / Annealed | Engineering: `material_rev2_1c172d3d87fa8fe7b808f455` |
| MAT-SS-316L | 316L / Annealed | Engineering: `material_rev2_492922aeac1fa94c78d8faf1` |

原有 `material_1` Aluminum、`material_2` DuraBar 的完整行和工程库存不变；两种旧项目通过 import-project API 加载检查。属性冲突不等于身份冲突，316L 等身份可选，但冲突属性不成为工程参数。C45 与 1045 不合并。runtime ID 使用研究身份、grade、standard、state 的 SHA-256；只在显式导入的新克隆内创建，并写入 `technical_identities.material_id`。

6061-T6 的适用 extrusion 数据显示屈服 276 MPa、拉伸 310 MPa、密度 2700 kg/m³、硬度 60 HRB，并保留 condition 与证据 ID。这些不是许用应力。实际包没有可直接采用的 allowable/design stress，9 个运行时材料的该默认值均为 null。安全系数 2、额外壁厚 4 mm、最小壁厚 7 mm 仍为项目政策。只在换材料时应用一次；手动覆盖和同材料重绘不会重新套默认值。

工程 `material_stock` 保持 268 → 268 条；674 条供应商库存仍为独立 evidence，没有符合明确工程库存语义的晋升，选材料不会改变 block 尺寸。104 条 treatment 保留参考语义；Inspector 显示 CONDITIONAL / UNKNOWN / NOT_APPLICABLE 状态，没有新增 treatment 选择字段或验证规则。

## 中央事实解析与消费者

`manifold/engineering_facts.py` 是技术参数成为工程可用事实的唯一路径。返回 SOURCE_BACKED / USER_OVERRIDE / UNRESOLVED / NOT_AVAILABLE、稳定身份、value/unit、scope、condition、证据及来源。只读取映射过的 technical_values；拒绝非 parameter、未建立来源权威、未知单位/范围文本、未适用的 scope/option/condition、未解决冲突和 ambiguous/relation-only 身份。显式且有支持证据的 preferred 值才可解决冲突。summary 截断时不推断全局属性结论。

| 映射语义 | 用途 |
|---|---|
| yield_strength、yield_strength_Rp0.2、tensile_strength、density、hardness、service_temperature | 材料信息；保留各自语义与条件，不转换为许用应力 |
| maximum_working_pressure、rated_pressure | 对已有 pressure_bar 需求作独立比较 |
| maximum_flow、rated_flow、nominal_flow、capacity | 各自独立；nominal/capacity 文本不得伪装为 max/rated flow |
| function_primary、fluid_temperature_min/max、viscosity、internal_leakage | 已归一化且适用时提供事实；没有新建执行限制 |

`/api/materials` 使用批量事实查询和批量 stock/treatment 元数据，保留旧字段；包含 9 个材料与原有库存约 103,223 bytes，其中没有原始证据 dump。一次本机读取约 20.5 ms；事实查询使用 identity/value 索引并限定每身份每属性 32 个观察、每批最多 50 身份。

Model 的材料 selector 使用 runtime ID，显示简明事实与技术证据入口；未解析条件观察默认折叠。Cavity Inspector、兼容 cartridge 选择、Schematic、Engineering Review、AI generation preflight 都可查看中央事实。新增只读 GET `/api/cartridges/{id}/engineering-facts` 与无持久化 POST `/api/engineering-facts/review`；后者只比较真实已填写的 net flow/pressure，生成 INFO / WARNING，没有新 FAIL，也不参与 routing 评分。材料直达详情的 Back 已修复并有专门回归测试。

AI provider request 加入结构化工程参考上下文；材料须已准入，cartridge 必须精确匹配身份，generation/preflight 复用同一解析器。来源参数、条件参考与未解析项分开，缺失值为 null。AI 的原始图纸事实准入和已有 logical cavity 选择保持原边界；ratings 不建立 compatibility。测试未调用任何外部 AI provider。

## 真实 Cartridge 样例

| 样例 | 中央解析结果 |
|---|---|
| Sun Hydraulics RDFA3 | SOURCE_BACKED maximum working pressure 344.7 bar；证据 EV-SUN-RDFA3-DIRECT2015-MAXIMUM_WORKING_PRESSURE，保留来源版本，未声称当前生命周期认证 |
| TRIES 519.022 | SOURCE_BACKED maximum working pressure 210 bar |
| Command Controls CVRP-16 | maximum working pressure UNRESOLVED；冲突值未选择 |
| Weber-Hydraulik 3-Wege | IDENTITY_AMBIGUOUS，无可执行技术值 |
| Delta Power MINI 4W | RELATION_SOURCE_ONLY，无可执行技术值 |

在隔离测试项目中，已有 300 bar 需求显示在 RDFA3 的来源压力值之内；已有 20 L/min 需求因适用最大/额定流量缺失而显示 WARNING。没有创造替代额定值，也没有修改兼容准入规则。

## 两次重建与本机替换

输入保持不变：当前生产 v4 DB + 原 REV1 ZIP + 更新后的 `PMC_Manifold_Global_Cartridge_Technical_Handoff_2026-10-01.zip`。当前 DB 已有修正的原 MDTools/REV1 执行定义；新克隆保留这些完整表，不重复转换 MDTools 几何；只清空克隆中的 REV2 技术层并用相同包重建、确定性准入材料。

- 原生产 SHA-256：`e8f6eac9084ab4a7befd1290a3b5d3aaee7edfabd7fe3a0dcae8904baea13c24`。
- REV2 包 SHA-256：`3a8dea4d38fc14fe8169697be465ea2fa492ea343da0b722d036385c07af4a80`；REV1：`bd02e61ea7b92c747ec6e5f7942e4c4618a27a236d49d083a3c0a48cd9df3a16`。
- 两个全新库：`data/pmc_engineering.runtime-a.db`、`data/pmc_engineering.runtime-b.db`。
- 所有 technical 表（排除带导入时间的 batch 元数据）、materials、身份链接、material_stock 内容摘要及中央材料事实完全一致；integrity_check 与 foreign_key_check 通过。
- 原工程表全部内容摘要一致，原材料行完全保留。执行兼容对 24,948 → 24,948；完整 sorted row/key SHA-256 前后均为 `1d6f05f4bd8c62e45546a40be9f73b74e3683e19e3d111cf257b1c8d6095dae9`。
- 备份：`D:\Project\Manifold\data\pmc_engineering.pre-runtime-20261001.db`。
- 替换后生产 `data/pmc_engineering.db`：schema 4，SHA-256 `1b0a4e23623d4a4b1b87b4d88dd075f9d75b96ae482ffd94c6095aa4dfee1e69`。
- DB 与 ZIP 不提交 Git；正常 `projects/saved/*.json` 全部 SHA-256 核对保持不变。浏览器测试项目只写入 ignored `output/rev2-runtime/qa`。

## 验证结果

- 聚焦 Python：67 passed，0 failed（engineering facts、REV2 importer/API、store/API、AI analysis 与 mounting units）。包含重复重建材料 ID、preferred/conflict 排除、真实语义映射、条件/option、参数证据类型、AI 结构化事实/缺失值与旧 ID。
- 全部 `.test.mjs`：69 passed，0 failed；Vite build 成功。现有字体资源运行时解析提示与 bundle size 提示未变化。
- `python -m manifold prove`：invalid PASS 295 / WARNING 2 / FAIL 6；corrected PASS 268 / WARNING 1 / FAIL 0。没有弱化工程规则。
- `git diff --check` 通过。没有再次运行完整 Python suite；前次报告中的 11 个已接受基线失败未重跑、未 xfail、未改行为。
- localhost `http://127.0.0.1:8765` 与 Wi-Fi LAN `http://192.168.253.117:8765` 实际浏览器全部通过，分别 isSecureContext true / false，pageerror 0。验证材料列表、稳定 ID 保存、空许用应力、覆盖/重绘、换材料默认值、supplier stock 隔离、Library research-only 解释、无 evidence 执行按钮、Review 与 Schematic 事实。
- 最终截图与验收 JSON：`output/playwright/rev2-runtime/localhost/`、`output/playwright/rev2-runtime/lan/`。已视觉检查 Model、Library、Review，详情返回正常。

本次涉及文件：

- `manifold/ai_design/generation.py`
- `manifold/ai_design/library_resolution.py`
- `manifold/ai_design/providers.py`
- `manifold/ai_design/remote.py`
- `manifold/ai_design/service.py`
- `manifold/engineering_db.py`
- `manifold/import_technical_knowledge.py`
- `manifold/server.py`
- `manifold/technical_knowledge.py`
- `tests/engineering-inputs.test.mjs`
- `tests/library-ui.test.mjs`
- `tests/technical-knowledge-ui.test.mjs`
- `tests/test_technical_knowledge.py`
- `web/ai-generation.js`
- `web/engineering-inputs.js`
- `web/library-ui.js`
- `web/main.js`
- `web/project-ui.js`
- `web/technical-knowledge-ui.js`
- `web/workflows.js`
- `manifold/engineering_facts.py`
- `scripts/check-rev2-runtime-browser.mjs`
- `scripts/check-rev2-runtime.py`
- `tests/rev2-runtime-browser.run.js`
- `tests/test_engineering_facts.py`
- `web/engineering-facts-ui.js`

本报告本身亦提交。commit SHA、push 后 remote HEAD 与 clean tree 结果在最终回复及 `output/rev2-runtime/delivery.json` 记录，避免将文件自身的 Git hash 循环写入提交内容。
