# Material UI and CAD-safe automatic routing

Starting HEAD: `f8bf30dc2674d081e85cd154d819b0eee80fc2dd`. Branch: `codex/sqlite-domain-reset`.

## Material UI

- Model Material & stock contains Engineering material and Raw stock / standard blank selectors. Research values, conditional observations, evidence links, supplier/treatment counts and source provenance were removed from the material inspector. Actual stock allowances remain visible only for selected engineering stock.
- Native optgroups use runtime `material_type`: Aluminum Alloy (5), Carbon Steel (1), Stainless Steel (4), Ductile Iron (2). Total: 12 precise choices; precise selected labels are unchanged.
- `material_1` / `material_2` remain loadable. Only the current legacy ID appears in an old project; neither appears in new-project selection. Library research/evidence and the central fact resolver remain intact.

## Automatic routing

The previous exact search saw an ownerless block-level topology FAIL but repair only followed routing-owned checks. It evaluated one candidate, then returned the invalid production solid.

Exact selection now rejects invalid/multiple-solid production CAD, checks fixed machining once without automatic generated routes, and uses the retained strategy pools for bounded automatic-only fallback. The full-combination search excludes inspected combinations. STEP runs lazily on the otherwise selected exact candidate; failed serialization updates its score and permits the next candidate, including a worse manufacturing objective. Validate, Build and Optimize share the resolver and the same gates. Build retains the selected, checked production STEP. Default 8-attempt / 240 s search and 300 s authoritative worker ceilings remain; preview still uses the approximate branch and one background exact geometry request.

Real project: `6e57fdcccb174b87a72c32f3069bb285`; source fixture: `tests/fixtures/automatic-cad-topology.json`. Original failed build `50ed9806153e434299a25f436302ba7d` remains immutable. Final actual LAN Validate build: `5f5aa4d595374aaa8ca9b896f0020044`.

| Net | Before | After |
|---|---|---|
| A | `simple_72` | `xyz:nearest:offset_y_m` |
| B | `yzx:nearest:direct` | `yzx:nearest:direct` |
| P | `axial_1_0:yxz:nearest` | `axial_1_0:yxz:nearest` |
| T | `axial_1_0:xyz:nearest` | `axial_1_0:xyz:nearest` |

| Measurement | Before | After |
|---|---:|---:|
| Production BRep valid / solids | false / 1 | true / 1 |
| STEP valid / solids | false / 1 | true / 1 |
| STEP volume delta / mm³ | 0.000148904 | 0.000978969 |
| PASS / WARNING / FAIL | 448 / 12 / 2 | 450 / 12 / 0 |
| Automatic drillings / plugs | 11 / 8 | 11 / 8 |
| Total / max drilling depth / mm | 1088.144 / 146.122 | 1091.244 / 146.122 |
| Exact candidate attempts | 1 | 2 |
| Standalone resolver timing / s | 16.39 | 36.50 |
| Recorded real Validate worker time / s | 22.95 | 46.89 first success; 54.55 final (concurrent proof) |

Both old and new volume deltas are below 0.01 mm³; the old STEP failed validity. Failure rows now name invalid STEP topology, solid count or volume condition truthfully. No source-protection, wall, hydraulic, priority or closure rule was relaxed. Authored geometry, material ID, fixed/manual/frozen machining and net intent are unchanged; the existing UI refresh synchronized the material display label. The 12 warnings remain 8 unresolved construction closures and 4 engineering-review items.

Local P move benchmark (same source/proposal, three runs; baseline routing loaded read-only from the starting Git object): median 1.719 → 1.766 s. Only P recomputed; A/B/T retained, no conflict expansion, no STEP gate in preview.

## Verification

- Focused Python: 47 distinct tests passed (31 routing/priority/incremental/store-build tests, 8 CAD-safe regressions, 8 store/API tests). Final source check: 22 relevant tests passed. No broad suite; the previously accepted baseline failures were not reclassified.
- CAD-safe tests use a real invalid OCCT open-shell solid and the real exact candidate path for Validate/Optimize. STEP recovery fakes only the export/reimport result and checks the Build artifact. Fixed invalidity, manual/frozen preservation, all four priorities, bounded attempts and the current real project are covered.
- Real two-T-10A routing fixture remains 0 routing FAIL, with existing pruning/dominance and incremental locality checks passing.
- Relevant JavaScript tests: 26 passed. Vite build and `git diff --check`: passed.
- `python -m manifold prove`: invalid case 295 PASS / 2 WARNING / 6 FAIL; corrected case 268 PASS / 1 WARNING / 0 FAIL.
- Real localhost browser: 12 choices, new/legacy project behavior, four native optgroups, selection-only Model fields, Library material evidence retained; zero page errors. Real LAN browser at `http://192.168.253.117:8765`: `isSecureContext === false`, same 12 grouped choices, final real-project Validate 0 FAIL.
- Runtime SQLite/schema/source data unchanged. Production DB SHA-256: `4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`.

Screenshots: [clean material inspector](output/playwright/cad-safe/lan-material-selectors.png), [actual Validate result](output/playwright/cad-safe/validated-real-project.png), [Library evidence](output/playwright/cad-safe/library-material-evidence.png). Raw before/after, per-attempt diagnostics and local timing are in `output/cad-safe/`.

Changed implementation: `web/main.js`, `web/engineering-inputs.js`, `manifold/cad_acceptance.py`, `manifold/routing.py`, `manifold/store.py`, `manifold/optimization.py`; focused tests and browser scripts updated. Commit/remote HEAD and clean tree are reported after push.
