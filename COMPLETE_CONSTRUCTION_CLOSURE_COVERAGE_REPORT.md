# Construction closure v8 — accepted release and system integration

Accepted release scope: ordinary construction accesses supported by the existing **103 usable generic machining definitions**. This is not universal plug coverage. Ø76/Ø89 high-flow accesses remain explicit known limitations and retain WARNING / not-manufacturing-ready behavior.

Starting HEAD: `43e3efb105899513794dc9eef0afa5d26548b2b0`.
Branch: `codex/sqlite-domain-reset`. Existing uncommitted implementation was preserved; no reset or source-audit restart.
Final commit / verified remote HEAD: exact post-push SHA and clean-worktree evidence are recorded in `output/closure-runtime/v8-release-delivery.json` and the final delivery response. The report is part of that commit; its own Git hash is recorded externally after publication.

## Accepted database activation

- Active path: `D:\Project\Manifold\data\pmc_engineering.db`; schema **8**.
- Active SHA-256: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2` — exact accepted stage4 bytes.
- Original v7 SHA-256: `93f256aea9305c9895ec82dec38c3ee2b28e1d17476d1c0468fd2ebf3aefada5`.
- Verified backup: `D:\Project\Manifold\output\closure-runtime\backups\pmc_engineering.pre-v8-activation.20261008.db` (original v7 SHA matches).
- Services/workers were stopped during the switch. Candidate verification, fresh backup and hash checks preceded atomic replacement at the original path.
- integrity_check: **ok**; foreign_key_check: **empty**.
- No startup migration, alternate runtime DB, or source MDB/PDF scan was introduced.
- All 45 unrelated tables have identical logical sorted row hashes. Existing rows in all additive tables were preserved; all 24 aliases remained unchanged.
- Intentional additive tables: closure_definitions, closure_products, closure_definition_products, thread_definitions, tool_definitions. Only tool_definitions' tool-type CHECK was extended, retaining its named indexes.

## Verified runtime figures

| Definition family | Usable definitions |
|---|---:|
| Expander | 35 |
| Short SAE | 18 |
| Standard SAE | 26 |
| Metric ISO 6149 | 24 |
| Total | 103 |

Metric layout: 48; inch layout: 55.
Products: **45**; mappings: **73**; aliases: **24**; threads: **901**; tools: **546**; Plug knowledge: **443**.
The original 14 definitions, 38 product mappings and legacy IDs are preserved. Counts were read from the activated SQLite database, not hardcoded into the UI. Generic machining is primary and a purchasing SKU is optional.

## Integration matrix

| Module | Database source/table | Change made | Test performed | Result |
|---|---|---|---|---|
| Startup / database health | DEFAULT_DB; PRAGMA user_version | Runtime validator accepts v8; closes validation connection immediately, allowing Windows activation | Startup, health 200, schema 8, hash/FK/integrity | PASS |
| Engineering Library | closure_definitions + optional product tables; existing domain tables | Dynamic generic counts/type; all existing domain APIs retained | Chromium 103 definitions · 443 knowledge; Threads/Materials/Tools/Modifiers/Closures APIs; original project references | PASS |
| Closure selector | closure_definitions, aliases, thread/tool dependencies | Explicit manual intent; closure-specific geometry edit avoids replacing a selected closure with regenerated default | Real SAE↔Expander, Save/Reload/Validate; all 24 aliases; incompatible selection | PASS |
| Automatic routing | normalized closure_definitions catalogue | Cache keyed to actual DB path/mtime/size; deterministic expander/SAE technology defaults precede newly added ISO alternatives | 8 supported automatic metric/inch flow-sized cases; T-10A; regeneration and default-family checks | PASS |
| Preview / exact geometry | SOURCE_EXPANDER_ENTRY / SOURCE_FORM_PORT_ENTRY in selected definition | Actual source contour, occupied depth/envelope and bounded hydraulic bore; current-version deferred layers | Real Chromium geometry switch; exact core and Feature layers; geometric/void regressions | PASS |
| Validation | Same bound closure/thread/tool rows as geometry | Complete generic machining accepted without SKU; incompatible selected closure remains FAIL, absent closure remains WARNING | Entry depth, occupied geometry, tooling, readiness and large unsupported cases | PASS |
| Manufacturing | Selected closure contour / machining recipe | Shared cutting primitives, FORM PORT/TAP operations, thread facts/tooling and closure recipes; incompatible definition cannot be exported as resolved | Real browser build manufacturing.json/drill-chart; all automatic matrix outputs | PASS |
| Production Drawing / supported BOM fields | Immutable build manufacturing.json + STEP | Entry diameter/depth, engagement and machining notes/tooling reflect pinned closure; blank product model stays blank | Existing anchors + actual 3-sheet production PDF with ENTRY/ENGAGEMENT text | PASS with existing template review warnings |
| Project storage / APIs | JSON schema 4; stable SQLite IDs | Manual closure selection survives serialization, Save/Reload/Validate; existing projects/duplication unaffected | Real browser/API save/reload; duplicate contract; all three original project files unchanged and loadable | PASS |
| Custom cavity/port writers | Existing SQLite cavities/interfaces/external ports | No new write backend | v8 create/archive/restore; version/FK retained in isolated write checks | PASS |
| Other library consumers | Existing cavity/cartridge/relation/material/stock/policy/modifier/knowledge tables via engineering_db | No fallback library, data promotion or unrelated schema change | Complete protected-table hash comparison; existing-domain API reads | PASS |
| Explicit deployment | Accepted normalized JSON additions; local v7 clone | Stage/activate CLI with conflict rejection, preserved rows/indexes, checks, backup and exact-hash activation | Bundle reproduces every accepted closure/thread/tool/product row; transactional conflict/activation tests | PASS |

## End-to-end results on the active database

**Ordinary automatic matrix:** metric/inch × 6/12/25/40 mm, eight real flow-sized source-port projects. Eight generated plugged accesses, all resolved. Every case: 0 WARNING / 0 FAIL, manufacturing_ready=true, valid single-solid BRep and STEP, full manufacturing output produced.

**T-10A:** 11 plugged / 11 resolved; direct baseline remains **638 PASS / 0 WARNING / 0 FAIL**. Actual normal-runtime Chromium Validate/Build is **639 / 0 / 0** because the shared authoritative path adds one explicit `step_round_trip` PASS. No existing check was removed or weakened. Manufacturing-ready; BRep valid / one solid; STEP valid / one solid; volume delta **0.0017379187047481537 mm³**. Full manufacturing output contains all eleven resolved closures. Browser Validate elapsed about 40 s; direct exact baseline check 27.20 s (single runs, not benchmarks).

**Manual switch:** Ø12 hydraulic drilling unchanged. SAE #8: entry Ø30.18 mm, engagement 10.36 mm, **83/0/0**. Expander: entry Ø14 mm, engagement 15 mm, **81/0/0**. Both source machining definitions produce updated exact preview/Feature layers, persist through Save/Reload/Validate and pass STEP/manufacturing with no SKU. SAE's two extra PASS checks are its FORM PORT/TAP tool checks. The initially discovered frontend global-reroute overwrite was fixed and the complete browser sequence then passed.

**Drawing:** actual pinned build generated a three-sheet vector PDF (307,233 bytes), with ENTRY and ENGAGEMENT callouts for the selected generic closure. No manufacturer part number was invented. Existing template `tolerance-review` and `machining-coverage` warnings remain; no drawing release/certification was claimed. The app has no separate closure purchasing BOM workflow, so no parallel BOM or fabricated product row was added.

**Browser:** normal service at http://127.0.0.1:8765, default active SQLite path. Library, selector, geometry switching, Save/Reload/Validate and T-10A were tested. Final fresh Chromium session: **0 errors / 0 warnings**, saved validated geometry reopened correctly. Earlier superseded deferred-layer requests can return their expected 409; they did not replace the current geometry. Screenshots and request/build evidence are under output/closure-runtime.

## Accepted known limitations

- Ø76 and Ø89 high-flow accesses in both metric/inch contexts are legitimate engineering scenarios whose closures remain unqualified. Four actual cases retain exactly one construction_closure WARNING each, 0 other FAIL, manufacturing readiness false, valid single-solid BRep/STEP. No fake closure, diameter cap or reduced severity was added.
- Other unqualified large closure technologies are outside this release's accepted qualified-family scope. No universal 100% claim is made.
- The 602-entry tooling-size screen is a conservative tooling catalogue domain, not a normal-manifold denominator. Actual witness coverage remains separately recorded.
- The legacy manual demo centroid-section manufacturing export remains the documented strict baseline XFAIL. Earlier incremental exact fixture failures remain baseline-identical; this task did not restart a broad regression audit.
- No product pressure qualification or workshop stocked-tool certification is inferred from generic machining completeness.

## R1 audit retained, not repeated

Official archive: `MDTools-Cavity-Library--2026-R1-Apr-16-Dot-Separator.zip`.
SHA-256: `123cff0facd981201e7619815e15eb77da8d27b371d2329c8fac29da5a24e26c`.
[Original VEST source](https://www.vestusa.com/downloadtemp/MDTools-Cavity-Library--2026-R1-Apr-16-Dot-Separator.zip).
Accepted existing inventory: **64 explicit identities / 101 physical explicit plug rows**, 209 total relevant rows, **0 undispositioned**. The exact CSV/JSON source inventory, DB/index manifest and dispositions remain in output/closure-runtime; no raw archives or PDFs are committed.

## Verification and deployment

- **61 distinct focused Python tests PASS, 1 accepted baseline XFAIL** across the release runs. Initial full focused run: 59/1 XFAIL; final impacted subset: 32/1 XFAIL; final deployment/custom-writer checks: 6 PASS. No new Python failure remains.
- **22 JS tests PASS**, plus committed-routing assertions. A historical timeout-message expectation was aligned with the existing runtime text; preview behavior was not changed to satisfy it.
- Vite build: PASS.
- Active-DB prove: PASS; deliberate invalid 295/2/6; corrected 268/1/0 retains its expected manual unresolved-closure warning.
- git diff --check: PASS.
- Normal service restarted; frontend rebuilt; active library/API and saved projects verified.

Other machines must explicitly deploy their SQLite data. Follow [CLOSURE_V8_DEPLOYMENT.md](docs/CLOSURE_V8_DEPLOYMENT.md): build a new staging clone using the versioned normalized delta, verify it, stop services/workers, then atomically activate with its exact SHA and a verified backup at the normal production path. Git alone never transfers or activates the DB.

Machine-readable acceptance: output/closure-runtime/final-closure-acceptance.json.
Activation/hashes: output/closure-runtime/v8-production-activation.json.
Post-push commit/remote/clean-tree evidence: output/closure-runtime/v8-release-delivery.json.
