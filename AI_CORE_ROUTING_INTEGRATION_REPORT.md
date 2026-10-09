# AI Draft and shared manifold routing integration

Starting HEAD: `cdb9e51ee96bf0e561a8c0739517882e77aae633`.
Branch: `codex/sqlite-domain-reset`. Delivery commit and verified remote SHA are reported in the delivery message.

This delivery was inspected statically. **No tests, browser automation, Vite build, CAD execution, new generation benchmark or AI provider call was run. New runtime outcomes and timings remain unverified.**

## Existing completed case

Source: `output/ai-design/ffeab6c333e5455ba6175fc62bc136ea/generations/d5dc3c37253d45fd86b1b2f48255e7b2/`.

| Layout | PASS | WARNING | FAIL | Worker seconds | Route proposal seconds | Validation seconds | Distance calls / seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2596 | 29 | 91 | 921.375 | 228.516 | 275.672 | 2418 / 236.817 |
| 2 | 3667 | 27 | 161 | 739.515 | 229.609 | 266.969 | 2228 / 231.156 |
| 3 | 3105 | 30 | 102 | 784.500 | 238.469 | 305.140 | 2706 / 262.558 |
| 4 | 3331 | 28 | 122 | 687.719 | 233.453 | 233.141 | 1782 / 199.596 |

These are existing measurements, not post-change results. The workers total 3133.109 s; the generation packet records 3137.36 s. All four route reports record one exact candidate. Layout 1 has 28 `circuit_intersection` FAILs, 28 related `declared_connection` FAILs, 22 unintended cut intersections, eight protected-cavity failures, two disconnected circuits, two plug engagement failures and one installation-access failure. All its FAIL rows are marked routing-repairable. Its nine nets have no per-net flow override, so the former flow-net combination exclusion was not the cause of this particular case.

Trace files: `5aeff0c427724ff6bd25f18932fd2a5b.json`, `49da9ff8187440d3a0e4dd21aa2683b6.json`, `305b0f2d6da54b7dbe1945b218a5d46c.json`, `49c1f204f57d4fa983c7cb438abe39a8.json`, under `output/cad-diagnostics/`. The earlier `964e4243c7de45788136e95d65f29780.json` remains unchanged.

## Responsibilities

Normal AI Generate now compiles **one** standard project from the existing resolved analysis: block/defaults, stable source identities, placed components, ports, net membership, schematic metadata and unresolved engineering reviews. It writes an editable, explicitly `NOT_ROUTED_NOT_VALIDATED` draft. It makes no CAD worker request and runs no multi-layout or exact-candidate optimization. Historical generation packets/options remain readable.

Opening this project starts the existing Model preview queue and shared `resolve_preview` / Router. The draft is available while that operation runs. Save Draft, explicit Reroute/Optimize and existing Validate/Build retain their roles. Hidden layout/exact search controls were removed from AI generation; there is no new competing Optimize Layout engine or setting. The obsolete `ai-generate` CAD-worker operation was removed.

## Confirmed overlap and root causes

Layout 1 contains `R-2b517485-2` on `net_CB_out_left`, right face U=184.90, V=95.88, Ø8, depth 220.80, and `R-2e486d24-1` on `net_CB_out_right`, same face/U/V/diameter, depth 180.05. The saved exact validation confirms different-circuit shared fluid volume. These are not legitimate same-net connections.

`route_obstructions` already has rules that detect this finite-cut overlap. The defects were in surrounding selection/acceptance:

- If complete combination search returns no clear solution, greedy selection can choose the least failing option. The old final sweep compared only one net's obstruction count, then marked every generated route as `proposal` with an empty issue even if global conflicts remained.
- `alternative_proposals` offered mostly one/two-net changes and discarded every complete proposal with *any* proxy conflict. A partial but genuine reduction could not spend the next exact-candidate opportunity.
- Source catalogs, retained-route contexts and already prepared pools were repeatedly screened/copied/ranked. The baseline proposal was materialized again before exact evaluation.

The saved traces do not record whether the original complete-combination attempt first stopped on an empty source-safe pool, the state ceiling or the pair ceiling. This report does not invent that missing diagnostic.

## Shared global conflict planning and progressive repair

Source-safe axial, simple, direct and detour strategies still pass the existing family/Pareto shortlist and exact connectivity pruning. Prepared pools now reuse the normal source-tool/flow sizing loop, including flow nets previously excluded from complete combination search.

Complete layouts are screened against source machining and retained/manual/frozen cuts. Mutable net pairs are checked in both directions using cached finite-cut, plug and access screening. Source checks remain separate and mandatory. No cross-circuit contact is authorized by `connects_to`; generated-contact authorization still requires actual same-circuit exact fluid overlap.

Progressive repair uses a beam of at most four complete states, at most **256 analytic states and 4000 new candidate-pair screens per repair invocation**. Each retained step strictly improves the lexicographic global conflict objective: source/protected/wall feasibility, hydraulic isolation, then remaining access/plug/connectivity screening conflicts. Round-robin moves give implicated nets opportunities; paired moves can escape a one-net local minimum. Successive states retain prior improvements, permitting coordinated changes across more than two nets. Geometry signatures prevent revisiting a configuration. Unknown compatibility after exhausting the budget is never admitted as clear.

The existing complete-combination limits (1000 states / 4000 pair opportunities), source-strategy coverage and configured exact CAD attempt limits remain. Progressive repair does not add exact CAD attempts. Authoritative selection can now consider a strictly improving intermediate layout even when unrelated proxy conflicts remain; existing `exact_route_score` still selects by exact engineering FAILs, distinct unresolved facts, then the selected Design Priority.

Every new final proposal receives a complete obstruction screen. Conflicting cuts are retained for inspection but marked `stale` with explicit unresolved routing issues, rather than being labelled a clean proposal. Here `stale` is the existing schema state for retained geometry needing review; using it avoids implicit rerouting when such a draft is saved, reopened or validated. It is not manufacturing approval.

## Shared initial placement

`manifold/layout.py` serves AI draft compilation and explicitly requested new Guided projects through the existing `check-design?initial_layout=true` endpoint. It uses:

- shared-net adjacency and connection degree;
- source machining/installed footprint extents, including primitive offsets;
- actual source hydraulic-window coordinates and depths in a deterministic wire-length objective;
- bounded swaps within the chosen mounting face;
- external-port targets derived from all relevant cavity terminals, with footprint/access separation;
- existing block dimensions, required faces and pressure/wall calculation.

It neither infers physical positions from schematic coordinates nor changes hydraulic identities. Unsupported fit remains an explicit blocking engineering review with editable locations retained. Existing authored parent/route geometry is rejected by the initial-placement entry point. It is never called by load, reload, Save, Validate, Build or Drawing.

## Calculation reuse and exact validation

`ExactPairs` provides operation-local conservative AABB distance lower bounds, disjoint-volume proofs and symmetric exact pair caches. If the lower bound cannot establish the required separation, the same OCCT distance operation remains required. Near/intersecting fluid, protected-region, plug and machining contacts retain exact volume calculations. Empty protected compounds retain zero-volume semantics. Geometry wrappers are retained with cache keys to prevent Python object-ID reuse errors.

Validation still emits each underlying check. A bounds-proven clearance is labelled `>= … (conservative bounds)`, not an exact measurement. Future reports include `calculation_reuse` counters so real savings can be measured without a second timing system.

Source hydraulic nodes used for redundant-drilling pruning now come from existing `feature_geometry`; they do not require a duplicate stock Boolean. The authoritative production solid is still built and validated normally. Snapshot caches reuse source pools, individual bore risks, obstruction results and pair compatibility; caches retain geometry/conditions in their keys and have bounded retention. Exact baseline evaluation reuses the already prepared proposal.

No measured post-change speedup is claimed. New proposal time, Validate time, exact attempt count, final routing FAIL count, BRep/STEP and incremental-preview timings require a permitted real run.

## UI and engineering boundaries

Validation Results adds a compact repair summary grouped by actual object pairs/circuits and problem family, with human-readable names and the existing locate/reference actions. Every original validation row remains below it; stale-build references retain their existing qualifications. Preview retains current route state/issues when exact geometry arrives. Progress distinguishes layout, routing, conflict repair, geometry and engineering-rule checking; milestone percentages are not ETA measurements.

No wall-clock deadline was restored. No minimum wall, overlap/opening requirement, protected source region, tool reach, closure behavior, production topology or STEP gate was relaxed. There is no tip-only terminal fallback and no axial bonus. Stage 1 analysis, normalized topology, provider contracts/settings, SQLite and compatibility data were not changed. There is insufficient new source evidence to justify merging or renaming MA/MB/intermediate nets, so those assignments were preserved.

Committed-route ownership remains intact: only pending automatic routes or an explicit optimization action enter candidate search. Manual/frozen cuts and approved project placements remain fixed. Old failed generation artifacts and saved routes were not rewritten; use a new Draft or explicit Reroute/Optimize to request a new proposal.

## Static checks and files

Python AST parsing, JavaScript syntax-only parsing and `git diff --check` were used. These checks execute no project/CAD functions and are **not runtime tests**. No test files were added. Tests, browser automation, build, prove, benchmarks and paid provider calls were intentionally not run. The frontend was not rebuilt and the running service was not restarted; restart/build through the existing launcher before runtime acceptance.

Files: `manifold/ai_design/generation.py`, `generation_models.py`, `manifold/cad_worker.py`, `layout.py`, `routing.py`, `server.py`, `spatial.py`, `validation.py`, `validation_progress.py`, `web/ai-generation.js`, `guided.js`, `main.js`, `validation-view.js`, and this report.

Protected file hashes remain:

- Active DB SHA-256: `1E3267BD6A6271CF819B5181ED52EAE55AB8B8B54A4A48CE45CC277175D7DAA2`.
- Provider configuration SHA-256: `2585ED2E0E32FF5677CF0D3136FDD948F7A9C9CF951EB6683DF969CF742E190A`.

**Acceptance status:** implementation and static inspection complete; a conflict-free result for the eight-valve project, all four priorities, committed-route runtime behavior, browser presentation and actual performance gains remain **unverified**, as required by the no-execution instruction.
