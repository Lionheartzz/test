# V2.2 field-level validation diagnostics — 2026-09-11

- Targeted provider, validation-detail, AI foundation and generation/store/API suites: **57 passed**, four upstream warnings, exit 0 (`output/tests-v11-validation-final.xml`, 45.57 s). Tests cover exact indexed schema paths, unknown-key/input redaction, semantic rejection, exact-error opt-in retry, default-no-retry, persisted failed runs and safe exports.
- Frontend build passed (existing >500 kB bundle advisory). Real browser interaction with a clearly labeled, intercepted local fixture displayed `$.components[0].model.status`, `literal_error`, safe explanation and `schema / rejected`; details opened automatically. Screenshot `output/playwright/validation-details-fixture.png` was visually inspected. Interception was removed afterward; no stored run was changed by this UI check.
- Provider configuration SHA-256 matched the pre-change checkpoint exactly. Provider/token/timeout/streaming/reasoning/API settings and canonical engineering validation were unchanged.
- The historical HTTP 200 / stop / 6,366-token run retained only a validation count. Its discarded response cannot be reconstructed. Automatic approval review rejected a proposed real replay before execution because sending the saved inputs to the configured external provider needed explicit authorization. No replay was sent; the historical error remains unclassified, and no speculative normalization was introduced.

# V2.2 real-provider controls and diagnostics — 2026-09-11

Corrective delivery after `ac5ff6f`. Verification uses isolated/local fixtures; no additional paid provider request was issued by this work.

- Full Python regression: **127 passed**, four upstream warnings (`output/tests-v10-provider-full.xml`, 406.88 s). Final affected suite after partial/final usage distinction, render classification and three additional regressions: **52 passed**, four upstream warnings (`output/tests-v10-provider-final.xml`, 50.94 s). Covers provider contracts plus existing AI generation, source identity, project/store/API and CAD paths.
- New provider regressions cover no token ceiling (including 131,072 and an integer beyond JavaScript safe precision), blank omission, alternate token parameter, explicit reasoning dialects/task overrides, default-no-retry and opt-in retry, truncation usage capture, HTTP parameter/auth/rate/network errors, malformed envelopes, schema versus normalization versus admission stages, SSE cumulative/final usage, deadline cancellation/stream closure, partial usage, and preservation of previous successful runs. A valid semantic response with over 2 MB of reasoning text verifies removal of the old response-byte gate. Reasoning/error contents are absent from retained diagnostic evidence.
- Prompt comparison: schema **4,230 → 3,371 characters**, full system prompt **6,699 → 6,337 characters**. These are measured characters, not token estimates (`output/provider-prompt-size-comparison.json`). Existing semantic field/complexity limits were not reduced.
- Real browser: historical operator failures appear in workspace cards and open with provider/model, duration, failure help and explicit unavailable legacy metrics. Mobile dialog client/scroll widths both equal **350 px**, error region empty. Screenshot `output/playwright/provider-fix-mobile-failure.png` was visually inspected.
- Settings UI POST was intercepted for testing: `100000000000000000003` remained an exact decimal string, extraction reasoning mapped to enabled/low using the selected thinking dialect, retries stayed zero. The intercepted POST did not write actual settings. A separate, clearly labeled UI fixture verified per-attempt counters, final usage, HTTP/finish state and reasoning controls; `output/playwright/provider-fix-diagnostics-fixture.png` was visually inspected. This fixture is not evidence of paid model behavior.
- Saved configuration was not rewritten by the implementation or delivery. An operator-session update occurred after the initial hash checkpoint (current observed values: 65,535 tokens, 300 seconds, streaming enabled, provider-default reasoning); those newer settings were retained. All **9,717** library source files still match the V5 SHA ledger, **0 changed** (`output/provider-fix-preservation.json`). No CAD, routing, validation or Design schema code was changed in this correction; prior proof artifacts remain intact.
- Final frontend build: **PASS**, exit 0, JS **646.37 kB / 172.40 kB gzip**. Existing >500 kB bundle advisory remains. `git diff --check` passes. Local service runs at `http://127.0.0.1:8765/` with the final backend.

Findings, supported controls, data semantics and the next operator trial: [Provider diagnostics](docs/PROVIDER_DIAGNOSTICS.md). Historical usage cannot be reconstructed, and successful HTTP delivery cannot prove a custom model honored its reasoning controls. The current integration still uses Chat Completions; SSE/usage/control support varies by endpoint.

# V2.2 editable AI manifold generation — 2026-09-11

AI generation implementation based on foundation commit `e593cee`. The checks below were completed locally before Git delivery.

- Full Python regression: **99 passed**, four upstream warnings, exit 0 (`output/tests-v9-generation-full.xml`, 438.11 s), including existing CAD, routing, project/store/API and AI tests. The final configuration-recovery adjustment is covered by the separate 11-test final suite below. `git diff --check` passes.
- Final AI-generation suite: **11 passed**, four upstream warnings, exit 0 (`output/tests-v9-generation-final.xml`, 45.35 s). Includes configurable/redacted local credentials, corrupt-settings recovery, local PDF rendering, actual HTTP multimodal transport against an isolated test server, contract retry/auth behavior, native-cavity generation, input/library identity, stale/conflicting intent, persistent face restrictions, bottom-port routing, explicit terminal loads and restart-visible jobs. No paid provider was called.
- Required proof: `output/proof/20260911-140605/`; intentional invalid case **264 PASS / 6 FAIL**, corrected **238 PASS / 0 WARNING / 0 FAIL**, exit 0. Failed cases and exact reports are retained.
- Browser end-to-end: create synthetic analysis, upload fixture, require P/T on bottom, maximum width 150 mm and no top cross-drilling, explicitly choose existing VC08-2 geometry and map both source windows. Generation tried two candidates and selected **126 PASS / 7 WARNING / 0 FAIL**. This fixture mapping is a test decision, not cartridge compatibility approval.
- Open the generation through the normal Studio, save and validate: **127 PASS / 7 WARNING / 0 FAIL**. Move P, undo, redo, reroute and save: **153 PASS / 7 WARNING / 0 FAIL**. Reopen the saved project; P remains at bottom U=79/V=50, RV1/P/T labels are readable, and the original requirement text and analysis/run/generation/hash trace remain intact. QA project: `projects/saved/f8f3f896d61440568f292adf508f943f.json`.
- Exact-solid, edited and final desktop screenshots were visually inspected (`output/playwright/ai-generation-solid.png`, `ai-generation-edited.png`, `ai-generation-final.png`). The 390 px provider-settings screenshot was also inspected; dialog client/scroll widths both equal 350 px, endpoint/model remain blank, and the UI error area is empty. Console entries were browser password-form advisories, not application errors.
- Five frontend alignment/label tests pass. The existing real-browser viewer regression passes all four movements within one continuous pointer drag (`node scripts/check-viewer-lifecycle.mjs`).
- All **9,717** source-library files match the V5 SHA ledger, **0 changed** (`output/library-preservation-v9-generation.json`). Schema version 1, normal saved projects, immutable build snapshots and the existing CAD import boundary are preserved.
- Final frontend build passes, exit 0: JS **639.52 kB / 169.99 kB gzip**. Existing >500 kB bundle advisory remains. Local service restarted with the completed backend and is available at `http://127.0.0.1:8765/`.

Current limitations: one local AI job, configurable Chat Completions image transport, at most four cartridges and finite layout search; exact validation does not certify schematic semantics, vendor compatibility, pressure ratings or manufacturing approval. Real-model accuracy remains for the operator's first configured-provider trial. Instructions: `docs/AI_DESIGN_LAYER.md`.

# V2.2 AI foundation and d58e907 review follow-up — 2026-09-11

Local implementation and verification; no new Git push or deployment.

- Python full suite: **89 passed**, four upstream warnings, exit 0 (`output/tests-v8-ai-full.xml`, 374.47 s). Final affected tests: **15 passed**, four upstream warnings, exit 0 (`output/tests-v8-ai-final-targeted.xml`), after the provider operation field and source-port STEP assertion. Full-suite coverage includes project/store/API behavior; final targeted coverage includes AI contracts, provenance, input/hash admission, failed/conflicting runs, immutable history, review overlays and engineering regressions.
- Required proof: `output/proof/20260911-014244/`; deliberate invalid case **264 PASS / 6 FAIL**, corrected **238 PASS / 0 WARNING / 0 FAIL**, exit 0. Corrected proof engine SHA matches the current validator: `ed5c19f985be051f507db8bbbf711fa0a69aef74e8875be14de186670fd7331f`. Earlier failures remain available.
- Exact source-port regression uses `metric:lib167:cavity:3`: lateral depth 10 intersects machining volume but not the source hydraulic window. Isolated d58e907 baseline incorrectly reported **28 PASS / 0 FAIL** and a connected graph; current code reports **23 PASS / 5 FAIL** and no hydraulic edge. Depth 25 reaches the real window and reports **31 PASS / 0 FAIL**. Evidence: `output/engineering-review-v8/`. Full machining subtraction and STEP round-trip volume remain intact.
- Role tests reject external-port definitions as cartridge cavities and reject unconfirmed role reinterpretation; engineer-confirmed reuse retains source identity. Browser checks exercised Inch-first New Manifold, Replace Cavity, external-port selection and PMC library insertion controls. Readable CV1/custom net labels coexist with independent `PORT_...` IDs. Native Metric/Inch catalog role partitions remain disjoint.
- Default-route fixture proves that both the simple route and the more complicated lower-proxy-risk route pass exact validation. Normal resolution selects the one-drilling/no-plug alternative by machining cost. Exact selection evidence is retained under `output/route-selections/` for normal runs.
- Real viewer lifecycle regression passes four pointer movements in one continuous drag, preserving other generated route references through reloads; the same harness fails against the d58e907 viewer. Reproduce with `node scripts/check-viewer-lifecycle.mjs`. Final screenshot `output/playwright/v8-continuous-drag-final.png` was visually inspected. Five alignment/label tests pass with `node --test --test-isolation=none tests/route-alignment.test.mjs`; the isolated test runner initially encountered sandbox `spawn EPERM`.
- Final browser workflow: upload PDF and PNG together, retain verbatim requirements, run synthetic and unknown-safe mocks, inspect source-region highlighting, correct width 150 to 140 mm, reopen the saved review, and mark old results stale after input changes. Unknown-safe returns zero invented components/ports/nets while retaining interpreted intent and unresolved items. The local QA analysis has three immutable runs; its original reviewed run remains selectable.
- Final desktop and 390 px mobile screenshots were visually inspected: `output/playwright/ai-foundation-final.png` and `ai-foundation-mobile-final.png`. Mobile dialog client/scroll widths both equal 350 px. Source and export links use readable colors. Final source-region count is one and the UI error area is empty. This is mock workflow validation, not evidence of OCR or real model accuracy.
- All **9,717** source-library files match the earlier V5 SHA ledger, **0 changed** (`output/library-preservation-v8-ai.json`). No Knowledge Base migration or library writes were added to the AI layer. Existing user project/build storage stays separate from ignored AI analysis storage.
- Final production build: **PASS**, exit 0; JS **625.47 kB / 165.60 kB gzip**. Existing >500 kB bundle advisory remains. `git diff --check` passes. Local service was restarted with current code at `http://127.0.0.1:8765/`.

Architecture, limitations and next-stage recommendations: `docs/AI_DESIGN_LAYER.md`. Real providers, general OCR/NLU, PDF region rendering and automatic manifold generation are not implemented in this foundation.

# Hands-on usability correction verification — 2026-09-10

Local correction pass after `8c47832`. Verification below was completed before Git delivery.

- Python full suite: **73 passed**, four upstream warnings, exit 0 (`output/tests-v7-full.xml`). Later affected project/store/API checks: **21 passed**, exit 0 (`output/tests-v7-final-targeted.xml`); final catalog/port/deletion checks: **5 passed**, exit 0 (`output/tests-v7-catalog-final.xml`), including complete footprint-index versus full-record relationship coverage for both units. The additional index coverage test was added after the full suite.
- Frontend geometry-reference and legacy-name checks: **5 passed**, `node tests/route-alignment.test.mjs`, exit 0. Covers unconverted automatic routes, external ports, rotated/offset cavity interfaces, suppression/face bounds, and readable labels without changing stable IDs. `node --test` initially hit sandbox subprocess EPERM; the same node:test module ran successfully in process.
- Final required proof: `output/proof/20260910-135836/`, intentional invalid case **6 FAIL**, corrected **238 PASS / 0 WARNING / 0 FAIL**, exit 0. Earlier failure/proof evidence retained. Final proof engine SHA matches current code: `b6d5c9c6dfb51071495ab0e1fa7a3d880ce342304eb2ff824d6142001ed34c66`. Legacy demo file unchanged.
- Real browser: independently configured P/T on RIGHT with two different source port definitions, A1/A2 on FRONT/BACK, B with no external port; project JSON held exactly two selected definition pins. New/imported/reopened projects rendered immediately without camera interaction. `v7-before-empty.png` retains the reproduced pre-fix blank viewport; `v7-initial-render.png` records the corrected result.
- Real source-backed port BRep equals the same definition's cavity cut; source `Port` case handling now produces the declared interface window. Stable port IDs/net membership stay separate from engineering display labels. The workspace Add External Port flow also selected and pinned a real definition. These are source machining cuts, not automatic thread-form or installed-fitting certification.
- Solid loading/error test retained the prior model, with an explicitly simulated one-time HTTP 500; then real exact generation succeeded. All temporary request intercepts were removed. Drillings visibly overlay the machined body in Solid and hide/show independently (`v7-solid-overlays-fixed.png`, `v7-solid-drillings-hidden.png`). The deliberate 500 produced an expected console error; no zero-error claim for that session.
- Actual mesh hover/click selected generated route `R-559aead0-1` in Solid. After refinement, dragging near the end, well away from its midpoint ring, moved V **50 → 54 mm** and ran exact draft checks (**67 PASS / 8 FAIL** in the intentionally incomplete QA project); failures were not hidden. Smart Align displayed guides during pointer dragging (`v7-full-segment-drag.png`, `v7-route-smart-align.png`). Automatic-reference and transformed-interface coordinates are additionally checked by the JS tests.
- Typed-name permanent deletion: wrong name rejected; correct name deleted only the QA project's record/history, returned an empty active project library and cleared its current draft. API tests additionally prove revision conflict handling and preservation of another project, shared source and immutable build evidence.
- Catalog and definition preparation showed explicit loading states in the browser, using a labeled test delay around real requests. Process-cold benchmark on this machine: same BSP query, **3.6227 s → 2.1016 s**; identical 45 matching records and first-page identities. OS file cache was not cleared. Evidence: `output/catalog-performance-v7.json`.
- Definition visuals inspected for real port steps, cones, depth/datum, hydraulic windows and live numeric changes; explicitly labeled QA annulus/offset cuts and a real source circle with a QA engineer-selected association exercised the remaining shapes. These fixtures were not saved to the shared library. Final screenshots: `v7-cone-profile-final.png`, `v7-annulus-profile-final.png`, `v7-circle-profile-final.png`, `v7-offset-profile.png`. Source/interpretation and unmapped thread/seal metadata remain distinguishable. Mobile 390 and desktop 1440 layouts inspected.
- `output/library-preservation-v7.json`: all **9717** converted source JSON hashes match the preserved V5 baseline. No original MDTools or shared PMC library records modified. Original MDB audit remains the separately documented pending item; this pass makes no new original-database claims.
- Final frontend production build passes: **611.69 kB / 160.79 kB gzip**; existing bundle-size advisory remains. Git diff whitespace check passes. Local service restarted with the current code at `127.0.0.1:8765`.

The independent-port QA project was permanently deleted through the tested UI. Other visual/interaction fixtures are retained only under ignored `output/`; unsaved test drafts were discarded. Prior archived QA records and immutable builds are preserved.

# Product usability verification — 2026-09-09

Product usability changes; **original MDB inspection remains pending because source database files are unavailable**. See `docs/MDTOOLS_SOURCE_AUDIT.md`. Verification below was completed before Git delivery.

- Full suite: **68 passed**, four upstream warnings, exit 0, `output/tests-v6-full.xml`. Final changed-area suite: **29 passed**, exit 0, `output/tests-v6-final-targeted.xml`; includes the equal-complexity route-margin fixture, named-project isolation, compare-and-swap saves, history, failed-build preservation, exact circular envelope and source preservation. Initial test evidence `tests-v6-projects.xml` is retained: its empty-stock fixture incorrectly expected PASS despite the existing required subtractive-volume rule; the build-pointer test now uses actual machined geometry. No validation rule was weakened.
- Required proof: `output/proof/20260909-223054/`, deliberate invalid case **6 FAIL**, corrected **238 PASS / 0 WARNING / 0 FAIL**, exit 0.
- Independent QA project built through both the browser and the new named-project CLI. Final CLI build `output/builds/9acb6927776345688efcb96bbb1246b7/`: **238 PASS / 0 WARNING / 0 FAIL**, including STEP round trip. Design SHA `33b7ec3577cf40c1d3f8b5d96c4438c4d9c467dab237d0f585da5887a3d9b3da`; engine SHA `f82611300d3006deee0fbc8b732249e23d3a8bcfdf472a4a7833efc91f883b12`. Legacy `projects/demo.json` was not edited.
- Actual browser flows: empty startup library; five-step New Manifold with zero inherited definitions; real cavity selection with exactly one pinned definition; unknown compatibility; independent project import; Save Project; rename, duplicate, archive, restore and reopen with data equality. Known cartridge-first and cavity-first paths used an explicitly labeled temporary synthetic API response, removed after the test; no fictitious compatibility was saved to project or source data.
- Three-dimensional generated drilling selected by clicking its visible mesh, then adopted with Refine in 3D and dragged. Exact draft checks detected the intentionally broken fixed-port entry closure (**1 FAIL**). Undo followed by Save & Validate restored PASS. A separate geometry test confirms connected branch extension preserves its declared connection.
- Independent assembly-envelope association exercised in the browser with explicit tool role, height and written QA decision; exact source circle, role, association and raw source were checked in project JSON. The draft change was undone, not saved.
- Desktop 1440 and mobile 390 project library and route workspace screenshots inspected: `output/playwright/v6-project-library-final.png`, `v6-project-library-mobile.png`, `v6-route-selected-3d.png`, `v6-route-drag-checked.png`, `v6-cavity-placement.png`. No accessibility certification or performance benchmark is claimed.
- Final frontend build exits 0: 594.89 kB / 155.46 kB gzip; existing bundle-size advisory remains. Startup probe now uses `/api/health` and works without a demo file. Starting the launcher while the local service runs returns successfully without starting a second instance.
- `output/library-preservation-v6.json`: all **9717** source JSON hashes match V5, all original cavity records round-trip exactly, **3077 dimensional / 241 provisional**. The raw historical export audit covers 8 database inventories, 367 tables and 9969 rows; it is explicitly not an inspection of the missing original MDB files.

QA projects are retained as archived local test records; normal startup presents Projects. Completed/in-progress user projects remain separate from the legacy development demo and immutable build evidence.

# Display, LAN and Windows portability verification — 2026-09-09

Historical V5 delivery; sections below record prior builds.

- Final immutable build `output/builds/715f1ac4db3c442bac1ba126be9076f4/`: **238 PASS / 0 WARNING / 0 FAIL**, including STEP round trip; CLI exit 0. Design SHA remains `70a3fea1d910304c08bcdece92a9091a72baf03ff15fdf51a51cf8237c807fd1`; engine SHA `68d469399486911883a8f609d2394e73d18693d653adad6a07b353119f450e3b`.
- Full `.venv` test suite: **60 passed**, four upstream deprecation warnings, 263.06 seconds, exit 0. Includes store/API, original-record preservation, exact draft cutting without writes, LAN Host/Origin rejection, routing and geometry tests.
- Required proof `output/proof/20260909-151237/`: deliberate invalid design **6 FAIL**, corrected **238 PASS / 0 WARNING / 0 FAIL**, exit 0. Both cases retained.
- Production frontend build passed: 582.07 kB / 151.64 kB gzip; Vite bundle-size advisory remains.
- Actual browser interactions: saved and edited-draft Solid modes show machined openings; hydraulic zones toggle independently from visible cavity outlines; draft length edit was undone and discarded. Desktop 1280 and 1440 layouts and 390-pixel mobile layout were visually inspected. Validation heading/filter are outside the model/sidebar grid. Screenshots: `output/playwright/v5-solid-final.png`, `v5-draft-solid.png`, `v5-zones.png`, `v5-mobile.png`. A connection-refused console entry occurred while deliberately restarting the server; it is not represented as a zero-error session.
- Real socket LAN test: GET state and same-origin POST check-design returned 200 through both discovered IPv4 addresses and the machine hostname. Unit tests reject foreign hosts and mismatched origin scheme/port. These requests originated on this computer; access from a second PC and its firewall were not tested. No firewall rule was added.
- `scripts/test-runtime.ps1` passed: copied virtual environment under a path containing spaces, invalid previous-user Python paths, preserved backup, healthy rebuilt environment, and no replacement of a healthy environment. Evidence directory `output/runtime-tests/24a14f0bf1aa47b0b9638d26039a18b3/`. The uv discovery branch used a simulated uv command with a real Python 3.11 probe; this machine does not have uv. Explicit Node/npm discovery and `-CheckEnvironment` passed.
- `output/library-preservation-v5.json`: **3318 total / 3077 dimensional / 241 provisional**. All 241 source record SHA values match the preceding inventory and each original record round-trips exactly. All **9717** source JSON files were hashed before/after mapping and remain byte-identical. PMC mapping edits use separate interpretation records; original imported records and relations remain pinned. Provisional engineering status is retained.
- No changes to the authoritative demo, original library files or existing build snapshots; no Git push or publication for this revision.

# Guided engineering / routing verification — 2026-09-09

Historical V4 delivery. No GitHub push or external publication was performed for this revision.

- Final build: `output/builds/138ce8aaa47c48079ea80869a56e8110/`: **238 PASS / 0 WARNING / 0 FAIL**, including STEP round trip. Authoritative `projects/demo.json` was not changed by browser tests.
- Design revision: `70a3fea1d910304c08bcdece92a9091a72baf03ff15fdf51a51cf8237c807fd1`. Engine revision: `7e307625c85090d332977d2230c540a8f732aff1506486b610b8e0a3a7b394bc`, independently matched against current engine files. Engine identity includes the new boundary and flow modules.
- Full suite during implementation: **55 passed**, `output/tests-v4-final.xml`. Subsequent changed-area checks: **30 passed** (`tests-v4-final-targeted.xml`), **13 passed** (`tests-v4-storage-final.xml`), **6 passed** (`tests-v4-angle-final.xml`), and final library ledger checks **2 passed** (`tests-v4-ledger-final.xml`). Each command exited 0; four upstream deprecation warnings remain. The initial failing routing assertions are retained in `output/tests-v4.xml`; missing-terminal proposal screening was fixed and the offset regression now checks real connectivity instead of demanding extra drilling geometry.
- Final required proof: `output/proof/20260909-100456/`, deliberate cross-net fault **6 FAIL**, corrected **238 PASS / 0 WARNING / 0 FAIL**, exit 0. Earlier proof evidence remains intact.
- Real converted-catalog audit: drill **305**, flat-bottom drill **43**, spot-face **64**, material stock **268**, checked through API tests and actual browser filter changes after debounce completion. Index summaries no longer overwrite full tool/material records.
- Full geometry-mapping inventory: **3318 total / 3077 dimensional / 241 provisional**, with source SHA and individual reasons in `output/library-mapping-v4.json`. No provisional status was relaxed.
- Exact angled fixture: one straight angled drilling connects two installed cavity windows, meets the specified flow-area screen, preserves one valid solid and round-trips through STEP within 0.01 mm³. Breakout and invalid entry direction are rejected. Grazing overlap is smaller than the required flow area even with positive overlap volume.
- Browser checks: Metric/Inch guided draft creation, arbitrary Pilot net, real catalog kinds/families, numeric profile changes, sequential net color/diameter edits, freeze → select/edit segment → return to automatic routing, optional smart-alignment drag with visible guide, and XYZ/UV display. All browser test drafts were discarded; no test custom cavity was saved to the shared library.
- Visual artifacts inspected: `output/playwright/v4-material-library.png`, `v4-profile.png`, `v4-frozen-route.png`, `v4-smart-align.png`, `v4-final-workspace.png`.
- Frontend production build exits 0; 580.06 kB / 151.01 kB gzip bundle. Existing Vite bundle-size advisory remains.

Engineering limits: opening adequacy is a characteristic BRep section/velocity screen at overlap centroid, not a proven minimum throat or CFD/pressure certification. Angled route proposal search is bounded to two terminals; authored straight angled drills are exact. Only defensibly closed source line boundaries are mapped; height zero is a planar mounting region, not an invented valve body. Missing compatibility, body/service geometry and machining interpretation remain engineering-review concerns. Normal editing still has expert controls.

# Editable project / native library verification — 2026-09-08

Historical delivery evidence; see the newest section above for the current pointer.

- Final build: `output/builds/016f2940926b4b1783b1ac4cd357d574/`; UI Save & Validate returned **238 PASS, 0 WARNING, 0 FAIL**.
- Design SHA-256: `9df9bf0477e21cc7feff88c4102c659034061023f48004e7e525c5ad62c4ce6b`.
- Engine SHA-256: `eef830e1235ef01eadde8be93f60450d8331c42a0f1bf0d00717e58fbfe81a1b`; independently checked against current files. The hash now includes the native catalog geometry mapper.
- Independent STEP reimport: valid single solid, 2,090,859.865425 mm³, 367,423 bytes; `output/v3-final-step-check.json`.
- Full suite: **51 passed**, exit 0, 94.78 s. After the final engine-hash/body-limit updates, store/API tests **8 passed**; the extended native-mapping test also passed. Four upstream deprecation warnings remain.
- Mandatory proof: `output/proof/20260908-222840/`, exit 0. Deliberate fault: **264 PASS / 6 FAIL**; corrected: **238 PASS / 0 WARNING / 0 FAIL**. Failing evidence is retained.
- Production frontend build passed. Bundle: 565.56 kB / 146.26 kB gzip; Vite size advisory remains.
- Final Chrome console: **0 errors / 0 warnings**. Actual 1440 × 1050 screenshot checked visually, no horizontal overflow. Service confirmed listening at **127.0.0.1:8765**.

## Full native catalog audit

`output/native-catalog-audit.json`: **3318 / 3318 cavity records** successfully mapped and their serialized native records compared exactly with the source. **3077 imported-dimensional**, **241 draft-projection**, **0 mapping exceptions**. This is complete serialization/mapping coverage, not 3318 individual CAD builds or vendor certification.

Native-unit tests cover Inch-to-mm conversion, Step 0 relative depths, a zero-depth conical lead-in, full source fields and unchanged legacy `$STEP12` operands. Native footprint tests cut actual mounting holes, rotate their local offsets and verify hydraulic terminal transformations. Metric HydraForce, Inch Sun and metric ISO footprint samples were also built as valid single solids during development. Isolated sample interfaces are not claimed as connected engineering PASS designs.

Geometry and machining status are separate. The regression test proves that changing a native datum and relabeling it as imported produces a mapping warning. Imported unresolved machining remains in `manufacturing.json` and makes manufacturing readiness false. Sun locating-shoulder / special-cut mappings remain explicitly provisional.

## Actual browser interactions

- Searched real Sun Inch cavity, inspected source data, copied/saved a PMC revision, inserted it as a normal feature and exported/imported `.pmc.json`. Exported native source record matched exactly; pin and review item survived roundtrip.
- Edited the inserted project pin, renamed a hydraulic interface, was required to select its network, applied it and saw the new normal Properties field. Global revision remained unchanged. Engineering Review showed geometry and machining flags plus an edit action.
- Resolved a review with a decision and reopened it. The UI requires a decision to close an item.
- Native feature: face and coordinate changes, duplicate, suppress, restore, delete, Undo / Redo. Library test revision: delete, restore and delete again; original records and old pins remain available.
- Verified new custom cavity form starts with PMC Custom / provisional provenance.
- Six faces: actual pointer hover at cavity center and 18 px away, followed by down/move/up; all selected CV1 with `grab` then `grabbing` and changed U. Cancellation restored the starting coordinate. Existing automated boundary tests remain in the suite.
- Clicked exact optimization: six candidates, FAIL 0 → 0 and WARNING 0 → 0; evidence `output/optimizations/d46b5797adab427d931e239a50a1bb66/`. Dedicated crossing fixture test improves **6 FAIL → 0 FAIL** and confirms optimizer does not save the authoritative project.
- Restored saved seven-feature demo and built it through the UI. QA definitions/drafts were not adopted as the authoritative design.

Screenshots: [final workspace](output/playwright/v3-final.png), [pinned definition review](output/playwright/v3-pinned-review.png), [optimization](output/playwright/v3-optimization.png), [six-face drag](output/playwright/v3-six-face-drag.png). All output/builds remain immutable. No cloud, AI API or external publication was used.

---

# Workflow version 2 verification — 2026-09-08

Current authoritative design is `projects/demo.json`. The previous MVP evidence below is historical.

- Final build: `output/builds/7331690b8ccd45e9a84dfb4bb1869ddb/`.
- Design SHA-256: `582d8e287a34d31df45410d0bdf79778c142c146cb9307cf8624740a10bac366`.
- Engine SHA-256: `d5b486fa4a12bdda19964a3e1d1524f4d9de537d18827e445232692b88878e45`.
- Final exact report: **238 PASS, 0 WARNING, 0 FAIL**. STEP independently reimported: valid single solid, 2,090,859.865 mm³, 367,423 bytes.
- `.venv/Scripts/python.exe -m pytest -q`: **46 passed**, exit **0**. Includes 34 existing engineering/store/API tests plus 12 workflow cases (six parameterized face cases). Four upstream deprecation warnings remain.
- `python -m manifold prove`: exit **0**, evidence `output/proof/20260908-121501/`; deliberate cross-circuit case **6 FAIL**, corrected case **238 PASS**, no warnings/failures.
- `npm run build`: exit **0**. Bundle-size advisory remains (Three.js bundle approximately 546 kB / 140 kB gzip).
- Final refreshed Chrome console: **0 errors, 0 warnings**. Desktop 1440 × 1050, no horizontal overflow.

## Actual browser interaction

- Six faces: used actual pointer down/move/up on a cavity ring, from face center toward both outside corners. Whole service-envelope radius was 16 mm. Recorded global U/V bounds:

| Face | First corner U,V | Opposite corner U,V |
|---|---|---|
| top | 16,16 | 164,104 |
| bottom | 164,16 | 16,104 |
| front | 16,16 | 164,84 |
| back | 164,16 | 16,84 |
| left | 104,16 | 16,84 |
| right | 16,16 | 104,84 |

- Duplicated CV1 to CV3; replaced with DEMO-COMPACT; suppressed/restored; deleted; Undo restored it and Redo removed it.
- Searched the reusable library for `compact` and inserted DEMO-COMPACT through the normal UI.
- Replaced a two-window cavity with DEMO-1Z: new mapping dialog required an explicit service-interface net; selected P and verified the result, then undid the change.
- Froze automatic P drilling geometry through the net panel, then used Save & Validate in the browser: **238 PASS**. Returned the final demo to automatic routes after this test.
- Inspected final solid and internal-review images. Green rings, cavities, four circuits and the relationship-derived construction plug are visible. STEP link targets the final build.

## Real local Codex handoff

- Uploaded synthetic PNG and PDF files through the browser's file input; content-addressed assets were stored under `projects/assets/`.
- Prepared `projects/handoffs/dd7988b0eee94f6c9d4dc202b040421f/request.md` from the web UI.
- Codex read the request/manifest, visually inspected the explicit synthetic net labels, verified every uploaded file hash, and wrote a structured proposal with CV1, RV1 and CV2 interface mappings.
- Saved through `store.rebuild(proposal, expected_revision=base_revision)`. Result: build `7d5934d90f8c45fe98e6c60bcf9d6a1e`, **241 PASS**, no warnings/failures. The open browser discovered the new revision and displayed the schematic and mapped components.
- This verifies the local handoff mechanism with an explicit synthetic fixture, not recognition accuracy on arbitrary real hydraulic symbols or vendor models. The web application does not run AI; the user pastes its request into Codex.
- Test assets, handoff proposal/result, failed and successful CAD builds remain local. The final everyday demo no longer references the synthetic uploaded assets.

Evidence: `output/playwright/v2-final.png`, `v2-solid-final.png`, `v2-handoff-completed.png`, `face-*-boundary.png`, browser snapshots/logs under `.playwright-cli/`, and the immutable build/report directories above.

## Remaining scope

See `docs/DEVELOPMENT.md`. Orthogonal routes are proposals ranked by length and plug count, not a general obstacle-avoiding optimization solver. Group dragging/alignment, angle drilling, detailed vendor cavities, full machining drawings and pressure-loss/strength analyses remain later work. PASS still means only the documented geometric and declared-interface rules.

---

# MVP verification — 2026-09-07

This records checks actually run on this Windows machine. Final project: `projects/demo.json`.

- Final design SHA-256: `9c13b8ae9b6619e40248019210e62d3c890a6c0d8e5b6cb5f256b035a07d7f98`.
- Final build: `output/builds/95cb3eb7dff04c52be23f3c5f10d15f1/`.
- Engineering report: **234 PASS, 0 WARNING, 0 FAIL**, including STEP export/reimport, valid single solid and volume agreement.
- Production STEP: 367,423 bytes. Review mesh JSON: 1,742,221 bytes. Both generated from OCCT geometry.
- `python -m pytest -q --junitxml=output/tests.xml`: **34 passed**, exit code **0**. Four upstream deprecation warnings remain (SWIG/Starlette); no test failures.
- `python -m manifold prove`: exit code **0**. `output/proof/20260907-164104/invalid/` has **6 FAIL** checks including a real P/A volume intersection. `corrected/` has **234 PASS** and no failures or warnings.
- `npm run build`: passed. Vite reports a >500 kB Three.js bundle advisory; gzip output is approximately 134 kB. All assets are served locally.
- `pip check`: no broken requirements. npm installation audit: zero reported vulnerabilities after Vite update. This is not a comprehensive security certification.
- Windows `Start-Manifold.ps1 -NoBrowser`: started the web server and rebuilt a PASS model. Running it again detected the existing service without a second server or project reset.

## Browser checks

Actual Chrome interactions through Playwright, with screenshots visually reviewed:

- 3D transparent production body, stepped cavities, four coloured circuits and plug visible.
- Feature-tree selection and inspection of CV1's distinct P/A windows and actual graph connections.
- Changed XD-P X from 67.5 to 70 in the UI, saved and rebuilt. The report showed actual wall **6 mm**, required **7 mm**, FAIL; STEP download became unavailable. Restored X=67.5 through the UI and rebuilt to PASS.
- Circuit P visibility toggled and its coloured volumes disappeared. Cavity, drilling and label checkboxes exercised.
- Opacity slider exercised with keyboard input; solid/top/isometric/fit modes exercised and inspected.
- Mouse rotation, right-drag pan and wheel zoom exercised.
- Full report contained **234 data rows**; issue-only filter restored.
- Production STEP downloaded through the UI. Download SHA-256 matched its source build artifact exactly.
- Invalid JSON produced an editor error. Restoring valid JSON passed server schema normalization, applied to a draft, saved and rebuilt.
- Codex-side JSON name edit plus CLI rebuild appeared automatically in the open browser. Original demo name was restored and rebuilt to the final build above.
- Desktop 1440×1000 and mobile 390×844 screenshots checked. Final desktop had no horizontal overflow.

Evidence: `output/playwright/final.png`, `production-top.png`, `p-hidden.png`, `wall-failure.png`, `mobile.png`; automated results in `output/tests.xml`. Browser snapshots and interaction logs are also retained under `.playwright-cli/`.

## Resolved environment issue

On this machine a plain CadQuery import initially exited with Windows heap-corruption code `-1073740940`. Isolated imports identified the CasADi/NLopt loading order. With pinned CasADi 3.6.7 / NLopt 2.9.1 and the `manifold.cad` import boundary, CAD subprocesses and the complete suite now exit normally. A subprocess regression test protects this behavior; no exit codes are suppressed.

## Scope

This is a working local engineering MVP, not a manufacturing-approved valve block. Demo cavity/port dimensions, thread metadata and installed-cartridge interface assumptions are documented in README and every validation report. Vendor-exact cavities, pressure/fatigue/flow analyses, full tooling checks and manufacturing drawings remain future work. No cloud deployment or AI API was added.

## Startup recheck — 2026-09-08

The local service was offline at resumption. `Start-Manifold.ps1 -NoBrowser` was run again successfully. It rebuilt the unchanged design to `output/builds/b2530eaa20e2480a8f783297024e5e11/`: 234 PASS, 0 WARNING, 0 FAIL. The API confirmed `stale=false` and the same design SHA-256. The service is listening at http://127.0.0.1:8765. The 34-test result above remains the last full suite; this recheck did not change source code or rerun the suite.
