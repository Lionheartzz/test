# KB REV2 Relation Replacement Integration Report

Date: 2026-10-06 (Asia/Singapore). Branch: `codex/sqlite-domain-reset`.
Starting HEAD: `8d8e3125ee1af0649eaa9d0ce0e559939fbf8e0b`.
Final HEAD / integration commit: recorded after commit in [delivery metadata](output/rev2-relation/delivery.json), and in the delivery message. A commit cannot embed its own hash.

## Inputs and outputs

- Source DB: `D:\Project\Manifold\data\pmc_engineering.db`; schema **4**; SHA-256 `4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`.
- Staging DB: `D:\Project\Manifold\data\pmc_engineering.rev2_relation.db`; schema **5**; SHA-256 `33f579801c38102011a3dbc55c0b9cfeb8c13a5434fcff8cd8260bc608fe27d2`.
- Independent repeat: `D:\Project\Manifold\data\pmc_engineering.rev2_relation.repeat.db`; SHA-256 `be9b1cad178197af47e9ea4c0f3e16c1aa23c91753ec1ac13034c90cdf30f335`.
- REV1: `D:\Project\Manifold\PMC_MDTools_Library\KB_REV1_2026-09-26.zip`; SHA-256 `bd02e61ea7b92c747ec6e5f7942e4c4618a27a236d49d083a3c0a48cd9df3a16`.
- REV2 actual path: `C:\Users\Zhou Ke\Desktop\KB_REV2_2026-10-05.zip`; SHA-256 `de7089dede165182500fd7a30ecdc31b86ae98099192cb27a5d51ebffcf2b372`. Matches the reviewed package exactly.
- The source is the current production v4 database, including the later core materials integration. It is byte-identical to the approved `pmc_engineering.core-final-a.db` baseline; the older technical staging had fewer materials/evidence and was not selected.
- ZIP, DB binaries, research files and browser screenshots are not Git-committed.

## Replacement and admission

| Metric | Actual |
|---|---:|
| REV1 relations | 15,272 |
| REV2 relations | 16,066 |
| Relation IDs retained / added / removed | 15,272 / 794 / 0 |
| Retained rows changed | 1,354 |
| Cartridge IDs retained / added / removed | 15,005 / 660 / 0 |
| Current Cartridge identities | 15,665 |
| Existing technical target identities preserved | 15,005 |
| Relation-only identities without technical rows | 660 |
| Missing technical target identities | 0 |
| CONFIRMED / PROBABLE | 13,078 / 2,988 |
| Normal RESOLVED relations | 16,060 |
| UNRESOLVED_MASTER / TYPE_MISMATCH | 0 / 1 |
| REFERENCE_ONLY_SUPPLEMENT | 5 |
| Execution-eligible relations | 13,068 |
| Resolved policy holds | 2,992 |
| Execution pairs before / after | 24,948 / 26,081 |
| Execution pairs added / removed | 1,133 / 0 |
| Physical evidence links | 31,972 |
| Duplicate relations / normalized identity collisions | 0 / 0 |

The old active evidence, runtime evidence links and imported batch were removed transactionally in the new clone. The complete REV2 CSV replaced them, including all 1,354 retained changed rows. Every stored `source_row_json` was compared to the package 25-field row. Existing Cartridge rows and stable IDs were preserved exactly; new identities use the existing deterministic stable-ID convention, blank function and `{}` ratings. No technical rows were manufactured for the 660 extras. `import_mdtools` only gained current-schema acceptance for its existing read-only custom/legacy preservation source; it was not used to rebuild the real MDTools database.

Source-field changes: `{'source_name': 786, 'source_url': 278, 'document_name': 738, 'evidence_text': 1031, 'confidence': 172, 'updated_at': 1354}`. Detailed IDs, confidence/status changes, physical pair additions and removal explanations are in [preflight JSON](REV1_RELATION_TO_REV2_PREFLIGHT.json) and [preflight summary](REV1_RELATION_TO_REV2_PREFLIGHT.md). No old execution pair was removed.

### Explained reference-count differences

The task reference was 13,069 eligible relations and 26,083 physical execution pairs. Actual results are **13,068** and **26,081**. `REL:cc2c63b08c5f261c` (VIS Hydraulics `FRD*.S08 → VH030`) is unchanged between REV1 and REV2. Both canonical identities `cav_0ef76a9b57a306bfb96b` (inch) and `cav_b1df448007d65e92f964` (metric) are **external ports** in the current DB, and both authoritative MDTools active rows state `CavityType=Port`. The existing `TYPE_MISMATCH` hold is therefore retained. This explains exactly one relation and two pairs; no type, geometry or policy was changed to force the reference count.

Four low-confidence CONFIRMED rows remain evidence-only:

- `REL:5f6505db6c925ddf`: 0.5.
- `REL:9a889336111ea9ab`: 0.5.
- `REL:a39b958ee50624f9`: 0.5.
- `REL:c4965ee54b6f26c1`: 0.5.

Geometry is independent of compatibility: 1,399 execution-fact pairs reference geometrically unusable cavity definitions. Their compatibility facts remain, while existing geometry admission continues to block manufacturing placement/execution. No cavity geometry, source protection, wall rule, routing, Drawing, AI logic or project schema was modified.

## Supplemental identities and audit knowledge

- **5** logical Sun supplement cavities and **10** native-unit physical identities are registered: SC-08-02, SC-08-03, SC-10-03, SC-10-05, T-20A.
- **5** authoritative main relations (DFTA, DFTB, CSTT, DMUQ, DMUT) are reference-only, with **10** explicit supplemental links. Runtime cavity links and execution pairs from them are **0**.
- Geometry remains `NOT_COLLECTED`; placement/machining/routing/tooling/execution-geometry flags remain false. Runtime `cavities` and `cavity_interfaces` additions from supplements are **0**.
- SC-10-05/T-20A are registered even though they have **0** authoritative relations. No mapping, geometry, interface or tooling was invented.
- Pending registry: **233** raw rows; resolved **88**, open **132**, awaiting_official_catalog **11**, raw blank/missing **2**. Missing/blank is query-normalized to UNSPECIFIED without inventing a disposition; raw JSON preserves the original status presence/value.
- `CLASSIFICATION_PENDING=307` is separately preserved as raw package KPI metadata. Pending and denominator classifications have **zero execution effect** and do not delete/deactivate master rows. Other `kb_relations.csv` relation types are not imported as runtime authority.

## Official reversal audit

- AFT: **17/17** specified VP identities preserved; 34 physical IDs retain the original runtime type, unit, activity and usability. Every authoritative REV2 relation for these names is present and resolved normally.
- Walvoil: all **42** canonical logical identities (84 physical IDs) were audited and preserved, including uncovered identities. This is stronger than preserving only the requested reversal subset.
- The task names 12 `vmpd/vui/vse/vpr` logical identities, but the exact reviewed master contains **11** names under those prefixes. The report does not fabricate a twelfth name. All Walvoil identities are preserved and no legacy stripping/classification code is executed.

Specified AFT names: `vp000006`, `vp000013`, `vp000015`, `vp000038`, `vp000070`, `vp000120`, `vp000121`, `vp000127`, `vp000154`, `vp000166`, `vp000193`, `vp000198`, `vp000204`, `vp000250`, `vp000330`, `vp000388`, `vp000555`.

Walvoil prefix names: `vmpd 100`, `vmpd 12`, `vmpd 34`, `vmpd 38`, `vpr/2/rl/c/38`, `vse/p/2-150`, `vse/p/2-70`, `vui 100`, `vui 12`, `vui 34`, `vui 38`.

## Preserved domain table hashes

These sorted primary-key row counts and SHA-256 digests are identical before and after. Existing Cartridge rows were separately compared row-for-row; the three legacy cavities and their interfaces are included in the cavity table preservation check.

| Table | Rows | Before = after SHA-256 |
|---|---:|---|
| `cavities` | 6,429 | `41cd119dfd38ae6705b366da1ed6ff1d468f74ec5636cb36e930483a6ea85c3c` |
| `cavity_interfaces` | 16,347 | `f91176e0212efdb4396bcfe8a9b206b338e8f3bb530aff423627a3c1b2d495d4` |
| `closure_definitions` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `external_port_definitions` | 446 | `3d3120d15b39cc405b802b44b71a906e20cbbd0a2ee2ab5202df823207924b4e` |
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

## Verification

- Both real staging imports passed `PRAGMA integrity_check` and `PRAGMA foreign_key_check`; production source integrity/FKs were checked read-only.
- Two independent staging builds have identical complete logical row digests for Cartridge, evidence, normal links, compatibility, logical/physical supplements, supplemental links and pending registry. File SHA differs because import timestamps differ. [Determinism results](output/rev2-relation/determinism.json).
- Final targeted Python/API/material checks: **36 passed** with real staging acceptance enabled, including all core-material checks and schema v5 custom/legacy read-only preservation. The earlier targeted run had 26 passed / 1 optional skip; the real test also passed in the full suite.
- Full Python: **467 passed / 47 failed**, 1,122.45 s. One failure was a stale material rebuild assertion pinned to schema 4; it was corrected to the current schema and passed in the targeted rerun. The **46 remaining failures were each reproduced on starting HEAD `8d8e312`**, using an independent code snapshot and v4 DB clone; no new remaining failure. The full suite was not repeated after this assertion correction and the one-line addition allowing the current schema as a read-only custom preservation source. The complete affected import/material/API tests were rerun and passed. [Comparison and messages](output/rev2-relation/python-comparison.json).
- Full JS: **65 passed / 19 failed**. Starting HEAD: **62 passed / the identical 19 failed**. New relation UI checks: **3 passed**. No new JS failure. [Comparison](output/rev2-relation/js-comparison.json).
- Vite build: **PASS**. Existing font-at-runtime and bundle-size warnings remain.
- `python -m manifold prove`: **PASS**. Invalid case: PASS 295 / WARNING 2 / FAIL 6. Corrected case: PASS 268 / WARNING 1 / FAIL 0. [Final fresh-process proof](output/rev2-relation/prove-final.txt); the earlier proof also passed.
- Browser: real Chrome against staging at **127.0.0.1:8765** and **192.168.253.117:8765**. Library dashboard, existing CBDH technical values, new CBSN-060 relationship-only identity/normal compatibility, DFTA supplemental reference, unassociated supplements, pending registry and Guided entry passed. Localhost secure context **true**, LAN **false**; no page errors. Existing insecure-context token initialization remained functional.
- Screenshots were visually inspected: compatible normal inch/metric definitions are separate from technical absence; supplemental identities explicitly show geometry not collected and have no Place/Bind/Use/Generate action. [Localhost results](output/playwright/rev2-relation/localhost/acceptance.json), [LAN results](output/playwright/rev2-relation/lan/acceptance.json).
- `git diff --check`: PASS before delivery.

### Confirmed Python baseline failures

- `tests/test_ai_engineering_resolution.py::test_actual_saved_rdha_lcn_analysis_keeps_recognition_and_groups_p_a_once`
- `tests/test_ai_engineering_resolution.py::test_different_geometry_remains_one_grouped_engineering_decision`
- `tests/test_ai_engineering_resolution.py::test_equivalent_physical_rows_collapse_and_canonical_is_deterministic`
- `tests/test_ai_engineering_resolution.py::test_supported_spec_spellings_resolve_same_semantics[1/4 BSPP]`
- `tests/test_ai_engineering_resolution.py::test_supported_spec_spellings_resolve_same_semantics[1/4" BSPP]`
- `tests/test_ai_engineering_resolution.py::test_supported_spec_spellings_resolve_same_semantics[G 1 / 4]`
- `tests/test_ai_engineering_resolution.py::test_supported_spec_spellings_resolve_same_semantics[G 1/4]`
- `tests/test_ai_engineering_resolution.py::test_supported_spec_spellings_resolve_same_semantics[G1/4]`
- `tests/test_ai_engineering_resolution.py::test_unit_preference_does_not_exclude_executable_other_native_standard[inch]`
- `tests/test_ai_engineering_resolution.py::test_unit_preference_does_not_exclude_executable_other_native_standard[metric]`
- `tests/test_ai_generation.py::test_ai_generation_is_editable_and_uses_sqlite_ids_without_embedded_library`
- `tests/test_ai_generation.py::test_ai_mounting_and_provisional_ports_keep_explicit_engineering_standards`
- `tests/test_ai_routing_consistency.py::test_existing_external_port_is_open_exact_terminal_after_move`
- `tests/test_cad_execution.py::test_explicit_optimization_preempts_transient_without_saving`
- `tests/test_cad_execution.py::test_failed_check_is_never_reused_as_a_prepared_success`
- `tests/test_cad_execution.py::test_native_review_timeout_preserves_completed_engineering_only`
- `tests/test_cad_execution.py::test_save_during_authoritative_calculation_rejects_stale_commit`
- `tests/test_cad_execution.py::test_slow_preview_does_not_block_apis_save_or_exact_build`
- `tests/test_cad_execution.py::test_streamed_preview_watchdog_returns_explicit_error_event`
- `tests/test_cad_execution.py::test_superseded_preview_cancel_race_and_authoritative_priority`
- `tests/test_cad_safe_routing.py::test_build_recovers_failed_step_gate_without_mocking_route_selection`
- `tests/test_component_preferences.py::test_independent_schematic_manufacturer_is_preserved[HydraForce]`
- `tests/test_component_preferences.py::test_independent_schematic_manufacturer_is_preserved[SUN]`
- `tests/test_engineering_facts.py::test_review_only_existing_quantities_no_missing_field_fail`
- `tests/test_functional_type_inference.py::test_explicit_schematic_source_and_unknown_value_are_preserved`
- `tests/test_hydraulic_sizing.py::test_construction_access_uses_route_size_and_missing_flow_is_unresolved`
- `tests/test_hydraulic_sizing.py::test_freeze_displayed_proposal_without_resolution_and_later_flow_change`
- `tests/test_identity_admission.py::test_identity_recovery_never_hides_other_failures[topology]`
- `tests/test_interactive_preview.py::test_moving_cavity_converges_below_watchdog_and_keeps_exact_layers`
- `tests/test_production_machining.py::test_material_stock_remains_separate_from_finished_geometry`
- `tests/test_production_machining.py::test_metric_and_inch_projects_keep_mixed_standard_ids_cad_tools_and_drawing`
- `tests/test_project_engineering.py::test_v2_and_versionless_adapter_preserves_concrete_old_defaults_and_explicit_rules`
- `tests/test_route_selection.py::test_explicit_optimizer_improves_feasible_baseline_using_shared_pools`
- `tests/test_routing_feasibility.py::test_explicit_optimizer_spends_budget_on_conflict_and_preserves_evidence`
- `tests/test_routing_feasibility.py::test_save_reconsiders_both_conflicting_automatic_variants_deterministically`
- `tests/test_sqlite_domain_reset.py::test_import_admission_and_source_boundaries_are_conservative`
- `tests/test_sqlite_domain_reset.py::test_schema1_migration_drops_fake_intent_and_ai_evidence`
- `tests/test_stream_completion.py::test_done_without_finish_still_requires_valid_semantics[semantic]`
- `tests/test_v1_engineering_views.py::test_cli_file_validation_resolves_same_geometry`
- `tests/test_v1_engineering_views.py::test_explicit_optimization_budget_is_total_exact_evaluations`
- `tests/test_validate_progress.py::test_invalid_operation_id_cannot_be_used_as_trace_path`
- `tests/test_validate_progress.py::test_progress_is_owned_read_only_and_duplicate_id_does_not_rewrite_result`
- `tests/test_validate_progress.py::test_project_changed_during_build_marks_owned_progress_failed`
- `tests/test_workflow.py::test_auto_route_reproduces_demo_and_follows_terminals`
- `tests/test_workflow.py::test_freeze_keeps_exact_contacts_and_roundtrips`
- `tests/test_workflow.py::test_unknown_net_color_build`

### Confirmed JS baseline failures

- Cartridge evidence remains grouped without executable actions for evidence-only records
- Engineering Library opens a category dashboard and one failed count stays local to its card
- Explicit cavity selection enters Cavities directly; projectless browse disables placement
- External-port Use action requires the explicit selection mode
- Home Projects jumps to the existing project heading without changing Home or setup state
- Home sidebar separates New Manifold, Model, Drawing, AI and Engineering actions
- Inspector evidence direct entry returns to category instead of reopening record
- Project Settings owns engineering inputs and excludes generation and implementation parameters
- Threads preserve search and page when returning from detail
- a pending upload completed in Management remains available through Resume
- cavity replacement picker stays local and uses only usable definitions
- explicit Delete confirms workspace scope and a generation job blocks Delete
- explicit Save finishing after top-level navigation refreshes Management without hijacking it
- explicit port/cavity actions carry correct dependencies without modifying authored JSON
- hung exact request times out visibly, retains usable view, then recovers
- priority invalidates only automatic choices and keeps frozen/manual data
- streamed proposal starts promptly; only exact work receives idle delay, with immutable context
- tests\technical-knowledge-ui.test.mjs
- top-level always opens Management; dirty editor resumes without saving or discarding

## Runtime/API and delivery boundary

Technical targets must all exist, while extra relation-only identities are allowed and receive no technical rows. Cartridge searches already use the optional technical left join; technical summaries now explicitly distinguish missing records. Existing compatibility APIs remain whitelist-only. Read-only supplemental/pending endpoints and a small Cartridge knowledge detail area expose the added layer without a new Library category or backend.

**Production DB unchanged: YES.** Launchers, MDTools master, runtime geometry and projects are unchanged. The task ends at validated staging; production promotion remains separate owner approval. New runtime code requires schema v5 and does not auto-upgrade the preserved v4 production DB. Acceptance used only process-scoped `PMC_ENGINEERING_DB`; see [operator instructions](docs/REV2_RELATION_REPLACEMENT.md).

Remaining blockers to authorized staging integration: **none**. Known regression exceptions and the two explained reference-count discrepancies are listed above.
