# V1 correction and engineering visualization acceptance

Verified locally on 2026-09-12. This pass changes V1 routing, geometry review, manufacturing evidence and project behavior. Geometry PASS remains distinct from manufacturing readiness or pressure certification.

## Implemented boundaries

| Request | Result and regression evidence |
|---|---|
| 1: transient inspection | `resolve_design` is transient by default. Repeated real automatic-route `/api/preview`, `/api/preview-solid`, freeze and refinement calls are checked with writes forbidden. Builds opt into route-selection evidence. |
| 2: optimization budget | Explicit optimization resolves one proposal per attempt; its total exact budget includes the baseline. A regression counts three validations for three attempts and fails on any nested exact selection. |
| 3: source-backed ports | CSV rows and JSON machining profiles retain all mapped cuts, axial intervals, cone/annulus parameters, offsets and native recipes. Generic drill L/D excludes definition-backed ports. Route ranking uses mapped machining; hydraulic summaries remain connection/routing hints. The inspector distinguishes machining extent from a window mask clipped to the cut. |
| 4: CLI semantics | File, default and saved-project validation resolve routes/parents and authorize generated contacts before exact validation. An unresolved automatic project produces matching CLI and application-resolution graphs/counts without STEP export. |
| 5: frozen ownership | A route segment's circuit must match its single route owner. Frozen ownership requires the corresponding manual net. The inspector directs hydraulic-intent changes through Reroute instead of exposing a contradictory circuit edit. |
| 6: refinement assertions | The regression asserts nonempty, exact counts and PASS results for `expected_connection`, `connected_interface` and `circuit_connectivity`. |
| 7: runtime identity | A process-start manifest records source SHA-256 values, loader executable-code hashes, Python/platform and installed CAD dependency versions. Disk/dependency drift makes builds stale and blocks new build evidence until restart. A source-mutation regression verifies the old engine ID never changes to claim new code. |
| 8: MDTools history | The source audit now distinguishes historical direct ODBC extraction from the currently unavailable original MDB files. |
| 9–10: drill ends and closures | Exact and approximate views follow the explicit drill angle, including 118° tips and 180° flat ends. Closure exclusions, drill points and complete machining are separate. Unbound raw plug/tool records are preserved but do not define invented counterbores, threads or seats. Plug-entry machining remains explicitly unresolved in this V1 representation and prevents manufacturing-ready status. |
| 11–12, 15: hydraulic networks | Exact flow nodes are boolean-unioned separately per net before tessellation. Same-net intersection surfaces are removed. Cross-net intersections retain separate nets, exact collision solids, a visible invalid-contact notice and contact isolation. |
| 13–14: machining versus flow | Machined void is exactly `stock - production`, clipped to stock by construction. Separate feature layers retain cavity machining, external-port machining, hydraulic windows and closures. Flow unions exclude declared plug volumes and use the installed-interface nodes. |
| 16–17: depth and preview | Exact Solid uses ordinary depth/occlusion; hydraulic X-ray is explicit. Editing replaces old exact meshes with an identified approximate preview, then synchronizes both model and route selection with the matching exact result. Rendering triangulates copies so it cannot alter subsequent validation bounds. |
| 18: A–F fixtures | Exact Python and real-browser fixtures cover perpendicular connected bores, conical tips, flat ends, plugs, cross-net collisions and a source-backed stepped external port. |

Raw resources without a mapped and bound machining profile remain unresolved. This pass does not add a new plug/tool knowledge base or infer profiles from names. A source window marked `clip_to_cut` is an interface mask, not a claim that its whole envelope is an open constant-diameter bore.

## Verification performed

- Python suite: **199 passed**, four dependency deprecation warnings. `output/tests-v1-final.xml` and `output/tests-v1-final.log`.
- `python -m manifold prove --out output/proof/v1-correction-final-engine`: invalid case **264 PASS / 6 FAIL**; corrected case **238 PASS / 0 WARNING / 0 FAIL**, including STEP round trip. Both cases remain under that output directory.
- Node alignment suite: **5 passed**. Real-browser continuous-drag regression retains the automatic route reference through four pointer moves.
- Browser fixtures: A–F in exact net, machining-void and Solid modes; independent machining/closure layers; explicit X-ray; isolated cross-net contact; 118° versus 180° parameter previews. Screenshots and browser logs remain in `output/playwright/` and `output/browser-engineering-v1-final.log`.
- Actual application at `127.0.0.1:8765`: project opening, mode switches, X-ray, freeze ownership, approximate-to-exact editing, source window inspection, and Save & Validate. Source-port project: **30 PASS / 0 FAIL**. Cross-net project: **23 PASS / 5 FAIL**, with STEP download disabled and an exact **666.67 mm³** contact notice.
- `npm run build` and `git diff --check` pass. Vite reports its existing large-chunk advisory.

The proof and source-port application build used engine revision `6bc837b9845d3bc74185af971f914ac23f239518d35efd66b6db55b0ed6f46f9`. A separate process reproduced this identity. Runtime: CadQuery 2.7.0, cadquery-ocp 7.8.1.1.post1, CasADi 3.6.7, NLopt 2.9.1, NumPy 2.4.6 and Pydantic 2.13.5. Checkout/runtime differences conservatively require fresh evidence.

## Reproduce

Run from the repository with its pinned `.venv` and installed frontend dependencies:

```powershell
.venv/Scripts/python.exe -m pytest -q --junitxml=output/tests-v1.xml
.venv/Scripts/python.exe -m manifold prove
node --test tests/route-alignment.test.mjs
.venv/Scripts/python.exe scripts/export-v1-view-fixtures.py
node scripts/check-engineering-views.mjs
node scripts/check-viewer-lifecycle.mjs
npm run build
```

The browser fixture exporter reads the already available converted MDTools library. Generated models, local QA projects, screenshots and build snapshots are local evidence, not changes to immutable historical builds.
