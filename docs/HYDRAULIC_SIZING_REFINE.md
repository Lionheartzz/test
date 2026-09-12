# V1 hydraulic sizing and adoption of the displayed route

Automatic nets now have an explicit `diameter_mode`: `automatic` (default) or
`manual`. For declared flow Q in L/min and velocity v in m/s, the required area is
Q × 1000 / (60 × v) mm² and the required diameter is √(4A/π). The next available
standard drill at or above that requirement sizes every generated segment,
including plugged construction access drillings. No sufficiently large standard
drill produces an explicit blocking sizing error; the largest drill is never used
as a silent fallback.

The Hydraulic Nets editor displays the calculation, selected drill, unresolved
flow/range, or engineer override. Editing the diameter explicitly selects manual
mode. No-flow automatic nets retain an explicitly unsized proposal diameter.
Legacy records without a mode preserve non-8 mm diameter choices as manual; the
old ubiquitous 8 mm default remains automatic/unsized. New explicit 8 mm choices
are preserved through `diameter_mode: manual`.

Exact validation checks the actual section of every hydraulic node against the
declared flow, in addition to the existing exact intersection opening checks.
Source cavity windows and external-port profiles remain unchanged. Insufficient
source interfaces, manual bores and frozen drillings report
`hydraulic_passage_area` failures. These remain V1 characteristic area/velocity
checks, not CFD, pressure-loss calculation or manufacturing certification.
Plug entry/thread/seat selection remains unresolved where no source is bound.

Refine in 3D sends the currently displayed resolved proposal with the draft.
Adoption checks its stock, source definitions, primary features and net ownership,
then copies its generated segments verbatim into frozen/manual ownership. It does
not call the route resolver or optimizer for supplied proposals. One BRep contact
pass preserves direct connection declarations. Legacy non-viewer calls without a
proposal resolve only one transient proposal, never the exact candidate search.

The button immediately shows adoption in progress and prevents duplicate clicks.
Success preserves the segment ID, selection, exact displayed model and visibility,
and enables dragging. Failure shows the actual reason and clears the waiting state.
Draft changes while adoption is pending reject the stale response. Frozen routes
are authored geometry: subsequent flow changes only change validation demand.
Choose automatic sizing and explicitly Reroute to resume automatic sizing.

## Regressions and evidence

- `tests/test_hydraulic_sizing.py`: 40 L/min at 6 m/s requires Ø11.894 mm,
  selects Ø12 mm, and passes exact opening checks; unavailable range blocks;
  manual Ø8 remains and fails; construction drillings inherit Ø12; source windows
  remain unchanged; displayed adoption cannot call routing; frozen geometry
  remains unchanged after increasing flow and becomes hydraulically inadequate.
- `node scripts/check-sizing-refine.mjs`: real browser sizing display, immediate
  pending feedback, failed adoption/retry, captured proposal equality, retained
  segment selection, retained exact BRep/37% stock context, and actual dragging.
- Local sizing build evidence is in `output/hydraulic-sizing-proof`: manual-small
  has 37 PASS / 7 FAIL; automatic-sized has 44 PASS / 0 FAIL including STEP round
  trip. Source dimensions are test fixtures, not vendor-approved geometry.
- Existing store/API, routing, workflow and engineering regressions were exercised.
  The final focused run passed 27 tests after fixing an empty protected-region
  intersection found by the source-window regression. Frontend build passed.
- Standard proof: `python -m manifold prove --out output/proof/sizing-refine-final`.
  Failure reports and corrected-build evidence are retained locally.
