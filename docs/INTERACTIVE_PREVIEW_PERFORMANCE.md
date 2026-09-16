# Ordinary cavity-move exact preview

This follow-up starts from `780a362` on V2.3. It addresses a newly created 160 × 100 × 150 mm manifold with two pinned T-8A cavities, four front ports and four automatic hydraulic nets. The source cavity definitions, route feasibility rules and 15-second preview watchdog are unchanged.

## Reproduction and cause

The saved reproduction and two displayed cavity positions both reached the 15-second deadline. Native stack capture at six seconds located the stall in `ShapeUpgrade_UnifySameDomain.Build`, called by CadQuery `Shape.clean()` from `review_model` while generating the machined void. The route proposal and exact production construction had already finished, as had the first production mesh. This was a display topology simplification stall, not route optimization or exact validation.

One recorded failed preview spent approximately 1.06 seconds resolving its current proposal, 0.42 seconds constructing geometry and 0.45 seconds tessellating the body, then stalled in void cleanup. The watchdog stopped it at 15.03 seconds. A second placement reproduced the same failure.

The fix removes same-domain face unification from review-only void, hydraulic union and collision results. Their exact Boolean operations remain; their actual BReps are tessellated, with no concatenated approximate tubes. The authoritative production construction and validation path retain their existing behavior. Added phase names distinguish production Boolean work from review removed-volume work, and native-operation entry is flushed to diagnostics before entering OCCT, so a stuck call cannot leave only an old outer phase in the trace.

## One calculation per edit

The old browser sequence started one worker for a fast route proposal, then another worker to resolve that proposal again and produce exact geometry. The default UI now requests an NDJSON stream from the existing exact-preview endpoint. A single worker emits the current proposal as soon as routing completes, then completes geometry and review generation for that same snapshot. Its original 15-second deadline covers the entire computation. Existing JSON callers are still supported.

Local parametric feedback remains immediate. Coalescing, immutable snapshots, cancellation and obsolete-result rejection apply to both streamed progress and the final model. Mesh JSON is serialized in the worker and forwarded as bytes. A post-header failure is an explicit error event, not a successful partial result. The browser also retains its independent deadline.

## Display and engineering status

The viewport distinguishes approximate live feedback, exact computation in progress, an exact unvalidated proposal, exact preview unavailable, and an authoritative Save & Validate result. A recovered preview clears the old timeout notice. Camera, selection, net mode and stock opacity remain intact through updates.

Some current automatic proposals in this reproduction have invalid BRep topology before this change. Exact preview is allowed to show the current proposal, but now explicitly exposes that topology condition. It is not reported as engineering PASS and no tolerance, source cavity or hydraulic opening is changed to hide it. Exact feasibility and STEP checks remain authoritative.

Builds now finish and persist validation, STEP round-trip and manufacturing evidence before display review generation. Only then can the worker write an engineering-complete checkpoint. A Python review error writes an explicit unavailable-review descriptor. If native review work becomes stuck, its remaining display budget is capped at 15 seconds and the worker is terminated; only the already-complete engineering report can be returned. No checkpoint exists while engineering checks are incomplete. Native crashes still reject ordinary worker results. The UI can show the actual authoritative result with an unavailable exact review and a clearly approximate view.

## Evidence and regressions

[Timing evidence](evidence/interactive-preview-move-profile.json) includes both reproduced timeouts and four successful streamed runs: initial placement, a 1 mm cavity move, a further move in both coordinates, and return to the initial position. Each successful edit performs one route resolution and one geometry construction, with no transient validation, STEP export or route-selection evidence. These are local samples, not guarantees on arbitrary hardware or manifolds.

`tests/test_interactive_preview.py` covers normal cavity moves below the watchdog, exact stock/void/net layers, unchanged pinned source geometry, review-only failure isolation, and exact volume preservation on valid geometry. `tests/test_cad_execution.py` exercises a native CPU loop during review and verifies that the returned report exactly matches the completed validation artifact, including the real STEP check; it also checks streamed timeout errors. The JavaScript regressions cover incremental/fragmented streaming, early proposals, failed or truncated streams, obsolete progress and one request per draft.

`tests/interactive-preview.run.js` creates an isolated QA project, edits cavity position through the actual properties UI, verifies approximate/computing/exact/unavailable states, retains selection and stock context, and checks recovery after a timeout event. The QA project is removed after the run.
