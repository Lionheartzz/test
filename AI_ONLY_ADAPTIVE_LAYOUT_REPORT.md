# AI-only adaptive block sizing and layout

Starting HEAD: `8434cd952e65b075561ad87e974fce0746dc39df`
Branch: `codex/sqlite-domain-reset`
Verification: saved evidence and static inspection only, as requested.

## Ownership boundary

`ai_design/generation.py::_plan_generated_layout()` is called only while
`candidate()` compiles a new AI Design. It receives the freshly constructed
candidate and generated feature IDs, never the active Model project. There is
no persisted adaptation permission and no check of `origin.method` granting
future access to dimensions or placements.

Initial dimensions still come from source footprints, machining depths, actual
flow-derived bores, material/wall requirements and the existing draft defaults.
After initial placement, AI generation applies at most one better analytic
layout. The packet retains the baseline, selected assessment, dimensions,
evaluated count and source revision. One editable Draft is delivered, with no
Exact CAD attempts during generation and no claim of verified connectivity.

Equal dimensions remain enforced by the envelope. Linked project dimensions
are excluded from growth unless superseded by explicit new envelope intent;
minimum/maximum requirements remain binding. Unsupported explicit position
requirements stop further automatic arrangement and remain blocking review
items. Fixed mounting features prevent growth. No stock SKU is invented.

After handoff, the AI Draft is a normal Model project. Preview, Auto Route,
Reroute, Optimize, Validate, Build, Save and Reload do not acquire layout
authority. The shared Router and incremental preview have no layout-planner
imports/calls. Their geometry ownership logic is unchanged. Manual, frozen,
committed and authored cuts remain protected by existing permissions.

The existing Model `Review layout alternatives` endpoint/UI remains a read-only
proposal operation with revision checks, an explicit Apply button and Undo.
It is not called from ordinary preview or routing.

## Layout correction and bounds

The previous Exact-evidence queue contained only local moves and port alignment;
its conditional omitted `growth()` entirely. Exact attribution now prioritizes
owners without excluding growth from explicit proposals.

Growth inserts one measured lane along one allowed axis. The lane uses effective
route bores, required wall, minimum access gap and source-window routing reserve.
It shifts one interface group across that lane. A uniform translation is
rejected because it creates no relative clearance. X/Y are considered before Z;
source footprint, envelope, depth and installation spacing screens still apply.
An expanded candidate must improve the engineering feasibility screen, not
merely its machining objective.

AI generation reuses the existing explicit planner's eight-layout limit in
place of the old four-layout initial sample. This repairs growth-family
starvation without increasing Router or Exact budgets. At most 48 transforms
are examined, eight layouts assessed, eight analytic route samples retained per
Net, and 32 sample attempts made per Net/layout. Shared three-terminal topology
candidates now participate alongside axial, direct, detour and port approaches
within the same sample bound. No hydraulic algorithm is duplicated in AI.

Missing methods, data or tooling alone do not trigger growth. Only spatial
screen failures or matched Exact attribution justify a size alternative.
There is no repeated growth loop or multi-layout BRep search. If samples remain
blocked, the original/better editable proposal retains its unresolved review
and still requires Exact Preview/Validate; source-window limitations are not
declared solved by increasing stock.

## Current saved evidence

Trace: `output/cad-diagnostics/9b78ff1968b9463690a9232ca34e550a.json`
Trace SHA-256: `05e002d5a503063dcd1a9c55c80300ddaaaed75fbc6b25a241e15c3c03cfa8e8`
Authored source revision: `341257eaca684b5a0946157f6366616016253038cedbde6821d5771f2a034556`
Matching saved project: `projects/saved/2b93c6c68df24d5ebe543215e8e91c99.json`
Saved file SHA-256: `450ff90ca5ae82b958fae5e45558cf57c37be7ce5c9468aa13072934fed43f2a`

The match was checked using canonical sorted JSON SHA-256, without importing
project/CAD code. Dimensions: 275 × 175 × 115 mm; 23 generated drillings.
Current exact contact is **MA ↔ MA_CBCG1_to_DSCS**, 116.10642475474 mm³:

- MA `R-f0055891-3`: left face, U 149.67637, V 66.7775, Ø8, depth 107.885 mm.
- CBCG1 `CV_dd5023b2cc1f5540d5ca:port2`: cavity top face, U 77.875,
  V 149.6763697733023; definition `cav_000ea3efc223ffbed29f`.

This is not the old MA↔T or MB↔T pair. MA retained 0/181 candidates, with
source protection, plug/access and connectivity rejections; MB retained 0/144.
No global clear combination existed in that saved run. Its unresolved display
must not be described as an engineering-safe route.

Saved timings (overlapping nested operations, not additive):

| Operation | Count | Seconds |
| --- | ---: | ---: |
| Request | 1 | 538.891 |
| Route proposal | 1 | 528.516 |
| Route simplification | 159 | 435.732 |
| Hydraulic opening | 613 | 409.189 |
| Boolean intersection | 2114 | 421.339 |

The saved bar remained at 8% until 528.125 seconds. This replaces the obsolete
10-opening/82-second failed trace as the current performance evidence.

## Shared Router calculation changes

Exact contact volume/opening measurements are cached independently of the flow
area and overlap acceptance threshold. Geometrically identical generated fluid
cuts share a key retaining block dimensions, full machining, closure and pose;
graph IDs and Net ownership labels do not prevent reuse. Acceptance is still
computed separately for each Net's real conditions. Source BReps remain owned
by one fixed-source snapshot. Null/invalid/unavailable geometry remains a
rejection, never a zero-area substitute or PASS.

Opening calculation evaluates identical/opposite-normal centroid planes once.
No approximation, overlap relaxation, invented flow or source-protection change
was introduced. Actual positive opening and all-terminal connectivity gates,
global conflict checks and exact validation remain authoritative.

The existing timing trace now reports machining-access screening, hydraulic
connectivity checks and global circuit screening, with current Net, completed
candidate checks and prepared route pools. Progress follows actual count
milestones, remains monotonic and cannot reach 100% before completion. Existing
150 ms publishing and owned-operation polling are reused; no ETA or wall-clock
deadline was added. AI generation uses its existing owned job progress callback
for layout/Net milestones and cancellation.

## Static delivery and runtime limits

Changed code: `ai_design/generation.py`, `layout.py`, `layout_planning.py`,
`routing.py`, `preview_routing.py` (boundary documentation only), `flow.py`,
`timing.py`, `validation_progress.py`.

AST parsing and in-memory Python compilation passed for all eight files.
`git diff --check` passed. No tests, CAD generation, browser, Vite, synthetic
benchmark or paid AI call was run. No database, provider configuration or saved
project was changed.

Protected database SHA-256 remains
`1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.

Still unverified: newly selected AI dimensions/positions, runtime calculation
time, progress appearance, exact MA connectivity/contact, BRep/STEP and final
validation counts. The saved collision is evidence of the previous result,
not proof that this correction achieves zero FAIL. A subsequent real Preview
is required; no current saved/manually edited project is silently redesigned.
