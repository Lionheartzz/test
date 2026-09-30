# Dominated route selection verification

Baseline: `43642a2acb5f68d16ad80b49a9efba37c092694f`, branch `codex/sqlite-domain-reset`.

The defects were confirmed: the old selector truncated clear raw routes at 16 before connectivity pruning; prepared resolution stopped at the first 0 FAIL; failure-directed alternatives offered no optimization moves once feasible. Incremental preview also treated a regenerated template as sufficient and compared axial alternatives using their raw metrics.

The 16-candidate simplification budget now preserves axial, simple, direct and detour strategy families using deterministic Pareto layers and entry/plane diversity. Geometrically distinct alternatives are not discarded for a similar scalar cost. Source-safe candidates are simplified before recomputing all manufacturing metrics, risk and the lexicographic priority objective. Retained-net compatibility is screened after temporary connectors disappear. A local valid template is one seed inside the budget, rather than an early return.

Exact resolution and Optimize use conflict-directed repair for FAIL and bounded objective-improving search for feasible designs. Source geometry, catalogs, cut bounds and pruning evidence are shared only within the same snapshot. Complete combinations compare the global objective, then per-net objectives to avoid dominated ties. FAIL / distinct unresolved facts / priority ordering and closure-warning grouping remain unchanged. Limits remain 16 simplifications, 8 exact resolution attempts and 240 seconds; combination search retains its existing state/pair ceilings.

| Real P alternative | Raw drillings / plugs | After pruning | Total depth, mm | Compatible with selected A/T/B |
|---|---:|---:|---:|---|
| `axial_1_0:yxz:nearest` | 3 / 2 | 3 / 2 | 307.12 | No |
| `simple_46` | 6 / 5 | 5 / 4 | 444.04 | Yes |
| `yzx:nearest:offset_y_p` | 4 / 3 | 4 / 3 | 379.06 | Yes, selected |
| `yzx:positive:offset_y_p` | 4 / 3 | 4 / 3 | 450.06 | Yes |

The complete P catalog has 21 source-clear connected alternatives after pruning, including legal axial strategies; only three are compatible with the chosen siblings. None dominates the selected P. The same entire-catalog assertion passes for T/A/B.

P remains `yzx:nearest:offset_y_p`; T remains `axial_1_0:yxz:nearest`. A counterfactual replacing P by its best isolated axial strategy was checked with exact OCCT: the opposed P/T X-drill tips overlap **4.27772 mm³** at Y=100, Z=100; P/T cutting volumes also leave **0.59656 mm** and **3 mm** walls against the required 7 mm. It produces **6 FAIL**. This is an actual obstruction, not an axial-eligibility rejection or an assumed requirement for the old route.

B's dominated detour changes from `xzy:nearest:offset_x_p` to `zyx:nearest:direct`; its estimated minimum external wall improves from 25.2 to 28 mm at equal operations/depth. Overall totals remain **14 drillings / 11 plugs / 1339.18 mm**. Exact results remain **584 PASS / 11 WARNING / 0 FAIL**; all warnings are unresolved construction closures. The real fixture uses **one exact candidate attempt after bounded analytic optimization**. The feasible-baseline regression requires two exact attempts and proves that 0 FAIL no longer stops improvement; the ceiling test stops at eight despite further valid improvements.

Warm incremental P-move proposal: approximately **0.236 s before, 0.96–0.98 s after**, excluding imports, transport and final exact preview geometry. It recomputes only P and retains A/T/B with no expansion. The extra bounded comparisons add latency; no global or persistent CAD cache was introduced.

Verification: **33 focused Python tests passed**, including the deterministic candidate outside the former top-16 cutoff that becomes optimal after real pruning, all four priorities, feasible optimization, attempt limits, whole-catalog dominance, cache parity, local dependencies and store/API checks. Final `manifold prove`: corrected **268 PASS / 1 WARNING / 0 FAIL**, invalid **6 FAIL** preserved. `git diff --check` passed. No broad suite was run.

Code: `manifold/routing.py`, `manifold/preview_routing.py`, `manifold/optimization.py`. Tests: `tests/test_route_selection.py`, `tests/test_incremental_preview.py`, `tests/test_preview_geometry_reuse.py`, `tests/test_cavity_axial_access.py`. Axial eligibility, source geometry, protected-region semantics, overlap/wall requirements, SQLite, Drawing and closure behavior were not changed.

Local raw evidence: `output/dominated-routing-20260930/{before.json,after-and-obstruction.json,local-new.json}`, `pytest-delivery/` and `proof-delivery/`. Generated evidence stays outside Git.
