# Main Station LIB on REV2 — Phase 1 integration

## Result

Combined staging is ready: `D:\Project\Manifold\data\pmc_engineering.rev2_relation_plus_lib.db`. Schema v6 adds 11 generic Library tables. Production is not switched. Active non-CAD targets: **3,059**, VERIFIED **2,875**, PARTIAL **184**, VERIFIED **93.98%**.

Starting branch: `codex/sqlite-domain-reset`. Starting HEAD: `c7e8d8d2ca7a33567fcccf34966c1456475ac7de`. No reset or unrelated changes. Final HEAD is the commit containing this report; the literal commit SHA is recorded after committing in `output/main-station-lib/delivery.json` and the delivery message.

## Inputs and output

- Handoff ZIP: `D:\Project\Manifold\PMC_MDTools_Library\PMC_Manifold_All_Useful_Knowledge_Main_Station_Handoff_2026-10-06.zip`; SHA-256 `43c0e510d98d8c92a65a45c5e2b99b79b9050ec3be9e5fb18dd16e51ee27b52f`; 2,260,960,260 bytes.
- Integration MD: `PMC_MDTools_Library/PMC_Manifold_Main_Station_Integration_2026-10-06.md`; SHA-256 `c3fb2a8893f596d5e210dd4d3137603d31b714c426804928a5a4e4fd84330091`.
- REV2 source: `D:\Project\Manifold\data\pmc_engineering.rev2_relation.db`; schema v5; SHA-256 `33f579801c38102011a3dbc55c0b9cfeb8c13a5434fcff8cd8260bc608fe27d2`; 1,519,075,328 bytes.
- Combined staging: `D:\Project\Manifold\data\pmc_engineering.rev2_relation_plus_lib.db`; schema v6; SHA-256 `930531e852c73985a04415069253fda569045d332740201262b8ef226f5019a9`; 1,827,905,536 bytes.
- Size delta: 308,830,208 bytes. Raw binary bytes imported **0**; CAD binary bytes imported **0**.
- Independent repeat: `D:\Project\Manifold\data\pmc_engineering.rev2_relation_plus_lib.delivery-repeat.db`; SHA-256 `ede886943e670a790b8bf727d2901b71ee8a9d331382c8ffa035e7fb50e3ebbd`. Logical data equal, excluding output-path metadata in `library_import_batches`.
- Production SHA-256: `4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`; matches the reviewed prior production fingerprint. Production DB and launcher configuration untouched.

## Domain results

Sources/evidence below are unique IDs linked from targets, not counts of raw source files. Version-conflict counts may overlap domains. Unresolved means missing target-evidence references; retained research gaps are separate structured findings.

| Domain | Targets | VERIFIED | PARTIAL | Linked sources | Linked evidence | ID versions | Missing evidence |
|---|---:|---:|---:|---:|---:|---:|---:|
| Closures / Plugs | 443 | 380 | 63 | 356 | 2358 | 1799 | 0 |
| Commercial / Cost | 9 | 9 | 0 | 57 | 87 | 17 | 0 |
| Cross-reference / Equivalence | 415 | 415 | 0 | 5 | 377 | 2 | 0 |
| External Ports | 271 | 271 | 0 | 52 | 1552 | 79 | 0 |
| Fasteners / Mounting Hardware | 84 | 84 | 0 | 47 | 207 | 1 | 0 |
| Fittings / Adapters / Port Hardware | 130 | 120 | 10 | 158 | 697 | 595 | 0 |
| Hydraulic Fluids / Compatibility | 24 | 24 | 0 | 82 | 252 | 204 | 0 |
| Inspection / Pressure Test / QA | 12 | 12 | 0 | 41 | 101 | 9 | 0 |
| Machining Knowledge | 18 | 18 | 0 | 40 | 122 | 13 | 0 |
| Manufacturer / Supplier / Lifecycle Registry | 9 | 9 | 0 | 26 | 29 | 3 | 0 |
| Manufacturing Policy / DFM | 9 | 9 | 0 | 19 | 42 | 7 | 0 |
| Non-relation Cavity Knowledge | 63 | 62 | 1 | 28 | 458 | 151 | 0 |
| Production Drawing / Manufacturing Documentation | 15 | 15 | 0 | 37 | 68 | 37 | 0 |
| Seals / O-rings / Backup Rings | 1138 | 1136 | 2 | 224 | 2310 | 873 | 0 |
| Standards Registry | 177 | 175 | 2 | 182 | 238 | 85 | 0 |
| Surface Treatments / Coatings | 105 | 18 | 87 | 29 | 232 | 4 | 0 |
| Thread Standards | 122 | 103 | 19 | 43 | 288 | 24 | 0 |
| Tooling | 15 | 15 | 0 | 50 | 387 | 8 | 0 |

## Merge boundaries and retained scope

- Baseline supplies target identities and states. Only CLOSURES_2026-10-06_REV04, PORTS_2026-10-06_REV03 and THREADS_2026-10-05_RUN01 dispositions are applied, each once. VERIFIED increments require resolving evidence and explicit verification scope. Computed target/status sets match the proposed queue; the proposed queue itself does not grant status.
- Accepted Seal REV04 is reconciliation only. Its baseline content is retained, not appended a second time. Material/fluid/temperature/pressure/velocity/backup-ring conditions remain in original structured rows.
- External Ports: 271 reference identities VERIFIED; thread identity 271, sealing coverage 206, geometry-source coverage 159. **Gate C FAIL retained**. Runtime 446 ports, geometry, usable flags and row hashes unchanged. No research row deactivates a working port.
- Closures: 380 VERIFIED / 63 PARTIAL. **Gate A FAIL retained**. No insertion into runtime closure definitions (still 0); no inferred pressure, port compatibility or machining.
- Threads: 103 VERIFIED / 19 PARTIAL; historical Gate B PASS retained. Rp/Rc/R, NPT/NPTF, UNC/UNF and unresolved UN remain literal source fields. Runtime 833 threads unchanged.
- Surface treatments retain 18 VERIFIED / 87 PARTIAL. DFM/QA/Drawing rule types and supplier snapshot dates remain in original rows. No cost-engine, CAD, AI, routing or workflow changes.
- CAD targets excluded: **1,824**. No full ZIP extraction. No document/CAD blobs. Source localization stores paths, byte counts and hashes only; the archive is not a runtime dependency.
- Legacy reference-only rows never override active rows. No similarity-based runtime matching or execution compatibility links were created.
- Cartridge technical reconciliation: 15,005/15,005 manufacturer + exact-part keys already present. Material package has 10 stable IDs, all present among the 17 existing research identities; the newer station identities are preserved. Neither specialized layer is rebuilt.

## Discovery, deduplication and diagnostics

- ZIP CRC checked by streaming. Duplicate archive paths rejected. Manifest membership/size, index/source map consistency and SHA-256 of each consumed structured file validated. CSV/JSON/JSONL parsing rejects malformed data.
- LIB_DATASET_INDEX omits 264 consumed remaining-domain/increment members. They were discovered via the top-level manifest/source map and domain audit structure, with identical hash checks. This is a package index gap, not an import failure.
- Unique datasets 247; dataset aliases 264; structured rows 80,075; evidence 16,067; sources 2,183; lightweight source-path aliases 18,315; target-evidence links 13,379.
- Identical native-ID content reused: `{"evidence": 18280, "source": 2338}`. Differing native-ID versions retained: 3,505. Canonical views use domain baseline, unified baseline, then designated increments. Original versions plus dataset provenance remain inspectable; these counts are not a claim of 3,505 contradictory engineering facts.
- Missing evidence references: 0. Native IDs split on both pipe and semicolon; the real closure row using a semicolon now resolves both existing evidence IDs. No source/evidence was invented.
- Native research conflict/unresolved datasets and field findings are retained in `library_records`, even when target verification is complete. VERIFIED reference identity is not an execution admission.
- Query access: `manifold.library_knowledge.browse()` / `detail()` provide pagination, statuses, gates, findings, evidence, sources and archive localization. No new UI or network endpoint in Phase 1.

## Exact preservation proof

All **36** pre-existing runtime, REV2 relation/audit, Cartridge Technical and Material Technical tables have equal before/after sorted logical row hashes. Source file SHA is rechecked after import. Relation evidence 16,066; execution-eligible 13,068; valid physical pairs 26,081; Cartridges 15,665; relation-only 660; supplement logical/physical 5/10; supplement relations 5; execution supplement pairs 0; pending 233.

| Protected table | Rows | Identical before/after SHA-256 |
|---|---:|---|
| `cartridge_cavities` | 26,081 | `efa37f025902a11de6828f60b2dec963a0e13ed55e4eca3192db81e92f33d865` |
| `cartridge_cavity_evidence` | 16,066 | `1209d46ef76fd5de233b5a32c2dbe65252cbdfd2e7194b3ef8e7c804ff7acc85` |
| `cartridge_cavity_evidence_links` | 31,972 | `0479c535e17073b0e39b8a85140b1a132742078ebc53dbf6e8db378b12d4663c` |
| `cartridge_cavity_supplement_links` | 10 | `1272b0363cce13f2c55cb0e617274217ed95886af4d14b6a50c6b234e779210e` |
| `cartridges` | 15,665 | `84dde7f8831911d6259710cac9b18b341fef903a89d543dfe58d1b836d98330c` |
| `cavities` | 6,429 | `41cd119dfd38ae6705b366da1ed6ff1d468f74ec5636cb36e930483a6ea85c3c` |
| `cavity_interfaces` | 16,347 | `f91176e0212efdb4396bcfe8a9b206b338e8f3bb530aff423627a3c1b2d495d4` |
| `closure_definitions` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `external_port_definitions` | 446 | `3d3120d15b39cc405b802b44b71a906e20cbbd0a2ee2ab5202df823207924b4e` |
| `kb_cavity_supplements` | 10 | `6355f4ba8a360e14bb7a85fb5a1bba9afcbaf8fe94ff528a289c24a35976ed0d` |
| `kb_import_batches` | 1 | `d56c533da5deae92e20377d1620b3940de9a8281e90c9507b3937dffe9e29808` |
| `kb_logical_cavity_supplements` | 5 | `ff25b107e317d9f78c38e0b520b0b60f2f4d42527b0cd259c0de24ea139f4424` |
| `kb_pending_registry` | 233 | `c124cb522448e7a8eaf97a446f55029207dbdea70d443f3ef2b2acd41786a0cb` |
| `kb_relation_migrations` | 1 | `1f0c7347dd1ce109a8afbcf6b0dc00bb023d669a97504429de4b28a8c5ef0957` |
| `machining_modifiers` | 326 | `6795ce8caaa4517766e5e95e1eb5b5ffdae38f9b991fa3bd0102ff5bdecf1ca5` |
| `manufacturing_policy` | 1 | `1e51ec4ab781388998636c63656b63982efbd405edb76b4f984f05c0d8aa2155` |
| `material_research_links` | 934 | `86dbad7f55efb61131e583ddcd195137efb4c2dca009665c67caec2bd196443d` |
| `material_stock` | 268 | `3b933829d7f085c5f98bcd2cfca5b39e5e85b949518944d3d2c0799e48b419ff` |
| `material_supplier_stock` | 674 | `63f8279b60892245e8df43cfb3541dc7a2e352c99dec09966bbdebe6d4fec07d` |
| `material_surface_treatments` | 104 | `588a6d297ae91a2d254862b38d1545690f8ac98f59e8c4329b1f3dac982653c2` |
| `materials` | 14 | `912106a370a352ea6f78b7cc5a90261afa0ad208a508a9f3ef32ad8aea3f5a32` |
| `technical_conflict_evidence` | 58,040 | `4efc21152da2ad30aabc9b2077efb49529be3a0d6f9c9717caae1e6ddcd9dc0f` |
| `technical_conflicts` | 179 | `c3f2ad8dff801125df42b2df05f99eb9adc0990f06cc9609c25f80550788e1c0` |
| `technical_evidence` | 229,012 | `b83a6a559f7ef5e1524988330f020819dae389ba717718bfec58dd572d52b6bd` |
| `technical_evidence_observations` | 260,430 | `dee386ea5aad4365e3e300892b21c54c79d369eb85b71da151a6c24a209882f5` |
| `technical_evidence_sources` | 229,424 | `54fdf179a1603090ff61aaaf84fbeac9d144adb40af09438d2b8542813851266` |
| `technical_field_status` | 195,116 | `5f7d3e15bcaa6c6d6aa0930c833178344901be47dc63079e33a45818a94efe37` |
| `technical_identities` | 15,022 | `963f04da8280aa69515ebd6a60f33f3e21bad36c5f5e3803da0c2a1f8cc00bb9` |
| `technical_identity_conflicts` | 155 | `2e692f8685aa14d5f0a8593999d29157ebfc56bcc973827099957cc3ea8ba384` |
| `technical_identity_evidence` | 229,257 | `1c8247b8e16752007c23cd83f57f2a2c8b6b0938a181b9a47b23cd288f29ba56` |
| `technical_import_batches` | 1 | `d85e9a28e153ef337cc093f0f50cf8449f2d0105a36f37a3d050742f6bc2562a` |
| `technical_source_aliases` | 10,108 | `22cf10e409e7a6c1c30a22b63ceb1ad43ed4fb13f1de066398bce693ab2c5254` |
| `technical_sources` | 10,126 | `6dad06f4848a6043fa9e1cc21071834a34f76906eb5747733de7b202e48cae75` |
| `technical_values` | 228,244 | `20a7f2c98593f2b0b58a256c6829f2a0716d9410f7c6b674b5271317888008b3` |
| `thread_definitions` | 833 | `0feddfb54f68c5cc879a536e08967157d7a83c941e33dba49a07b6c1d0d81bce` |
| `tool_definitions` | 412 | `106afae6a0360e062112053aeec67d985e2ac10a0fd98c5f2456db2af176638d` |

## Verification scope

- Import integrity: `PRAGMA integrity_check = ok`; foreign-key violations 0. Independent delivery rebuild: all logical tables equal except batch output-path metadata.
- Application startup: ASGI lifespan PASS with process-local combined DB; `/api/health` HTTP 200 and `/api/catalog/manifest` schema 6. No production server/launcher switch; no browser/UI changes.
- Focused Library/import/API checks before the latest scope reduction: 30 PASS / 1 SKIP. The final separator correction is confirmed by the real import yielding 0 missing evidence references; no additional suite run.
- Vite build PASS; git diff --check PASS.
- Already-started JS suite: 65 PASS / 19 FAIL; same 19 failures reproduced on this task's actual starting HEAD c7e8d8d. No frontend code changed.
- Already-started Python suite finished before the user's stop instruction: 474 PASS / 47 FAIL / 1 SKIP (1,022.68 s). These are recorded without claiming all 47 are unchanged baseline failures; this task did not rerun a baseline comparison after the user explicitly said no audit/regression/unnecessary testing.
- Latest user instruction takes precedence over the original broad regression checklist. No more broad tests, baseline audit, prove, or long validation was performed.

## Remaining Library-only gaps

- 184 PARTIAL targets remain PARTIAL; Port Gate C and Closure Gate A remain FAIL within their research scope. No execution claims are derived from these research states.
- The incomplete package dataset index and 3,505 native record-version differences remain explicit diagnostics. Phase 1 provides backend research storage/query helpers; UI/runtime application of these facts is outside this task.
- Production activation remains a separate decision. Combined staging and all raw inputs are excluded from Git.
- Machine-readable import details: `output/main-station-lib/import-delivery.json`; repeat: `import-delivery-repeat.json`; logical equality: `determinism.json`; startup: `startup.json`.
