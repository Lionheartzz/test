# V1 automatic routing: feasibility before machining cost

The old proposal order added proximity risk to machining cost. With `fewer_plugs`,
an intersecting P/T pair could be cheaper than a detour even after its collision
penalty. Exact selection already ranked validation failures before cost, but its
small candidate budget could be spent on unrelated cheap variants.

## Selection policy

- Known geometric obstructions rank before all machining preferences. A cheap
  analytic screen uses capsules *inside* straight cylinders to prove insufficient
  separation. It also checks stock walls and separated same-net cuts. Outer proxy
  capsules are not treated as exact cylinders or used to certify feasibility.
- The transient proposal performs no exact candidate validation. Automatic nets
  are traversed in stable ID order and a single repair sweep can reconsider a net
  selected earlier. Only exact OCCT validation grants PASS; source profile,
  connectivity, opening, closure and other checks retain their existing authority.
- Save & Validate and Optimize Routes share a conflict-directed neighbourhood.
  Exact failed-check items identify affected networks. Alternatives may move
  either network, with a bounded set of paired moves to escape a one-net local
  minimum. Cheap and low-obstruction alternatives both enter the pool.
- Detours include the existing one-step offsets and, when hard failures require
  further exploration, two-step offsets. Existing variant strings remain valid;
  the new `offset_z_m2` form records a reproducible double offset. Positions are
  still constrained by the stock bounds and all original validation rules.
- Exact ranking remains lexicographic: FAIL count, WARNING count, machining cost.
  An evaluated feasible route always beats an invalid one regardless of length,
  drilling count or plugs. On an exact PASS, proxy risk cannot displace a cheaper
  exact PASS. Failed alternatives remain in the saved evidence.
- Save uses at most six exact evaluations including baseline. Optimize uses its
  requested total budget (default six, maximum twelve). There is no nested exact
  route search. An automatic stored variant is reconsiderable; a frozen/manual
  route is preserved. The search is deterministic and bounded, not complete.

## Regression geometry and reproduction

`tests/fixtures/automatic-cross-net.json` contains four flat-ended custom test
ports in a 120 × 120 × 100 mm block, with automatic P and T networks and 8 mm
generated drillings. Opposing direct trunks cross at the block centre. An offset
trunk and two connecting drillings eliminate the intersection at greater length
and with extra plugs. These are test dimensions, not vendor-approved profiles.

`tests/test_routing_feasibility.py` verifies the invalid direct baseline, exact
collision volume elimination, connectivity of both nets, wall checks, higher
selected machining cost, all four priorities, reconsideration of the first net,
paired candidate availability, reversed net-list determinism, and explicit
optimization without saving the user project.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_routing_feasibility.py tests/test_review_followup.py tests/test_v1_engineering_views.py tests/test_store_api.py tests/test_product_projects.py tests/test_workflow.py -q
.venv/Scripts/python.exe -m manifold prove --out output/proof/routing-feasibility
```

The real project mentioned in the request was not attached as a readable file in
this task. This regression reproduces its described geometry class; it does not
claim verification of that unavailable project.

## Local verification (2026-09-12)

- The command above passed all 54 targeted routing, engineering, store/API and
  workflow tests. Four existing dependency deprecation warnings remain.
- The P/T direct baseline has 85 PASS / 3 FAIL. The selected build, including STEP
  round trip, has 137 PASS / 0 FAIL. Plug count increases from 0 to 3 and the
  machining score from 263.878603 to 861.878603. This score is not a monetary quote.
- Persisted evidence: `output/routing-feasibility-final/baseline-fail.json`,
  `output/routing-feasibility-final/selected-build/validation.json`, the selected
  `production.step`, and `output/routing-feasibility-final/summary.json`.
- The standard engineering proof retains the invalid case's 264 PASS / 6 FAIL
  and corrected case's 238 PASS / 0 FAIL under `output/proof/routing-feasibility`.
- No browser implementation changed. The prior preview queue and BRep viewer
  remain intact; the exact-preview regression confirms no full route search.
