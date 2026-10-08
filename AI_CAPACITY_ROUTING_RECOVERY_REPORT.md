# AI capacity and routing preview recovery

Starting HEAD: `a7252cc36a18b55b8ca050be4f9b48dec0c95eec`.
Branch: `codex/sqlite-domain-reset`. Starting working tree was clean; no reset.

## Confirmed causes and changes

- Removed the four-cartridge gate. Recognition/bindings accept 120 components,
  600 terminals and 300 analysis nets; generation explicitly enforces the existing
  **120 total project features (including drillings) / 40 project nets**.
  Source window mapping supports 64 interfaces and net membership supports 100
  terminals. Oversized analysis is retained with a project-capacity diagnostic.
- New AI designs incorrectly called committed-route-only Validate and returned
  unresolved authored features instead of the evaluated route geometry. The
  dedicated `ai-generate` worker operation now performs bounded exact routing;
  the handoff merges its actual proposal into the authored design. Ordinary
  Validate/Build still check committed geometry without implicit rerouting.
- Layout uses source machining/installed footprints, minimum walls, real face
  axes, a balanced grid and an alternate rectangle. Port entries are screened
  against occupied footprints. Proposed padding can be clipped to a requested
  feasible envelope; actual source dimensions remain hard limits.
- Generation defaults to four layout attempts, two exact candidates per layout,
  and a 480-second total budget. Explicit limits are 6 / 8 / 480 respectively;
  an individual native calculation retains its existing 300-second ceiling.
  Preparation/placement consumes the total budget too. Cancellation terminates
  the owned native worker. Timeout/cancellation retains the authored checkpoint,
  original analysis, diagnostics and a Studio-openable unvalidated draft.
  Results from superseded analysis are retained without overwriting newer inputs.
- Preview ownership was incorrectly tied to the visible exact model. Current
  routing is now checked independently of display success; retained viewer
  geometry never authorizes a Save. Retry uses the current authored draft and
  checks the saved revision before clearing a transient disconnect flag. A real
  version conflict remains blocked. Project switches reset transient flags;
  old request versions/project epochs remain rejected.
- Explicit **Save Draft** removes obsolete generated cuts only from unresolved
  automatic nets, retains authored/manual/frozen work, keeps unresolved states,
  and clears current build approval. Previous builds and revision history remain
  intact. Normal Save/Validate require current routes. Inspector callbacks are
  rebound after Save so subsequent edits target the current draft object.

## STEP measurement found during larger-case acceptance

Eight-cavity geometry was valid before and after STEP import, but default OCCT
fixed quadrature produced a false volume difference of **0.02672047 mm³**.
The *same solids and STEP bytes* measured with adaptive integration differed by
approximately **4.7e-10 mm³**. The shared STEP gate now uses two increasingly
accurate integrations and requires each volume to converge within 0.001 mm³.
Its existing **0.01 mm³ absolute difference**, valid-solid and single-solid
requirements are unchanged. A real 0.02 mm³ volume loss still fails.
No source machining, exported geometry, protected-region/wall/overlap rule,
Design Priority, manual/frozen geometry or closure policy was relaxed.

## Real v8 generation matrix

These are local semantic test circuits with explicit bindings to real SQLite
`cav_003e5a8ca3cca13cf39d` machining and all hydraulic windows. Each has two P/T
nets. No fake Cartridge↔Cavity mappings were inserted and no paid AI call was
made. Custom straight-bore test ports were explicitly declared; these tests do
not assert supplier/model compatibility or pressure certification.

| Cavities | PASS | WARNING | FAIL | Observed seconds | Total features |
|---:|---:|---:|---:|---:|---:|
| 4 | 313 | 0 | 0 | ~18 | 12 |
| 5 | 371 | 2 | 0 | ~32 | 13 |
| 8 | 607 | 6 | 0 | ~56 | 18 |
| 12 | 897 | 8 | 0 | ~86 | 22 |
| 16 | 1329 | 10 | 0 | ~156 | 28 |

All: valid single BRep, valid single STEP, converged volume difference <0.01 mm³,
normal Save/Reload with committed routes and all components/net mappings retained.
Warnings are actual `drill_reach` checks and remain visible. These are finite
tested cases, not a claim of unlimited capacity or manufacturing certification.

## Chromium acceptance on localhost

Actual active v8 database; QA copies only, original saved projects retained.

1. T-10A saved-project port move + injected routing timeout → retained-view
   warning, Retry and Save Draft available. Saved unresolved P had **zero stale
   P drillings**; committed T/A/B were retained. Restoring the authored pose and
   explicitly retrying produced an owned proposal; normal Save and Validate ran.
2. A real wall failure was preserved (6.6 mm <7 mm). Existing explicit Optimize
   tried two exact candidates and reduced FAIL 1→0. Final normal Save/Validate:
   **639 PASS /0 WARNING /0 FAIL**, 11 plugged accesses resolved, manufacturing
   ready, valid single BRep/STEP; final STEP delta **0.0000746008 mm³**.
3. Five-cavity AI draft used the same Studio. A real routing proposal followed
   by injected exact-display failure could still be normally saved. Retry and
   authoritative Validate completed: **483 PASS /3 WARNING /0 FAIL** after the
   block-height edit. The three real drill-reach warnings were retained.
4. Injected status disconnect recovered via explicit Retry when the saved
   revision matched. An actual external rename with local unsaved edits remained
   blocked; both the local draft and newer saved version survived.
5. Legacy loading/normalized revisions, stale save rejection and project/build
   isolation were exercised through existing store/API tests. Async supersession,
   cancellation and cross-project ownership were exercised through JS tests.

Local screenshots and machine results:
`output/ai-recovery/routing-failure.png`, `five-cavity-exact-failure.png`,
`five-cavity-recovered.png`, `t10a-recovered-final.png`, `capacity-*.json`,
`capacity-summary.json`, `volume-precision.json`.

## Verification and boundaries

- Strict focused capacity/generation checks: **16 passed**; subsequent focused
  padding/recovery/preflight checks: **12 passed**.
- Draft preservation, cancellation, analysis-update handling, project store/API:
  **25 passed**. Owned native-worker cancellation: **1 passed**.
- STEP precision and focused CAD-safety checks: **8 passed**.
- Relevant generation/preview/recovery JavaScript: **20 passed**.
- Vite build passed. `python -m manifold prove`: deliberate invalid 6 FAIL;
  corrected **268 PASS /1 WARNING /0 FAIL** (`output/proof/20261008-153103`).
- `git diff --check` passed. No broad regression suite/audit was run.
- Extra legacy checks still expose previously existing assumptions: incremental
  P/CV1 moves have 6/1 exact FAIL respectively while locality assertions pass;
  an old Build test expects implicit rerouting of unresolved geometry; old AI
  Management fake DOM lacks `addEventListener`; an old full-port ambiguity test
  expects blocking despite the existing thread-only draft path. The latter was
  reproduced with starting-HEAD `prepare()` on the same DB, without resetting the
  tree. These are not reported as PASS and were not used to weaken any rules.

Active SQLite remains **schema v8**, byte-identical before/after:
`1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.
No SQLite tables, MDTools source, importer, library data, Drawing, material
research or compatibility policy were changed. Only code, tests, this report
and the small source-geometry regression fixture are committed; generated CAD,
DBs and local QA outputs remain untracked/ignored.
