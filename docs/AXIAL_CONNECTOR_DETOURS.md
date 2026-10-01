# Axial connector detours — 2026-10-01

Baseline: `8e90f63e06e35414de379da059e8123a464ba51e`, branch `codex/sqlite-domain-reset`.

Previously, axial terminal overrides supplied only a direct orthogonal connector. New variants keep the certified opposite-face bore unchanged and offset only its final transverse approach, shortening adjacent collinear legs where appropriate. A bounded second bend and alternate full-cylinder junction are supported. Planes come from finite blocking machining/access regions, including drill-tip extent; internal stage boundaries inside another relevant cut are rejected.

New keys append explicit coordinates, for example `axial_1_0:yxz:nearest:c0_y_117.503442`, `:j0_82.496558`, or a two-plane suffix joined by `+`. They regenerate independently of the obstacle context and pass Design/PreviewContext validation. All **72** original P/T axial variants were compared against the baseline JSON and remain identical.

The shared generator uses actual retained routes locally; global generation also compares real hypothetical peer axial proposals. It creates at most **12** connector/junction alternatives per net, without a plane Cartesian product or extra analytic-generation BRep builds. Axial-direct and axial-detour have separate bounded strategy opportunities inside the existing **16** simplification budget. Fixed-bore obstructions are retained as failures and skip futile connector pruning. Scoring, eligibility, source protection, wall/overlap rules, closure behavior and exact time limits are unchanged.

The deterministic synthetic fixture proves a fixed cross-net connector obstructs axial-direct while the axial bore itself is clear. New local connector variants pass exact **0 FAIL**, preserve the bore and frozen obstacle, and keep every required hydraulic interface connected. Fewer plugs and Simple machining select by actual metrics, including ordinary routes; no axial bonus was added. A second local test discovers a clear detour around a retained automatic route while recomputing P only.

Real T-10A evidence:

- The two bottom axial bores, `R-5c62e091-AX0` and `R-e632b709-AX0`, have **46 mm** exact separation and zero overlap.
- The old direct X connectors `R-5c62e091-1` / `R-e632b709-1` overlap **4.27772 mm³**.
- A separate immutable obstruction exists: P's axial bore / T's X connector have **0.59656 mm** wall; P's axial bore / T's front connector `R-e632b709-2` have **3 mm** wall, against the required 7 mm. Changing P's connector cannot repair these pairs.

| P route | Drillings / plugs | Setup faces | Maximum depth | Total depth |
|---|---:|---:|---:|---:|
| Selected before and after: `yzx:nearest:offset_y_p` | 4 / 3 | 4 | 127.80 mm | 379.06 mm |
| Best source-clear connector detour: `axial_1_0:yxz:nearest:c0_y_117.503442` | 4 / 3 | 4 | 146.122133 mm | 428.625575 mm |

That detour eliminates the transverse volume intersection: **zero P/T overlap**, but its minimum P/T wall remains **0.59656 mm**. Exact validation gives **4 FAIL**: `P-3/T-1`, `P-AX0/T-1` at 0.59656 mm, and `P-3/T-2`, `P-AX0/T-2` at 3 mm. A two-bend candidate clears the connector failures but retains the two immutable axial-bore failures. It therefore cannot replace the selected P with retained T. The selected complete design has **17.59656 mm** minimum P/T wall and zero P/T intersection both before and after.

Final total: **14 drillings / 11 plugs / 1339.18 mm**, **584 PASS / 11 WARNING / 0 FAIL**; warnings remain unresolved closures. Warm local P proposal measured **1.18–1.25 s** (this run's baseline 1.356 s; previous task approximately 0.98 s), excluding imports/transport/final exact geometry. A/T/B are retained with no expansion.

Verification: **38 focused Python tests passed**; final proof corrected **268 PASS / 1 WARNING / 0 FAIL**, invalid **6 FAIL** preserved; `git diff --check` passed. Covered connector obstruction, real pairs, saved/reloaded variants, API acceptance, bounded generation, all priorities, domination, source protection and incremental locality. No broad audit was run.

Files: `manifold/cavity_access.py`, `manifold/routing.py`, `manifold/schema.py`, `manifold/preview_routing.py`, `tests/test_axial_connector_detours.py`, this report. SQLite, authored geometry and Drawing were not changed. Local raw evidence lives under ignored `output/axial-connector-20261001/` (`before.json`, `after.json`, `real-new-candidates.json`, `pytest-delivery/`, `proof-delivery/`).
