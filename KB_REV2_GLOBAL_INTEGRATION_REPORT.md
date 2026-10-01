# KB REV2 Global integration report

Completed against the execution-time HEAD with the owner-approved baseline test exception. Production promotion is not part of this delivery.

## Baseline and delivery

- Starting HEAD: `bc1e43327185d1e396eb22ca43e8c5cc7bc5360a`. Active branch: `codex/sqlite-domain-reset`.
- Starting worktree was clean; newer routing, incremental preview, source protection and Library navigation fixes were preserved.
- Final HEAD: the delivery commit containing this report (`git rev-parse HEAD`). The literal commit/remote SHA is recorded after commit in `output/kb-rev2-preflight/delivery.json` and the delivery message; a commit cannot contain its own hash.
- Only source, tests and documentation are committed. Research ZIPs, raw PDFs/CAD, databases, baseline export, screenshots and logs remain ignored local artifacts.

## Databases

| Artifact | Schema | SHA-256 |
|---|---:|---|
| `D:\Project\Manifold\data\pmc_engineering.db` (production, read-only) | 3 | `0edff3d3796b2d2fee6c733c19b0ca582bc3a5a4f5abccce314c2ba998ef0b6a` |
| `D:\Project\Manifold\data\pmc_engineering.rev2.db` (delivery staging) | 4 | `e8f6eac9084ab4a7befd1290a3b5d3aaee7edfabd7fe3a0dcae8904baea13c24` |
| `D:\Project\Manifold\data\pmc_engineering.rev2.repeat.db` (independent repeat) | 4 | `8767e22931ffb74011d4e9ad405516753d846db5cb51d0b44f43b57fc290cefb` |

Staging size: 1,512,161,280 bytes. Production unchanged: **YES**. Existing materials, 268 runtime stock rows, custom/legacy cavities, interfaces, threads, all REV1 evidence and all execution eligibility flags were preserved. Every existing engineering table has identical sorted-row counts and SHA-256 before/after import; the full comparison is saved in both staging import reports.

The runtime now validates schema v4. Default launchers still point to the unchanged v3 production file and will reject it until a separate owner-approved promotion. Startup never creates, repairs, upgrades or silently imports a database. Browser acceptance uses a process-only staging override and isolated project/output storage; normal projects and immutable builds were not changed.

## Read-only inputs and validation

REV1: `D:\Project\Manifold\PMC_MDTools_Library\KB_REV1_2026-09-26.zip`.
SHA-256: `bd02e61ea7b92c747ec6e5f7942e4c4618a27a236d49d083a3c0a48cd9df3a16`. CRC and required files pass; 15,272 relations, 3,689 logical master rows, 6,872 physical/crosswalk rows and 5 supplements.

Global/Sun/Material bundle: `D:\Project\Manifold\PMC_MDTools_Library\PMC_Manifold_Global_Cartridge_Technical_Handoff_2026-10-01.zip`.
SHA-256: `3a8dea4d38fc14fe8169697be465ea2fa492ea343da0b722d036385c07af4a80`. Size 52,700,434 bytes; 64 entries, all 63 manifest payload size/hash checks pass.

Global and Material convergence audits, complete dispositions, evidence/source/conflict pointers, scope vocabularies and stock-source URLs were validated before output creation. The repaired package removes 26 dangling master references, retains scope originals/details with explicit mappings, adds source aliases, distinguishes six source-review records, and supplies conflict evidence-ID arrays. No research was redone and no missing technical value was invented.

Primary data file metadata follows. ZIP-relative paths resolve under the bundle above. Full field/schema lists, hashes, sizes and counts for **all** manifest payload files are retained in staging `technical_import_batches.report_json` and `output/kb-rev2-preflight/staging-build-1.json`.

| ZIP member | Bytes | Input records | SHA-256 |
|---|---:|---:|---|
| `conflicts/GLOBAL_CARTRIDGE_CONFLICTS.csv` | 2,743,869 | 144 | `020dd95f9b7e7ddbf4e36c66e309337eb20456330d0d365f8f39818cc2ecb90a` |
| `evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl` | 250,219,790 | 225,404 | `0276328213e2498fdba9305176b05362b9f2de230a647eadf5e44f4d57f68e8e` |
| `evidence/SOURCE_REVIEW_EVIDENCE.jsonl` | 10,883 | 6 | `443931682ed80b501d6b484e1f5b99922353fa592d3dea7c06b9a56408623884` |
| `material/MATERIAL_CONFLICTS.csv` | 22,404 | 34 | `52917df38445517424b6f8dbac72fda516e8c2ea9c0ffccefa10164730e16684` |
| `material/MATERIAL_COVERAGE.json` | 62,002 | 1 | `ff4da4753fb4f1890e7bf4261d9752c8fc760087dcd02e9c2196a81edbe35c58` |
| `material/MATERIAL_MASTER.jsonl` | 250,701 | 10 | `c77039536073a716facb7a895244b26e6708415924265cc4480347b547779863` |
| `material/MATERIAL_PROPERTY_EVIDENCE.jsonl` | 1,002,627 | 816 | `b14af8171966b422ea0881fe84367411a4e53d298b5ac35b2b2f4e04bb34a70b` |
| `material/MATERIAL_SCOPE_MAPPING.csv` | 14,556 | 83 | `b44748ec2a53498aa3bc1ae81a6c04585412e3a53641687cacdbe0c18b3f2d74` |
| `material/MATERIAL_SOURCE_REGISTRY.csv` | 134,194 | 191 | `eb71423e2a1ddcee95466da43da1af2e0fc5eac651639e41919c2d24705cfdcc` |
| `material/MATERIAL_STOCK_EVIDENCE.jsonl` | 1,004,349 | 674 | `1df510e10e3d423d90eaa9e44f947cd50d2d8735bd7872acbff0596ef1ec385c` |
| `material/MATERIAL_STOCK_MASTER.csv` | 364,724 | 674 | `361bda40f1d1c4e089ecb3eaaf1016e542eb4512eb202d6644fb74e1b815e386` |
| `material/MATERIAL_SURFACE_TREATMENT.jsonl` | 91,755 | 104 | `4ded755fd3dab5680b437b2b167e06c44bcc744ea58d92981eace331032939a8` |
| `material/MATERIAL_UNRESOLVED.csv` | 1,394 | 10 | `4893cbf2fcc87d36daedada40d4d0587707e7c89135199e5f299706a5295d3f1` |
| `normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv` | 7,123,599 | 15,005 | `79939e42d0f57a8378fbfe4791aeec2b699cbc01c840e2b68257d75884b35c8c` |
| `normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl` | 26,941,036 | 8,896 | `67672fd98842e461f9aed5ed3b9c1d023bcec282078ddea3b60cae3a5969ca9e` |
| `normalized/GLOBAL_FULL_PART_TO_BASE_MODEL.csv` | 2,022,926 | 7,400 | `07de61e55368fa31f761e81f5c0d19e4e7bd15f9364ee6431ed5e9386a0b2de2` |
| `normalized/MANUFACTURER_ALIAS_INDEX.csv` | 5,573 | 44 | `b0232d20a1c1b453aa134c5f8f1599dd933546df45d19f43f3c7e895a7a63122` |
| `normalized/MANUFACTURER_OPTION_CODE_INDEX.csv` | 282,754 | 1,008 | `833119d416ee159ea32ec755ef0e3ef9bf91a9f304f9b7d3c2cb4b6c76f9b2e2` |
| `sources/CARTRIDGE_SOURCE_INDEX.csv` | 18,821,021 | 15,272 | `7037000ff42a11284cc3fe18cc9de665afeaec502150a446bbc6f3a4d8e0cadd` |
| `sources/GLOBAL_SOURCE_REGISTRY.csv` | 8,122,932 | 9,845 | `ca1a091a819acea642fad0c209944de46f556b80e6ca681846ac682364e2eb35` |
| `sources/REV1_SOURCE_TARGET_EDGE_DISPOSITIONS.csv` | 47,190 | 175 | `f2fdcae3a92521fe1762488b4670ee22e2f3088811d56824eeb381e02ebbdf37` |
| `sources/SOURCE_ID_ALIAS_INDEX.csv` | 962 | 3 | `850045181123f333ffea246c846dbfd19e2ac8eed6aaddce0b0449eb0c75b999` |
| `sources/UNIQUE_SOURCE_INDEX.csv` | 5,621,424 | 6,094 | `e727bb0789a2c69480cf0f94d1368e4ed0c7d05a48899a333808cab931ba9c04` |
| `sun/SUN_ASSET_INDEX.csv` | 1,099,884 | 2,738 | `a530787dc4f63407503c78d630882e81effd6c3f65dcd8196dbfe7fd31edec8b` |
| `sun/SUN_CAD_ALTERNATE_INDEX_AUDIT_2026-09-28.json` | 7,550 | 1 | `4fbe40ee4900f5461fd8a498c92a967658662bd0ea4131f2bc0db8c330af1596` |
| `sun/SUN_CAD_AVAILABILITY_AUDIT.csv` | 1,523,369 | 897 | `0e632e909709bb323d7aeb760aeadf0a5d58e48b4338e4091f313fa7ec005334` |
| `sun/SUN_CARTRIDGE_TECHNICAL_MASTER.jsonl` | 5,829,806 | 897 | `7be21c39eaaa0cc93c1fed72349f5cc7deaa692375c86bc358aa86c9d96ed1b6` |
| `sun/SUN_CONFLICTS.csv` | 27,155 | 67 | `616a01467a983f9155e7b0d30a8787cbbe06ca5254bc05cd897712cdd689186f` |
| `sun/SUN_COVERAGE.json` | 320,171 | 1 | `b2db853f10aa4f6737d82c6f89c99b479f2e471567f1fa7db40801487a4e9647` |
| `sun/SUN_FULL_PART_TO_BASE_MODEL.csv` | 595,022 | 1,768 | `c8ccf0d6ead57eab4ed3babbb2d973e42f3538f11c79dcd52b56071d60e73c2b` |
| `sun/SUN_IDENTITY_EVIDENCE.jsonl` | 1,594,456 | 1,272 | `2a8d7bd6a6685571217ea30547e32a520be07dfffeb2ae79e6d81b3f2b24f564` |
| `sun/SUN_OPTION_CODE_INDEX.csv` | 47,354 | 278 | `c04a11a28c4deb1d34e8d53aa5b649c24aac2d5e7f3dee6d27b7442e00f813db` |
| `sun/SUN_PARAMETER_EVIDENCE.jsonl` | 38,209,144 | 32,477 | `cf95897938e463a9b8768c040a1cd4b9f0548c30cc19663f4c11c787b5647788` |
| `sun/SUN_SOURCE_REGISTRY.csv` | 2,337,192 | 3,814 | `b4bb5e2d0e3ffcc854e08d2c14e14ad88c9adfaf23d4f994adf481480f2976fe` |
| `sun/SUN_TRUE_UNRESOLVED.csv` | 4,601 | 4 | `ec6bc099e8575909d01957641551183d83eea774cb5a9ab79e8e8b6ad8037490` |

## Actual staging statistics

| Domain / layer | Rows |
|---|---:|
| Existing Cartridge identities, all represented | 15,005 |
| PARTIAL_CONFIRMED / RELATION_SOURCE_ONLY / IDENTITY_AMBIGUOUS | 14,985 / 5 / 15 |
| Global parameter evidence input | 225,404 |
| Global unique evidence IDs | 225,134 |
| Independent Sun parameter / identity input | 32,477 / 1,272 |
| Cartridge evidence after union/dedup | 227,462 |
| Cartridge parameter / identity / source-review classes | 225,750 / 1,706 / 6 |
| Cartridge source registry (deduplicated declared IDs) | 9,914 |
| Cartridge conflicts / Material conflicts | 144 / 34 |
| Material identities / property evidence | 10 / 816 |
| Surface treatments / supplier stock evidence | 104 / 674 |
| Material sources | 191 |
| Stock LISTED_SIZE / dated LIVE_STOCK / UNKNOWN_AVAILABILITY | 647 / 12 / 15 |
| Total technical evidence / preserved dataset observations | 228,952 / 260,370 |
| Identity-evidence links / current value observations | 229,197 / 228,202 |
| Field-gap status rows | 195,065 |
| Conflict-evidence links | 58,038 |

Count reconciliation: the 225,404 Global input rows contain 270 identical duplicate rows. There are 279 identical duplicates across the included datasets. Independent Sun data contributes additional identities/evidence, so the union is larger than the Global-only file. Source index 6,094 and Global registry 9,845 are distinct datasets; the imported registry also includes standalone Sun-only sources. Material coverage originally counted 190 sources; the explicit repair registers Steelbars UK, making the actual count 191. No audit counts were forced onto imported data.

Stock export IDs collide across different thicknesses: 27 extra distinct observations across 10 original-ID collision groups. Complete-record hashes provide deterministic internal IDs while preserving original IDs and every raw row. All 674 rows remain. A reference to an ambiguous collided ID is rejected; no thickness or preferred record is guessed. Supplier listings never enter `material_stock`.

Attribution limits are retained: 6,027 Cartridge evidence records have no explicit link to a current runtime identity (including discovery/source-level context), and 45 Cartridge conflicts remain outside the matched runtime identity set. They remain stored with valid evidence/source links. All 674 stock records have their own evidence and supplier layer; they are not general technical parameter values. Of 14,985 PARTIAL_CONFIRMED targets, 14,984 have parameter values. Integrated Hydraulics (Eaton) PPD2 preserves its supplied disposition but has no attributed value: the package names its ten PPD2 facts under **Eaton Vickers**, with no explicit manufacturer alias/master mapping. The importer does not silently transfer them between manufacturers. Its Library detail explains this limitation. Ambiguous and relation-only targets get no automatically inherited parameter values.

## Schema, API and Library behavior

Normalized `technical_*` tables separate identities, sources/aliases, evidence, original dataset observations, identity associations, value observations, field outcomes and conflicts. Material treatment/stock tables stay separate from executable materials. Shared evidence is attached through explicit identities/base mappings with source scope, original wording, applicable option and condition retained. No unresolved winner is inferred from conflict prose; source review and identity evidence never become parameter values.

Existing Engineering Library categories remain. Cartridge detail now exposes identity/disposition, technical sections, bounded/lazy evidence with filtering/pagination, conflicts and source links alongside unchanged execution-safe compatibility. Materials & Stock shows the two existing runtime materials plus ten research grades, with treatments and a separate supplier evidence section. Only complete HTTP(S) URLs become links; local artifacts and composite addresses stay provenance. Detail/back search state and async request guards remain intact. No technical evidence has Place/Bind/Use controls.

Read-only endpoints: `/api/cartridges/{id}/technical`, `/technical/evidence`, `/technical/conflicts`; `/api/materials/technical` and `/{id}`, `/{id}/evidence`, `/{id}/conflicts`, `/{id}/stock`. Existing `/api/materials` continues to expose only runtime material/stock data. Evidence limit is at most 100, conflict page limit 20 and per-side previews are bounded. SQL is parameterized; summary value observations are bounded at 200 with an explicit remaining-count notice. Technical search is opt-in for the Library API; AI identity search keeps its previous manufacturer/model/function matching.

## Compatibility and deterministic rebuilding

**24,948 execution-safe pairs before = 24,948 after; full key sets equal.** Sorted pair-key SHA-256: `e01be8c299d553977c7a6a8b29f886de9844431eabb90e1c11f19d2c055c5d0b`. Every pair passes the unchanged `compatible()` query. Physical and logical candidate queries were compared before/after for 16 distributed identities. Existing compatibility/AI-resolution tests pass; no whitelist, resolution policy, routing rule, geometry or minimum-wall rule was relaxed.

Two new staging files were built independently from the same unchanged source DB and package. Primary-key sets and row counts match for every technical table, including stable import batch IDs. Imported-at/batch metadata explains different binary file hashes. Synthetic tests also compare the complete logical technical rows excluding timestamped batches. Output existence is still a hard rejection; there is no in-place upsert/migration framework.

Both stages: `PRAGMA integrity_check = ok`; `PRAGMA foreign_key_check = 0 rows`. Results/key digests: `output/kb-rev2-preflight/determinism.json`, `compatibility-regression.json` and the two staging import reports.

## Verification and explicitly approved baseline exception

- Final full Python suite: **409 passed, 11 failed**, 26 warnings; 920.71 s. Full XML/log: `output/kb-rev2-preflight/python-final.xml` / `.txt`.
- All 11 failure names and corresponding failures were reproduced using an unmodified Git export of starting HEAD `bc1e433` with the original v3 engineering DB: **11 failed**, 83.44 s. Baseline export is retained under `output/.kb-rev2-baseline-head`; comparison log/XML under `output/kb-rev2-preflight/baseline-failures.*`.
- Owner explicitly authorized delivery/push with these unchanged baseline failures on 2026-10-01: **“允许基线例外，保持范围并提交/push”**. They are not hidden, marked xfail or fixed by weakening engineering rules. The only newly failing schema-3 literal assertion was adapted to `SCHEMA_VERSION` and passes.
- Focused importer/schema/compatibility/API/project checks: **25 passed**. Tests cover invalid manifests/references/scopes/audits, duplicate evidence, source review exclusion, full source preservation, deterministic rebuilding, FK integrity, scope/status/flow distinctions, stock ID collisions and ambiguous references, manufacturer aliases preserving IDs, read-only APIs and v3/v4 startup/import behavior.
- All JavaScript `.test.mjs`: **66 passed, 0 failed** with `--test-isolation=none`.
- Vite build: **PASS**. Existing large-chunk/runtime-font warnings are retained.
- `python -m manifold prove`: **PASS**; invalid fixture **295 PASS / 2 WARNING / 6 FAIL**, corrected **268 PASS / 1 WARNING / 0 FAIL**. Proof artifacts remain in `output/kb-rev2-proof`.
- `git diff --check`: **PASS**.

Unchanged baseline failures:

- `tests.test_ai_generation::test_ai_generation_is_editable_and_uses_sqlite_ids_without_embedded_library`
- `tests.test_ai_routing_consistency::test_existing_external_port_is_open_exact_terminal_after_move`
- `tests.test_cad_execution::test_slow_preview_does_not_block_apis_save_or_exact_build`
- `tests.test_hydraulic_sizing::test_freeze_displayed_proposal_without_resolution_and_later_flow_change`
- `tests.test_hydraulic_sizing::test_construction_access_uses_route_size_and_missing_flow_is_unresolved`
- `tests.test_production_machining::test_metric_and_inch_projects_keep_mixed_standard_ids_cad_tools_and_drawing`
- `tests.test_sqlite_domain_reset::test_import_admission_and_source_boundaries_are_conservative`
- `tests.test_v1_engineering_views::test_explicit_optimization_budget_is_total_exact_evaluations`
- `tests.test_workflow::test_auto_route_reproduces_demo_and_follows_terminals`
- `tests.test_workflow::test_unknown_net_color_build`
- `tests.test_workflow::test_freeze_keeps_exact_contacts_and_roundtrips`

## Real browser and visual acceptance

- Localhost: `http://127.0.0.1:8765`, `isSecureContext === true`: **PASS**.
- Actual LAN: `http://192.168.253.117:8765`, `isSecureContext === false`: **PASS**.
- Both exercised projectless Dashboard, actual Cartridge search and detail, Sun CBDH technical values/compatibility, evidence pagination, source URLs, both conflict sides, IDENTITY_AMBIGUOUS, RELATION_SOURCE_ONLY, material properties/treatments, separate engineering/supplier stock, and actual Guided standard external-port selection followed directly by cavity selection. No browser page errors or technical execution controls. Screenshots visually inspected.
- Reproducible commands: `node scripts/check-rev2-browser.mjs http://127.0.0.1:8765` and the actual LAN URL above, against the process configured with staging SQLite. Real project/output storage was isolated under `output/kb-rev2-browser-data`; no provider calls or production data writes were used.
- Results/screenshots: `output/playwright/rev2/localhost/` and `output/playwright/rev2/lan/` (acceptance.json, dashboard, Cartridge/evidence, conflicts, ambiguous, relation-only, material, Guided port/cavity images). The temporary acceptance service is stopped after verification. Launcher defaults are not changed.

## Remaining boundary

Production promotion remains a separate owner-approved task. The 11 pre-existing regression failures remain as the explicitly approved exception above. No unapproved research facts, manufacturer equivalences, compatibility pairs or automatic pressure/flow/material decisions were added.
