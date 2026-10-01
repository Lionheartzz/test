# PMC Hydraulic Manifold Core Materials — 2026-10-01

从 `7ef770e68f6ba4a3f6d2124bbab2d431a9e1752e` / `codex/sqlite-domain-reset` 实施。正常新项目 selector 由混合 9 项（7 精确 + 2 泛称）变为 **12 个精确、来源支持的身份**。运行时表共 14 行，含保留的 2 个泛称旧 ID；研究身份 10 → 17，另外保留本次未准入的具体候选。schema 仍为 **v4**。

## 最终验收表

原十个研究身份的 canonical grade/state/standard/product_form 字段完整保留；补包记录经审查的 block-stock 形式和 primary delivery standard。原七个 runtime ID 没有变化，标签/材料 family 在显式新库重建时更新。其他形式、其他标准的数值不会因此成为通用参数。

| Material identity | Runtime? | Grade | State/temper | Standard | Product form | Primary source | Notes |
|---|---|---|---|---|---|---|---|
| MAT-6061 | Yes | 6061 | T6 | ASTM B221 | Extrusion | [Hydro Extrusion North America](https://www.hydro.com/globalassets/01-products--services/extruded-profiles/americas/ena-resources/alloy-data-sheets/hydro_2019_data_sheet_6061.pdf) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-6082 | Yes | 6082 | T6 | EN 755-2 | Extrusion | [Hydro Innovation & Technology](https://www.hydro.com/globalassets/08-about-hydro/hydro-worldwide/germany/extrusion-germany/alloy-data-sheets/hydro-en-aw-6082.pdf) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-C45 | Yes | C45 | +N | EN ISO 683-1:2018 | Bar | [Saarstahl](https://en.saarstahl.com/app/uploads/2024/03/20160401102929-0503_C45.pdf) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-SS-304 | Yes | 304 | Annealed | ASTM A240 | Plate | [Outokumpu](https://www.outokumpu.com/-/media/files/products/core/outokumpu-core-range-datasheet.pdf?hash=0DB21994AD31F93E9C62A531BE9C36E6&modified=20251117111909&revision=025e9931-a1d5-4c8f-8ff5-f881d38916da) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-SS-304L | Yes | 304L | Annealed | ASTM A240 | Plate | [Outokumpu](https://www.outokumpu.com/-/media/files/products/core/outokumpu-core-range-datasheet.pdf?hash=0DB21994AD31F93E9C62A531BE9C36E6&modified=20251117111909&revision=025e9931-a1d5-4c8f-8ff5-f881d38916da) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-SS-316 | Yes | 316 | Annealed | ASTM A240 | Plate | [Outokumpu](https://www.outokumpu.com/-/media/files/products/supra/outokumpu-supra-range-datasheet.pdf?modified=20251117111951&revision=7a909396-d1f3-4d36-9c1c-99606be41fd2) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-SS-316L | Yes | 316L | Annealed | ASTM A240 | Plate | [Outokumpu](https://www.outokumpu.com/-/media/files/products/supra/outokumpu-supra-range-datasheet.pdf?modified=20251117111951&revision=7a909396-d1f3-4d36-9c1c-99606be41fd2) | Existing runtime ID preserved; reviewed block-stock context |
| MAT-CORE-6061-T651-EXTRUDED | Yes | 6061 | T651 | ASTM B221 | Extruded bar | [Sun Hydraulics](https://www.sunhydraulics.com/sites/default/files/media_library/Product_Bulletin-Manifold_Materials_of_Construction%20update_v4.pdf) | Exact new independent identity |
| MAT-CORE-6061-T651-PLATE | Yes | 6061 | T651 | ASTM B209/B209M | Plate | [Kaiser Aluminum](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1015/Kaiser_Aluminum_6061_Sheet_Coil_and_Plate.pdf) | Exact new independent identity |
| MAT-CORE-7075-T651-PLATE | Yes | 7075 | T651 | ASTM B209/B209M | Plate | [Kaiser Aluminum](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1017/Kaiser_Aluminum_7075_Sheet_Coil_and_Plate.pdf) | Exact new independent identity |
| MAT-CORE-DURABAR-65-45-12 | Yes | 65-45-12 | As-cast | ASTM A536 | Continuous cast bar | [Dura-Bar](https://www.dura-bar.com/products/ductile-iron/65-45-12) | Exact new independent identity |
| MAT-CORE-DURABAR-80-55-06 | Yes | 80-55-06 | As-cast | ASTM A536 | Continuous cast bar | [Dura-Bar](https://www.dura-bar.com/products/ductile-iron/80-55-06) | Exact new independent identity |
| MAT-1045 | Research-only | 1045 | +N | AISI/SAE 1045 | Round bar | [voestalpine High Performance Metals Australia](https://www.voestalpine.com/highperformancemetals/australia/app/uploads/sites/265/2024/08/Datasheet-1045-2026-v2.pdf) | Exact normalized 1045 bar product standard is not declared by the producer; nearest-designation list and supply states do not validate the old +N identity. C45 is not substituted. |
| MAT-7075 | Research-only | 7075 | T6 | ASTM B210/B221 applicability requires confirmation; UNS A97075 | Tube/pipe | [Kaiser Aluminum](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1017/Kaiser_Aluminum_7075_Sheet_Coil_and_Plate.pdf) | Existing T6 tube/pipe identity lacks a confirmed applicable product standard and solid manifold stock form; independently specified T651 plate is selectable. |
| MAT-S355 | Research-only | S355 | As-rolled / normalized grade suffix-specific | EN 10025-2 | Hot-rolled flat product | [SSAB](https://www.ssab.com/-/media/files/en/zero/data_sheet_2422_ssab_s355j2n_zero_2025_01_21.pdf) | Generic S355 does not establish exact suffix/state/product form. SSAB documents a distinct S355J2+N structural plate; generic S355 cannot inherit it. |
| MAT-CORE-6061-T6511B-CANDIDATE | Research-only | 6061 | T6511B | Kaiser product designation; general product standard unresolved | Extruded bar | [Kaiser Aluminum](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1001/KaiserSelect_Manifold_Bar_Brochure.pdf) | Producer-specific T6511B manifold bar is documented, but its applicable product standard is not declared in this brochure. Do not equate it with T651 or T6. |
| MAT-CORE-S355J2N-CANDIDATE | Research-only | S355J2 | Normalized rolled | EN 10025-2 | Plate | [SSAB](https://www.ssab.com/-/media/files/en/zero/data_sheet_2422_ssab_s355j2n_zero_2025_01_21.pdf) | Specific S355J2+N structural plate identity is supported, but no manifold-block application need was established in this bounded core review; not promoted merely to fill the count. |
| material_1 / Aluminum | Existing only | Unspecified | Unspecified | Unspecified | Historical source stock | Original MDTools master | Hidden for new work; old JSON and ID unchanged |
| material_2 / DuraBar | Existing only | Unspecified | Unspecified | Unspecified | Historical source stock | Original MDTools master | Hidden for new work; old JSON and ID unchanged |

新增可选身份：6061 T651 extruded bar / ASTM B221、6061 T651 plate / ASTM B209/B209M、7075 T651 plate / ASTM B209/B209M、Dura-Bar 65-45-12 as-cast continuous bar / ASTM A536、Dura-Bar 80-55-06 as-cast continuous bar / ASTM A536。它们与 T6、tube/pipe、其他厂家或近似等同牌号均不合并。

1045：已核对 voestalpine 2026 v2。资料给出 Hot Rolled / Normalised 供货状态和 nearest standards，但没有证明原 +N 身份的精确 normalized-bar 产品标准；PDF 页眉 UNS 标记与其 nearest 列表亦不同。没有用 C45 替代，也没有把 AISI designation 当作完整 bar 产品规范。

7075：生产商支持 T651 plate，其性能、形式和标准另建身份。原 T6 tube/pipe 数据仍保留；它既缺适用标准确认，也不是当前 solid manifold block 形式，不能被直接改成 plate。

S355：generic S355 没有完整 suffix/state/form。SSAB 明确支持独立的 S355J2+N normalized-rolled structural plate，作为未准入候选保留；当前 core 没有充分的 manifold-block 需要，不为填数量新增到 selector。Kaiser 专用 T6511B manifold bar 同样保留为候选：来源确实给出该产品和尺寸表，但未声明其完整产品标准，不改称普通 T651/T6。

## 主来源与适用范围

全部新数据仅保存 URL、组织、标题、revision/date、2026-10-01 检索日、短摘录、结构化观察/适用范围。没有把版权 PDF 或规范全文复制到仓库；临时 PDF 仅用于表格视觉核对。

| Organization | Source | Revision/date retained | Applicability |
|---|---|---|---|
| Sun Hydraulics | [Manifolds: Materials of Construction](https://www.sunhydraulics.com/sites/default/files/media_library/Product_Bulletin-Manifold_Materials_of_Construction%20update_v4.pdf) | 999-904-013, January 2024 | Sun standard/custom manifold construction only; no universal material pressure limit |
| Kaiser Aluminum | [Rod & Bar Alloy 6061 Technical Data](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1025/Kaiser_Aluminum_6061_Rod_and_Bar.pdf) | KA-RBH-6061-8.10 | 6061 rod/bar; extruded B221 and cold-finished B211 columns remain separate |
| Kaiser Aluminum | [Sheet Coil & Plate Alloy 6061 Technical Data](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1015/Kaiser_Aluminum_6061_Sheet_Coil_and_Plate.pdf) | Rev. 05/06 | 6061 flat products; typical tensile specimen 0.500 inch diameter |
| Kaiser Aluminum | [Sheet Coil & Plate Alloy 7075 Technical Data](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1017/Kaiser_Aluminum_7075_Sheet_Coil_and_Plate.pdf) | Rev. 05/06 | 7075 T651 flat product row; typical properties; no T6 tube substitution |
| Kaiser Aluminum | [KaiserSelect General Engineering Plate](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1043/KaiserSelect_General_Engineering_Plate.pdf) | Public brochure; revision/date not printed | Published plate ranges; not discrete engineering stock sizes |
| Kaiser Aluminum | [Flat Rolled Products — Summary of Specifications](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1010/Kaiser_Aluminum_Sheet_Plate.pdf) | KA-SP-AFSS3-1.09 | Historical capability listing; does not assert current mill certification |
| ASTM International | [ASTM B209/B209M-21 — Aluminum-Alloy Sheet and Plate](https://store.astm.org/b0209_b0209m-21.html) | B209/B209M-21 | Public standard-owner scope; product form and alloy/temper tables; no unlicensed normative document copied |
| Hydro Extrusion North America | [Alloy 6061 — Extruded Mechanical and Physical Property Limits](https://www.hydro.com/globalassets/01-products--services/extruded-profiles/americas/ena-resources/alloy-data-sheets/hydro_2019_data_sheet_6061.pdf) | 2019/01 (2/2019) | Standard T6 extrusion limits; special Hydro tempers are separate |
| Hydro Innovation & Technology | [Technical datasheet — Extruded products, Alloy EN AW-6082](https://www.hydro.com/globalassets/08-about-hydro/hydro-worldwide/germany/extrusion-germany/alloy-data-sheets/hydro-en-aw-6082.pdf) | 6082 Rev.2, 01/2019 | EN 755-2:2016 extruded profiles; open and hollow profile thickness limits differ |
| Hydro Extrusion North America | [Alloy 6082 — Extruded Mechanical and Physical Property Limits](https://www.hydro.com/Document/Doc/Alloy%206082.pdf?docId=560720) | Revision 2019/02 (3/2019) | 6082 extrusion product support; do not import NA limits as EN-profile limits |
| Saarstahl | [Material specification sheet — Saarstahl C45](https://en.saarstahl.com/app/uploads/2024/03/20160401102929-0503_C45.pdf) | Public specification sheet; date not printed | C45 per DIN EN 10083; normalization process; QT values not used for +N |
| SIJ Metal Ravne | [SIQUAL 0503 Steel](https://steelselector.sij.si/data/pdf/C45.pdf) | Copyright 2016 | C45 normalized section-size rows; producer labels properties typical/reference, not guaranteed certificate values |
| DIN Media / DIN | [DIN EN ISO 683-1:2018-09](https://www.dinmedia.de/de/norm/din-en-iso-683-1/291176752) | 2018-09 | Official public scope lists C45 and bar/forging forms; replaces EN 10083-1/-2. No paid normative tables copied. |
| Outokumpu | [Outokumpu Core range datasheet](https://www.outokumpu.com/-/media/files/products/core/outokumpu-core-range-datasheet.pdf?hash=0DB21994AD31F93E9C62A531BE9C36E6&modified=20251117111909&revision=025e9931-a1d5-4c8f-8ff5-f881d38916da) | 1560EN:4, November 2022 | 304/4301 and 304L/4307 flat products; ASTM A240 Table 6; EN properties kept separate |
| Outokumpu | [Outokumpu Supra range datasheet](https://www.outokumpu.com/-/media/files/products/supra/outokumpu-supra-range-datasheet.pdf?modified=20251117111951&revision=7a909396-d1f3-4d36-9c1c-99606be41fd2) | 1561EN:4, November 2022 | 316/4401 and 316L/4404 plate; ASTM A240 table; do not mix other EN variants |
| Dura-Bar | [Dura-Bar 65-45-12 Ductile Iron](https://www.dura-bar.com/products/ductile-iron/65-45-12) | Public product page; revision not stated | As-cast continuous bar; longitudinal mid-radius tensile sample; section-sensitive hardness |
| Dura-Bar | [Dura-Bar 80-55-06 Ductile Iron](https://www.dura-bar.com/products/ductile-iron/80-55-06) | Public product page; revision not stated | As-cast continuous bar; longitudinal mid-radius tensile sample; rectangle hardness by request |
| Dura-Bar | [80-55-06 Ductile Iron Product Brief](https://www.dura-bar.com/getmedia/ca3b3f47-82b1-428f-8e6f-83351f8e3888/80-55-06-ductile-iron-0319.pdf) | Form 99-75-00-86-00, 0319 | Historical standard wording retained alongside current explicit conformity statement |
| voestalpine High Performance Metals Australia | [AISI 1045 Datasheet 2026 v2](https://www.voestalpine.com/highperformancemetals/australia/app/uploads/sites/265/2024/08/Datasheet-1045-2026-v2.pdf) | Datasheet 1045 2026 v2 | Supply hot rolled/normalised; nearest-designation list is not a declared exact bar product specification |
| SSAB | [SSAB S355J2+N Zero](https://www.ssab.com/-/media/files/en/zero/data_sheet_2422_ssab_s355j2n_zero_2025_01_21.pdf) | Data sheet 2422, 2025-01-21 | Normalized-rolled structural plate, 6–60 mm; separate S355J2 designation, not generic S355 |
| Kaiser Aluminum | [KaiserSelect Manifold Bar](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1001/KaiserSelect_Manifold_Bar_Brochure.pdf) | KSR021-010412, copyright 2012 | Proprietary T6511B manifold bar; no silent inheritance by T6/T651 stock |

Sun 的 6061-T651 / extruded-bar 说明按公告原文身份保存，并由 Kaiser 6061 rod/bar 表格交叉支持。Sun 210/350 bar guidance 及 proof/burst 数值仅存 `OEM_APPLICATION` 参考，**不映射为 intrinsic material maximum pressure、yield 或 allowable stress**。Dura-Bar 80-55-06 的旧 0319 PDF 使用 similar wording，当前产品页明确 conformance；冲突两侧与明确 reviewed preferred identity evidence 一并保存。

## 参数、产品形式与 stock

继续使用唯一中央 `engineering_facts.py`，没有第二套 property resolver。补包经原 REV2 importer 的 `--material-supplement` 入口进入现有 v4 sources / identities / evidence / values / conflict / field-status 表。只允许精确身份的经审查参数；保留 MINIMUM / TYPICAL / NOMINAL / RANGE、测量说明和出处，不混合它们。

- 6061 T6 的 Hydro extrusion 下限与其他特殊 temper 分离；bar 与 plate 的 T651 分开。
- 6082 EN-profile 数据需要 profile type 和 raw-stock thickness；不会套用 NA rod/bar 条件或从 finished block 尺寸猜原料。
- C45 normalized producer 数据保持 diameter、producer variant 和 historical producer-standard basis；不会把旧表值声明为当前 ISO 的 design minimum。
- 不锈钢 ASTM plate 行与 EN 的 C/H/P 行分离；室温/stock-form 条件仍为显式条件。
- 7075 T651 的典型强度、Brinell 硬度和密度支持在其确切形式/条件下查看；不会套到 extrusion/tube。来源未声明 tungsten indenter，补包使用通用 HB，不写 HBW。
- Dura-Bar 最低 tensile/yield 来自 as-cast longitudinal mid-radius 样本；hardness/elongation 的 round-bar 尺寸条件不推广到 rectangle。
- 没有找到可直接采用的 material allowable/design stress，12 个默认值均为 null；**没有 yield / safety factor 推算**。原项目政策 2 / 4 mm / 7 mm 和用户覆盖行为保留。
- `material_stock` **268 → 268**，无新增工程库存；674 supplier records 独立保留。公开范围/临时库存不是完整 stock tuple；Kaiser 稳定 size 表属于另一个 T6511B 条件，未被移植到普通 T6/T651。
- 原 104 个 treatment 与已核实的旧身份关联保留。新身份没有基于近似状态继承 treatment，没有 auto-select 或新增 treatment 验证规则。

Model、Schematic cartridge facts、Engineering Review 与 AI 结构化事实仍使用原中央入口。材料评审不改变 Cartridge 技术事实或 compatibility。Core 材料请求为 bounded batch，约 61,487 bytes，本机一次读取约 13.8 ms；没有逐材料逐属性 evidence 请求。

## Legacy 与 UI

默认 `/api/materials` 只返回新工作可选身份。`include_legacy=true` 支持 Library 浏览；`current_id` 可附带当前旧身份。Model 只在旧项目已使用该 ID 时显示其 legacy 选项：`Legacy unspecified Aluminum` / `Legacy unspecified Dura-Bar`；不自动 remap，也不重写项目 JSON。Home 和 Guided 使用正常 selector 结果。

Library 明确显示 Engineering / Research-only / Legacy unspecified 和实际原因；primary identity sources 可直接打开。Raw evidence 没有 Place/Bind/Use 权限。

## 重建、本机替换及兼容

使用当前生产 v4 baseline、相同原始 REV1 / REV2 包和 `data/knowledge/core_materials_2026-10-01.json`。最终独立新库：`data/pmc_engineering.core-final-a.db`、`data/pmc_engineering.core-final-b.db`。早期 staging 仅用于检查，未晋升。

- 两库全部技术表（排除 timestamp batch 元数据）、materials、values、identity links、stock 内容摘要完全相同；中央材料返回对象也相同。
- 原七个 material_id 全部相同；其他 executable engineering 表、所有 Cartridge-domain 技术表与原库相同。integrity/FK 检查通过。
- Compatibility **24,948 → 24,948**，完整 sorted-row/key digest 都为 `1d6f05f4bd8c62e45546a40be9f73b74e3683e19e3d111cf257b1c8d6095dae9`。
- 补包 SHA-256 `ab5337034e8db09de482d78da31036e29ef4b9ed6a1c1cbef2deeec4692621e0`。
- 原生产 SHA-256 `1b0a4e23623d4a4b1b87b4d88dd075f9d75b96ae482ffd94c6095aa4dfee1e69`。
- 备份 `D:\Project\Manifold\data\pmc_engineering.pre-core-20261001.db`。
- 最终生产 `data/pmc_engineering.db`：schema 4，SHA-256 `4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`。
- 正常 `projects/saved/*.json` 的全部 hash 和数量核对未变化；浏览器测试只写 ignored `output/core-materials/qa`。数据库/ZIP 不提交 Git。

## 验证

- 76 focused Python passed，0 failed：material supplement/import/API、Engineering Facts、store/API、AI analysis/mounting。涵盖旧 IDs round-trip、selector 过滤、独立双库、standard/form/size/temperature/producer 条件、来源拒绝、generic S355 拒绝、1045/7075 理由、Dura-Bar、allowable 空值与 compatibility。
- 70 JavaScript tests passed；Vite build 成功。原 font runtime-resolution 和 bundle-size 提示保留。
- `python -m manifold prove`：invalid PASS 295 / WARNING 2 / FAIL 6；corrected PASS 268 / WARNING 1 / FAIL 0，保留无效样例。
- `git diff --check` 通过。没有跑完整 Python suite；既有 11 项 baseline exception 未重跑、未 xfail、未削弱行为。
- localhost 与 `http://192.168.253.117:8765` LAN 全部实际交互通过，secure context 分别 true / false，pageerror 0。验证 Home/Guided 新列表、旧两个 ID、Model 精确选择和保存、未推算 allowable、7075/1045 详情、只读 evidence、primary source popup、legacy Library。
- 视觉截图：`output/playwright/core-materials/localhost/`、`output/playwright/core-materials/lan/`；Model / primary evidence / legacy 页面已人工视觉检查。

涉及文件：

- `manifold/engineering_db.py`
- `manifold/engineering_facts.py`
- `manifold/import_technical_knowledge.py`
- `manifold/server.py`
- `manifold/technical_knowledge.py`
- `tests/engineering-inputs.test.mjs`
- `tests/library-ui.test.mjs`
- `tests/test_engineering_facts.py`
- `tests/test_technical_knowledge.py`
- `web/engineering-facts-ui.js`
- `web/engineering-inputs.js`
- `web/guided.js`
- `web/home-view.js`
- `web/library-ui.js`
- `web/main.js`
- `web/technical-knowledge-ui.js`
- `data/knowledge/core_materials_2026-10-01.json`
- `manifold/material_supplement.py`
- `scripts/check-core-materials-browser.mjs`
- `scripts/check-core-materials.py`
- `tests/core-materials-browser.run.js`
- `tests/test_core_materials.py`

本报告亦提交。最终 commit、remote HEAD 与 clean tree 状态在最终回复及 `output/core-materials/delivery.json` 记录，避免把提交自身的 hash 循环写入文件。
