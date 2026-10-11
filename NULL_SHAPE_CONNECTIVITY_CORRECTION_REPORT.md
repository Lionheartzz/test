# Null TopoDS connectivity regression correction

Starting HEAD: `2cb7b2fd854d232318a3570524dd9383be5e8a39`.

Branch: `codex/sqlite-domain-reset`; starting worktree clean.

## Existing evidence and its limits

- Latest failed trace: `output/cad-diagnostics/a6a683edc6ca48c9869d06c2efdd3d9c.json`, SHA-256 `67e92611fff47b9af13ee55cee8f3d780bcbfd156b5b5e50a327f706afc83f36`.
- The preceding `d46ce11799844c0c80404f392948b2a6.json` has the same failure pattern.
- Both are `preview-solid`, engine `8962ab98fe863665c06b9129b8178cdb3f12ccbb3d54bf53e57b90ed39471267`, with `Null TopoDS_Shape object`.
- Latest owned elapsed time: **90.281 s**; 10 `hydraulic.opening` calls consumed **82.267 s**, within 3 route simplifications. There is no saved traceback, node pair, candidate variant or authored-source revision. `diagnostics` is empty.
- Contemporaneous saved Draft: `output/ai-design/343f91fdb98c435296b6e78322157433/generations/1e6e1a98e1624606b6d2799ec0edb30b/authored-draft.json`, canonical revision `f350eebe8633ca0034dbf3ee046025de857d9120f1429dd11052b64cc45f3ab2`. Its generation metadata has the same engine, precedes the failed requests, and has the reported 275 × 175 × 115 mm block. **The old failed traces cannot authenticate that this was their exact request revision.** Future traces record the normalized request revision before routing starts.

The installed CadQuery source identifies the exact error string at `cadquery/occ_impl/shapes.py::shapetype()`: it raises when `TopoDS_Shape.IsNull()` is true. `Shape._bool_op()` calls `Shape.cast(op.Shape())`, which reaches that check. Thus an intersection can throw during result wrapping, before the caller receives a Shape or calls `Faces()`.

The old trace supports the newly exercised opening path as the regression area. **It does not prove which particular Boolean, node pair or source section failed.** No traceback or exact operation attribution is fabricated.

## Why the previous change exposed it

`2cb7b2f` made exact opening checks mandatory even when actual Flow is unknown. It called an intersection for volume, then `opening_area()` repeated that intersection and intersected the result with each section plane. Those paths assumed all results were non-null usable shapes. The worker retained only the final exception text, losing the operation, ownership and traceback needed to distinguish an empty section from a kernel failure.

Mandatory connectivity and positive-opening verification remain enabled.

## Geometry handling

- New `manifold/cad_geometry.py` checks the actual installed CadQuery APIs: `isNull()` first, then `isValid()`. Non-null compound emptiness uses `Compound.__bool__`, backed by `TopoDS_Iterator.More()` in the installed source. No downstream bounds/center/face/volume/Boolean access occurs on an identified null shape.
- A valid empty compound intersection returns zero solid volume. Valid face/edge/vertex-only intersections also have zero **solid** volume. A valid section with no faces, or zero face area, returns zero opening.
- A null result, invalid topology, or recognized OCCT failure is an unavailable geometric evaluation, **not** a fabricated zero or positive opening. A null result rejected by CadQuery during casting is caught at the operation boundary.
- Only `Standard_Failure`, the exact CadQuery null-cast `ValueError`, and explicit topology-check failures are contained as geometry errors. Other Python exceptions propagate to the worker and receive a local traceback; they are not silently treated as constraints or PASS.
- `opening_area()` validates its common solid and section results before property access. It still computes real exact sections. The route graph passes the already computed common geometry to avoid repeating the same Boolean.

## Candidate and source containment

`routing.py::_verify_route_candidate()` now contains recoverable generated-candidate geometry failures. Records include phase, CAD operation, Net ID, variant, affected nodes where available, safe null/validity states, original exception class and bounded traceback. Failed geometric evaluations are cached separately from verified no-contact outcomes.

The rejected candidate receives no connectivity proof and cannot enter `_candidate_admitted()` or the feasible global pool. Other candidates continue within the existing shortlist/search budgets. Its potentially malformed generated cuts are withheld from production geometry; if no usable route remains, the Draft retains its authored/source geometry with explicit `candidate_geometry_error` and connectivity failures. This does not delete manual, frozen or committed machining.

Shared source cuts and fluid nodes are checked separately before candidate contact evaluation. Failures while constructing or inspecting that shared geometry propagate as **source geometry unavailable/invalid**, with distinct diagnostics and a short source-specific message. They are not mislabeled as an impossible physical route and do not trigger random rerouting of fixed geometry.

`cad_worker.py` records `request_source` before routing, plus bounded local `worker_failure` tracebacks. Candidate/source diagnostics use the same timing trace. Normal UI receives short actionable CAD messages, not tracebacks, complete designs or OCCT dumps.

## Other defects found

1. **Dimension-dependent mass:** the installed `Shape.Volume()` calls `computeMass()`, whose face/shell calculation uses surface properties. A lower-dimensional contact could therefore look like positive "volume". Hydraulic overlap now sums actual Solid volumes only. Opening measurements also remove zero-volume face/edge remnants from mixed common geometry, preventing the compound's first-child dimension from determining the centroid incorrectly.
2. **Duplicate common Boolean:** the route graph's overlap was recomputed inside `opening_area()`. The exact common is now reused; no opening calculation is disabled.
3. **Failure marked finalizing:** `run()` advanced to 99% finalizing even after an exception, overwriting useful progress context. It now advances there only on success; failures retain operation-specific diagnostics.

## Scope and verification

Files changed: `manifold/cad_geometry.py`, `manifold/flow.py`, `manifold/routing.py`, `manifold/cad_worker.py`, and this report. No source machining definition, SQLite data, provider configuration, AI Stage 1, layout logic or routing budget was changed. The three-terminal alternatives and all fail-closed admission gates remain.

Performed: existing trace/source inspection, installed CadQuery API source inspection, in-memory Python AST/syntax compilation, and `git diff --check`.

As requested, **no automated tests, browser automation, Vite build, CAD Preview/generation, paid AI call or regression suite** was run. Actual Preview recovery, the original failed operation/pair, new route feasibility, MA/T conflict resolution, engineering results and performance remain unverified until the next real Preview. No runtime PASS or zero FAIL is claimed.

Active DB SHA-256 unchanged: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.

Provider configuration SHA-256 unchanged: `2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`.
