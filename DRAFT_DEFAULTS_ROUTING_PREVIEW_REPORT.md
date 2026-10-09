# AI Draft defaults and Model preview routing

Starting HEAD: `dc97deca5ce029dd09c3ff5c5f1c221013f4b306`

Branch: `codex/sqlite-domain-reset`. Starting tree was clean.

This delivery implements the requested changes using source inspection and saved artifacts only. **No new Draft, routing result, material qualification or BRep PASS has been demonstrated.** The commit and verified remote SHA are supplied with delivery; this report belongs to that commit.

## Defaults and material

- Precedence: current explicit requirements, linked-project settings, then existing shared application defaults / deterministic PMC proposal. Conflicting explicit material requirements are blockers. Current explicit envelope bounds supersede the corresponding linked bound; other bounds remain binding.
- New `draft_defaults.py` queries existing `engineering_db.materials()`, excludes legacy/unspecified identities from automatic proposals, and requires selectable source-backed grade/state and solid-stock form. It uses the existing `material_strength()`, `feature_ligament()` and `required_wall()` calculations. It evaluates actual working pressure, safety factor and envelope fit before a stable material tie-break; no grade is given an invented pressure rating.
- An ordinary eligible 6061-T651 bar/plate identity is preferred after screening. One existing bar identity is `material_rev2_3ef4c3d11a2c83779d42853e` (6061 T651 extruded bar, ASTM B221). The selected row supplies both `block.material_id` and its matching label. Selection was **not executed** in this task; this ID is not a claimed regenerated-project result.
- Explicit / linked identities are retained with an unresolved review if qualification fails, rather than silently substituted. Explicit environmental/treatment applicability remains unresolved when current facts cannot establish it. Legacy stress overrides are preserved, but cannot qualify a source material; initial sizing reserves space for both source and overridden ligament rules.
- The proposal basis is recorded in existing Engineering Review / origin metadata and the generation packet. Material remains editable; no extra confirmation is required for a valid preliminary proposal. No research/evidence panel was added to Model.
- Unknown operating pressure/flow remain `None` and get open engineering review items. Product ratings, capacities and relief settings are not operating loads. Explicit terminal/net loads and linked project defaults/overrides remain usable.
- Safety factor, velocity, drilling mode and priority come from the shared schema defaults or inherited/explicit settings. No new universal wall thickness was introduced.

## Initial dimensions

The old initial grid charged every cavity the largest installed footprint. New shared packing uses each definition's own machining/installed envelope, mounting face, access gap and required wall. Hydraulic bore size supplies a preliminary routing-space allowance. Source depth, port footprints, explicitly positioned mounting holes and envelope bounds participate. Linked block dimensions are preferred unless superseded by current requirements.

Only explicitly created projects use initial placement; load, Save, Validate, Build and Drawing do not reposition existing geometry. The one-Draft compiler remains analytic and performs no CAD search. Current precise material IDs have no associated `material_stock` rows: legacy Aluminum stock is **not** re-labelled as a precise 6061 blank. New dimensions and stock suitability were not measured by a generation run.

## Saved real evidence and attribution limits

Inspected generation: task `343f91fdb98c435296b6e78322157433`, generation `3c4612498e7d4125a2030452d5995525`. It produced an unvalidated 400 × 400 × 110 mm Draft in 4.05 s with 8 cavities, 4 external ports and 15 nets. Its inputs contain no material, pressure, flow or envelope requirements and no linked project. The authored artifact contains no generated route cuts.

Saved trace `8aeff7e8f54242bdac06ead53ea1b0e0.json` records an 85.187 s preview, including 72.157 s route proposal and a repair milestone. It does **not** retain the final approximately 28 drilling cuts, collision attribution or search-budget exit reason.

| Observed preview contact | What can be established without rerunning CAD |
|---|---|
| A_DC ↔ B_DC, 341.33 mm³ | These nets use separate windows of the directional-valve / T-17A interfaces. Exact offending drilling pair and feasible replacement are not recoverable from the saved authored Draft/trace. |
| MA ↔ MA_CBCG1_to_DSCS, 341.33 mm³ | The nets use distinct hydraulic windows, including the same T-11A component. No evidence supports merging them. Exact offending pair remains unverified. |
| MB ↔ P, 64.32 mm³ | Both belong to the same complete-layout isolation screen. The missing closure-entry screening path could affect wider local cuts, but this contact cannot be attributed to it from volume alone. |

341.33 mm³ is consistent with perpendicular Ø8 mm cylindrical intersection; it does not prove which features caused either contact. These observations are **not** a new Validate report.

## Shared Router changes

1. Ordinary orthogonal detour generation now sees other active generated routes. Existing offset variants retain their old source-based meaning; new explicit-coordinate `planes_...` variants encode repeatable detour coordinates. Project and preview-context validators share the variant pattern (no schema-version change).
2. Progressive repair supplies the complete current layout to ordinary and axial connector strategy generation while screening source-safe pools and all candidate pairs. This is shared routing, not an AI-only engine.
3. The old strict-improvement gate rejected every equal-conflict intermediate layout. A single changed-conflict plateau step can now occupy one beam slot; another plateau cannot immediately follow it, and a plateau alone is never returned as an improvement. Source protection stays ahead of cost. Budgets remain 256 states, 4,000 pair screens and beam width 4; final exact candidate budgets are unchanged. No wall-clock deadline was added.
4. `_manufacturing_cuts()` now uses the existing closure runtime contour for bound compatible plugs, including local entry/seat/transition machining. Previously it screened only the hydraulic bore/tip while production geometry cut the larger closure entry. No source dimension or closure definition was changed.
5. Final analytic conflicts retain editable drillings and stale/unresolved state, with peer net names and feature-pair metadata. Exact cross-net contact also marks only this request's newly computed/resized automatic proposal nets stale. Manual, frozen and unchanged committed routes are not rewritten; no false cross-net `connects_to` authorization is added.
6. The existing timing trace now retains bounded pool/family counts, state/pair counters, conflict history, plateau count, selected variants, remaining feature conflicts and exit reason. Preview diagnostics retain exact collision volumes and explicitly labelled **bounds suspects**, not falsely exact feature attribution.

## BRep and progress

The exact invalid-topology indication is preserved. No Boolean healing, source geometry replacement, mesh substitution or validation relaxation was made. For an invalid preview only, diagnostics inspect already built individual cuts / block machining and production solid count, separating invalid input cuts from unresolved combined-solid topology. They do not construct another BRep or run STEP. The real BRep cause and post-change validity remain **unverified**.

The existing progress node was outside `.hud-top` and overlapped ViewCube space. It now joins the same HUD flow, reserves right-side cube space, wraps on narrow screens and stays separate from the collision notice. Percentage remains backend milestone-based and monotonic within the displayed operation; only a completed response shows 100%. Worker activity / elapsed time and finished/error states are retained. No timer-derived percentage or new CAD timeout was introduced. Browser appearance is unverified.

## Protection and checks performed

- SQLite SHA-256 before/after: `1E3267BD6A6271CF819B5181ED52EAE55AB8B8B54A4A48CE45CC277175D7DAA2`.
- Local AI provider configuration SHA-256 before/after: `2585ED2E0E32FF5677CF0D3136FDD948F7A9C9CF951EB6683DF969CF742E190A`.
- Stage 1 recognition, provider/output contracts, compatibility data, source machining dimensions, saved projects, Drawing and committed route geometry were not changed.
- Python AST parsing and shared routing-pattern syntax compilation: passed. JavaScript `node --check` for the four changed JS modules: passed. `git diff --check`: passed.
- Per the explicit request, **no tests/test changes, browser automation, Vite build, CAD/prove/STEP run, AI generation benchmark or paid AI call** were performed. No service restart or frontend deployment/build was performed.
- Material runtime selection, compact layout feasibility, real collision clearance, BRep/STEP validity and runtime performance remain unverified. Static implementation is not engineering/manufacturing acceptance.

## Changed files

`manifold/draft_defaults.py`, `manifold/layout.py`, `manifold/ai_design/intent.py`, `manifold/ai_design/generation.py`, `manifold/routing.py`, `manifold/preview_routing.py`, `manifold/schema.py`, `manifold/cad_worker.py`, `manifold/timing.py`; `web/ai-generation.js`, `web/main.js`, `web/preview-routing.js`, `web/studio.css`, `web/validate-progress.js`, `web/validate-progress.css`; this report.
