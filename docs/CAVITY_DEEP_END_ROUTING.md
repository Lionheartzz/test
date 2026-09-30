# Safe cavity deep-end routing — 2026-09-30

Baseline: `d23272071c47ed88abee849a6799b78ec2a2699f`, branch `codex/sqlite-domain-reset`.

Previously, cavity windows supplied only terminal center points. Generic orthogonal routes therefore searched side entries and obstacle detours without an explicit opposite-face cavity-axis strategy.

The new strategy integrates actual cylinder/cone/annulus machining profiles with the assigned window, including offsets and rotation. An inscribed coaxial corridor must establish the existing overlap volume and, when specified, flow opening. Binary search finds the minimum sufficient drill-tip stop; source seats, lands, other windows and deeper machining remain protected. Eligibility uses loaded analytic geometry, without a separate BRep build per terminal. Complete routes still pass ordinary source, wall, cross-net, plug and access screens and authoritative exact validation.

Opposite-face handling covers all six installation faces. Generated accesses are real drillings with diameter, depth, 118-degree tip and plug semantics. A genuine coaxial functional port may close the entry. Required authored construction accesses retain their identities. No closure definitions or user settings were invented.

T-10A's actual cutting body ends at 51.8 mm within `port1`; `port2` is shielded by deeper machining. Both P and T can generate `port1` deep-end candidates. With the fixture's Fewer plugs priority, the complete clear combination selects axial T and a different side P route. A/B remain unchanged. Existing objectives choose normally; no axial score bonus was added.

| Observed two-T-10A fixture | Before | After |
|---|---:|---:|
| P drillings / plugs | 5 / 4 | 4 / 3 |
| P total drilling depth, mm | 444.04 | 379.06 |
| T drillings / plugs | 4 / 3 | 3 / 2 |
| T total drilling depth, mm | 422.06 | 350.12 |
| All drillings / plugs | 16 / 13 | 14 / 11 |
| All total drilling depth, mm | 1476.10 | 1339.18 |
| Exact PASS / WARNING / FAIL | 684 / 13 / 0 | 584 / 11 / 0 |

T's bottom axial access has cylinder depth 146.122133 mm. Its tip makes sufficient first contact at the actual deep window without drilling to its center. All assigned cavity interfaces remain connected. The 11 warnings are unresolved construction closures; overall status remains WARNING.

`_protected_source_cuts()`, `route_obstructions()` and exact validation rules were not relaxed. Normal proposals, incremental preview, Validate and Optimize share the strategy. Preview preserves unaffected nets and compares clear axial alternatives even on the current-template fast path. Approximate warm P-move proposal time was 0.360 s before and 0.190 s after; this excludes imports, transport and final exact preview geometry. Eligibility itself performs no BRep build.

Verification: 42 focused Python tests passed, covering six faces, protected/offset counterexamples, tip/flow contact, tool resizing, functional ports, required accesses, T-10A/rebuild identity, pruning, local dependencies and store/API guards. Optimize evaluated two exact candidates and retained 0 FAIL. `python -m manifold prove` produced corrected **268 PASS / 1 WARNING / 0 FAIL** and preserved the invalid **6 FAIL** case. `git diff --check` passed. No broad regression suite was run.

Code: `manifold/cavity_access.py`, `manifold/routing.py`, `manifold/preview_routing.py`, `manifold/schema.py` (automatic variant syntax only). Tests: `tests/test_cavity_axial_access.py`, `tests/test_preview_geometry_reuse.py`. SQLite, engineering source definitions and saved user projects were not modified.

Local raw evidence: `output/axial-routing-20260930/before.json`, `after-final.json`, `optimization.json`, `pytest-delivery/` and `proof-delivery/`. These generated artifacts remain outside Git.
