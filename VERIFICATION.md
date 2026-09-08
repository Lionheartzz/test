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
