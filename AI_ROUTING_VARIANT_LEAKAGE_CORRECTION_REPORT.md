# AI route handoff and eight-valve correction

Starting HEAD: `09062034db75a15383825238d563ba0d818f0e2e` on `codex/sqlite-domain-reset`, initially clean. Delivery commit and verified remote SHA are recorded in the delivery message and local `output/runtime-checks/variant-leakage-20261012/delivery.json`.

**The eight-valve design remains unresolved and is not approved.** This change fixes the AI pinning defect and improves the measured result from 13 to 7 unintended cross-Net intersections. It does not establish manufacturing readiness or prove that no feasible layout exists.

## Cause and authority correction

`layout_search.plan_new()` wrote `screen().selected` into `routing_variant`, including selections from an incompatible analytic fallback. All eight Nets in the real 310 × 245 × 230 mm proposal contained these samples. `_complete_route_combination()` correctly protects specified variants, so global combination search was skipped and progressive repair could not reconsider them.

New AI generations retain these selections in assessment diagnostics only. Their Draft Nets are unpinned; the common Router can search globally. Explicit user variants and committed, manual and frozen machining keep their existing protections. No blanket stripping occurs during Model import, Save or Reload.

Historical recovery is an explicit action returning a copy. It requires the owned immutable generation packet, exact full-design revision equality, uncommitted analytic provenance and matching recorded variants. Edited designs, different user pins, committed/frozen/manual Nets and origin-only claims are refused. The original generation and saved Project are never rewritten. The UI ignores a recovery response after another screen has opened.

## Additional candidate and layout defects

- Common-junction strategies existed in the AI sampler but were absent from ordinary shared Router pools. The shared Router now exposes a bounded family derived from actual source stations, functional entries, available entry corridors and source-safe deep access. It changes drilling proposals within supplied geometry only.
- Independently source-clear parallel entries could clash at their own plug envelopes. Entry selection now checks previously generated same-Net cuts before choosing a real opposite-face access. Complete connectivity and source/global obstruction gates remain mandatory.
- Face-open source windows were approached at their midpoint even where a mounting cut obstructed lateral entry. A separate window-branch candidate can turn farther inside an actual continuous source cylinder, behind mounting cuts. It retains the window's offsets, rotation and pose. It rejects interrupted/annular cores and non-face-open staged windows. It grants no protection exception and changes no cavity axial eligibility.
- Legacy port/source wrappers cannot parse coordinate-bound branch strategies; those strategies now retain their own regeneration grammar.
- AI layout search no longer uses insertion-order `queue[:2]`. At most 12 cheap hypotheses, with at most two representatives per transformation family, are ranked before retaining a two-parent frontier with family diversity. Full analytic layouts remain capped at eight, route samples at 32 per Net and retained analytic options at eight. Source rotation, branch planes, separate corridors, entry faces and measured group spacing/growth are reviewable AI-generation candidates.

The 1,000 combination-state / 4,000 pair-screen limits, 256-state progressive repair limit, 16 exact per-Net shortlist and eight authoritative Exact-candidate ceiling were not increased. No wall-clock deadline was added. Runtime uses normalized library geometry; SQLite was unchanged.

## Fixed-layout evidence

All comparisons use the same source coordinates, source definitions, topology, minimum wall and 310 × 245 × 230 mm Block. None of the original saved evidence was overwritten.

| Case | Cross-Net contacts | PASS / WARNING / FAIL | Drillings / plugs | Total depth | Runtime / Exact candidates |
|---|---:|---|---:|---:|---|
| Original analytic pins | 13 | 4202 / 38 / 39 | 49 / 45 | 8109.503 mm | 15.422 s / 1 |
| Starting-code unpin-only comparison | 14 | 3357 / 26 / 52 | 42 / 38 | 5876.772 mm | 224.062 s / 1 |
| Corrected shared Router | 7 | 4341 / 37 / 22 | 50 / 46 | 7980.568 mm | 353.984 s / 3 |

Unpinning alone produced **no net reduction**: 13 became 14. The original 13 exact cut profiles were replaced, but new intersections appeared; this is not evidence that pin removal solved those engineering conflicts. Global diagnostics initially had empty A_DC/B_DC/SHUTTLE_OUTPUT pools. With the new shared families, all eight pools contain independently admitted candidates.

The corrected global combination search used 8 states and 59 pair screens and found the retained pools incompatible. Progressive repair used 256/236/236/119 states and 355/139/0/10 newly screened pairs across its recorded calls. Three full Exact candidates were evaluated; the final neighbourhood exhausted without a clear combination. These results establish a retained-candidate limitation, not physical impossibility of every layout.

All eight final Net routes have verified source-to-route connectivity; `connected_interface` and `circuit_connectivity` have no FAIL. There is an additional inadequate incidental same-Net direct contact, listed below, which remains a real FAIL.

Production BRep: valid, **one solid**. STEP reimport: valid, **one solid**, volume delta **0.0000618621706963 mm³** (< 0.01 mm³). Manufacturing-ready: **false**. Pressure/flow, complete threaded-port machining, product qualification and other review facts remain independent unresolved requirements.

### Remaining exact physical blockers

All generated bores below are Ø8 mm. Coordinates, faces, depths and selected variants are recorded in `final-comparison.json` and the retained selected proposal.

| Nets | Exact feature pair | Fluid overlap mm³ |
|---|---|---:|
| A_DC / B_DC | `R-702e7749-7` / `R-309be2fb-7` | 341.33333 |
| B_DC / T | `R-309be2fb-4` / `R-e632b709-3` | 199.76258 |
| B_DC / T_DC | `R-309be2fb-4` / `R-8e428e23-3` | 31.68796 |
| B_DC / MA | `R-309be2fb-5` / `R-f0055891-2` | 198.52253 |
| MA / MB | `R-f0055891-AX0` / `R-1d09f6fa-1` | 341.33333 |
| MA / MB | `R-f0055891-AX2` / `R-1d09f6fa-1` | 341.33333 |
| T / T_DC | `R-e632b709-3` / `R-8e428e23-1` | 200.98830 |

These seven contacts account for 21 FAIL rows (`circuit_intersection`, `declared_connection`, `unintended_cut_intersection`). The 22nd FAIL is `expected_connection`: B_DC `R-309be2fb-7` / `R-309be2fb-9` has only 0.03132 mm³ overlap against the unchanged 0.1 mm³ requirement. Full Net connectivity through other edges does not make this direct contact adequate. No near-tangent contact or validation rule was suppressed.

### New AI layout assessment

The updated AI-only planner ran eight analytic layouts in 196.281 s, without any AI provider call. It retained an **unvalidated, incompatible** proposal at 310 × 245 × 230 mm with C6 rotation 0° instead of the original 270°; other source positions were unchanged. Its selected feasibility vector is `[0, 0, 8, 0, 1, 9]`. All generated routing variants are null. This separate proposal was not applied to Model and was not treated as Exact-approved. Another expensive Exact run was not justified by this still-conflicting analytic assessment.

## Ownership and preservation

Only new AI-owned generation calls the adaptive layout planner. Common Router changes produce cuts inside fixed supplied geometry. Model Preview, Auto Route, Optimize, Validate, Build, Save and Reload gain no resizing or repositioning behavior. Existing layout alternatives remain explicit review/Apply operations.

SHA-256 before/after matched for the saved original Project, active schema-v8 DB, earlier independent routing candidate and original normalized AI task:

| Protected file | SHA-256 |
|---|---|
| `projects/saved/2b93c6c68df24d5ebe543215e8e91c99.json` | `450ff90ca5ae82b958fae5e45558cf57c37be7ce5c9468aa13072934fed43f2a` |
| `data/pmc_engineering.db` | `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2` |
| Earlier independent `interior-selected-proposal.json` | `4258f0abfd8d8a17df84232d7b4fb1a24d38d333714f034d93f46b0475a1a292` |
| Original AI task `current.json` | `89f9a31c14687a91daa5914302bc2fb7ba674fc7a30e073a5adcc98e48ae4094` |

## Focused verification

- Handoff, recovery API, candidate connectivity, pose/offset/source-core rejection, opposite-face plug entries, frontier ranking, topology review and coordinated-layout tests: **24 passed**.
- Real four-Net T-10A Exact routing/rebuild regression: **1 passed**.
- Incremental manual/frozen retention: **1 passed**. Incremental cavity move: **1 passed**, retaining unaffected Nets.
- Incremental P-move test: **1 existing failure**, reproduced with starting-HEAD `routing.py` and `cavity_access.py` loaded into an isolated process, without resetting files. Both versions give 740 PASS / 0 WARNING / 4 FAIL: feature wall, plug engagement, invalid BRep and two solids from the legacy pinned fixture. Both initially recompute only P and retain A/T/B. This was not silently marked PASS or expanded into another repair task.
- JS recovery/stale-response and topology-review checks: **4 passed**. No browser interaction or visual acceptance was run, as requested.
- `python -m manifold prove`: PASS; invalid fixture 295/2/6, corrected fixture 268/1/0. Evidence: `output/proof/20261012-012558`.
- `git diff --check`: passed. No broad suite, Vite, browser automation, paid AI or recognition rerun.

Changed files: `manifold/ai_design/{api,generation,layout_search}.py`, `manifold/{branch_candidates,cavity_access,routing,schema}.py`, `web/ai-generation.js`, `tests/test_ai_routing_handoff.py`, `tests/ai-route-recovery.test.mjs`, and this report.

Local evidence root: `output/runtime-checks/variant-leakage-20261012/`. `final-comparison.json` contains full selected routes, manufacturing metrics, exact blockers, protected hashes and search diagnostics. `final-fixed/` contains the final proposal, validation, STEP and trace; `final-layout/` contains the separate unpinned AI layout proposal. The intermediate two-solid candidate in `shared-search/` is preserved as rejected evidence. Large CAD/trace outputs are not committed.
