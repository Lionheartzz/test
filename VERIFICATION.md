# Display, LAN and Windows portability verification — 2026-09-09

Current local delivery; sections below record prior builds.

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
