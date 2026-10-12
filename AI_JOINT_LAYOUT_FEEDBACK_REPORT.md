# AI joint layout and machining feedback

Starting HEAD: `ba8d3ddf2275168629f35dcf79a137ce4572fbeb`.

The disconnected loop had four concrete causes. `layout_search.screen()` scored machining and conflicts from an incompatible diagnostic full assignment instead of its actual compatible core. `joint_layout.optimize()` failed to refresh recorded assessments and action generators after routing refinement. `Session.seed_combination()` repeatedly inserted duplicate cores, evicting different arrangements. Finally, zero-label layout screens could still run expensive fragment searches when a reused core was nearly complete.

The correction retains an explicit search-only joint state: stock, source placements, compatible cuts and terminal dependencies, missing Nets, current-core insertion conflicts, deferred pair screens and Exact failures. Diagnostic full assignments are separate. Ranking uses hard failures, compatible coverage, machining objective and then stock volume. No analytic result is engineering approval.

`route_feedback.py` consumes current-core and Exact cutting-feature attribution. Complete machining bounds and required wall determine separating distances. It can move both terminal groups, insert measured stock space, intersect several blocking constraints, and expand a moving cluster when it hits another movable source installation. All resulting sources and all regenerated Nets are screened again, including the third Net. Permitted face/window orientation alternatives remain available. Bounds guide proposals; they do not authorize hydraulic contact.

Small layout screens explore existing pools without fragment regeneration. Selected layouts retain bounded refinement; an unproductive refinement records a geometry-revision decision instead of repeating the same geometry. Refined and Exact-rejected states replace obsolete feedback generators and update the journal. Compatible cores are deduplicated, diversified and rechecked against current source geometry before reuse. Existing numerical budgets were not increased.

Verification used general QA definitions, not vendor or eight-valve special cases:

- Default shared-Router AI search: two individually source-clear, crossing networks; compatible coverage **1/2 → 2/2**. Joint terminal motion and stock height **20 → 28.01 mm**; fixed mounting faces preserved. Eight layouts, 31 transforms, one Exact attempt, **2.891 s**.
- Real authoritative result: **93 PASS / 0 WARNING / 0 FAIL**, valid single-solid BRep, valid single-solid STEP, volume delta **0 mm³**. Input Design unchanged. Only the disposable worker transport was replaced with its identical local Exact body for the QA case; candidate generation, geometry, engineering validation and STEP were real.
- Restricted real coaxial candidates exercise refined failure → new layout → real Exact acceptance. Another three-Net case verifies collision-driven joint source motion and all-Net compatibility screening. Explicit coordinate/face/rotation/size locks, diagnostic ranking independence, core diversity and changed-source invalidation are covered.
- Focused feedback/coordination/routing checks: **20 passed**. Three selected ownership/compilation boundary checks: **3 passed**. Static Python compilation and `git diff --check` passed. No T-10A, prove, broad suites, browser, Vite or paid AI calls.

All runtime changes are under `manifold/ai_design/`. Shared Router/Model execution paths and acceptance rules were unchanged. `LayoutDomain` still requires explicit new-generation ownership; AI origin metadata grants no permission. SQLite and all nine saved projects retain their pre-change SHA-256 hashes.

Limits: this remains bounded search, not a proof of global feasibility. Conservative machining bounds can suggest ineffective actions, which are re-screened. Topology/STEP failures without attributable geometric evidence remain explicit engineering failures. The eight-valve long search was deliberately not repeated; its existing partial routing result is not promoted to full acceptance.

Compact evidence: `docs/engineering/ai-joint-layout-feedback-evidence.json`. Local reconstructible search and Exact outputs: `output/runtime-checks/joint-feedback-20261012/default-search/`.
