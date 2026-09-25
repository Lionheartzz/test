# Exact CAD execution reliability on V2.3

Base: `2bb4aa1` (V2.3 Drawing Workspace and PMC26-3069 drawing layout). This change keeps the existing routing model, OCCT/BRep rules, source geometry and version 1 projects.

For the subsequent ordinary two-cavity/four-port movement reproduction, review cleanup fix, single-worker streamed preview and separation of completed engineering evidence from display failure, see [Interactive preview performance](INTERACTIVE_PREVIEW_PERFORMANCE.md).

## Findings and execution changes

The old API executed native CAD inside FastAPI's service process. A request thread is not isolation from an OCCT call that holds the Python GIL. Named/legacy builds and optimization also held the shared project lock throughout calculation. Save & Validate resolved exact candidates, then constructed and validated the selected candidate again. Drawing projection and generated-draft checks had additional in-process CAD paths.

All those service CAD paths now use one disposable worker process. Preview, exact preview, route adoption/refinement, build, optimization, generated-draft checking and drawing projection share this bounded executor. There is no unbounded CAD queue. A new preview replaces the preceding preview; an authoritative action terminates a preview before starting. A preview cannot replace an authoritative action. If another authoritative action is running, the request gets a concrete busy response. Project saving does not need this calculation lane.

The API snapshots input and checks the optimistic revision under a short project lock, releases the lock during CAD, and rechecks before publishing the result. A newer save wins; stale calculations cannot replace its design or build pointer. Interrupted build directories remain diagnostic evidence and are never published as a completed project build.

Windows workers use a kill-on-close Job Object, a 3 GiB process-tree memory limit, and below-normal scheduling priority. The actual interpreter is assigned while suspended, before executing Python/CAD. This matters for Store Python: the local venv/activation proxy was observed starting an interpreter outside the owning job. Direct interpreter startup retains the venv through [CPython's launcher contract](https://github.com/python/cpython/blob/3.11/PC/launcher.c). Worker descendants, CPU accounting and memory limits are consequently owned by the job. Non-Windows workers use an owned process group for termination; the Windows-specific memory/accounting implementation is not claimed for those platforms.

Every worker has a watchdog independent of browser polling. Defaults are 15 seconds for transient previews, 300 seconds for builds/optimization/drawing or generated-draft checks, 30 seconds for adoption and 60 seconds for refinement. The browser has a separate 20-second preview deadline and bounded authoritative requests. Cancellation, disconnect, timeout and native exit reclaim the worker. A nonzero native exit rejects even a result written before the crash. No failing engineering check is converted to a successful result.

Large preview JSON is serialized in the worker and returned verbatim by the API. Repeated framework traversal of mesh coordinates was another measurable event-loop stall: a 120-feature preview initially delayed the projects API by 1.77 seconds after CAD finished. Moving serialization and removing the redundant API traversal reduced the measured maximum to 0.016 seconds. A million-coordinate response is covered separately by regression.

The engine fingerprint still includes source, dependencies and executable bytecode. Marshal's reference-sharing format differed between a freshly compiled module and its cached equivalent; reference-free serialization makes those equivalent executables have the same identity. Changed executable code still changes the identity and fails the restart guard.

## Exact checks and UI behavior

**Validate** evaluates the current candidate exactly and retains its resolved design, constructed solids, authorized contacts and complete validation report. If feasible, it goes directly to STEP export/reimport and review generation. If infeasible, the existing bounded conflict-directed search remains available. The selected candidate's already computed solids/report are reused within that calculation only. Explicit Optimize Routes still performs its requested bounded search. There is no cross-draft validation cache or approximation replacing BRep authority.

Transient requests use immutable draft snapshots and increasing per-view versions. Client abort and explicit server invalidation stop superseded work, including a request that arrives after its cancellation. Failures retain the last usable view, expose the actual resolution/timeout reason and clear computing feedback. Same-project build/reload retains the camera. Hydraulic Nets keeps the chosen translucent stock context, including opacity zero; Solid, Machined void, Feature layers and explicit X-ray retain their existing semantics.

## Diagnostics

`GET /api/engineering/status` returns the active calculation and the last 12 outcomes. `output/cad-diagnostics/<id>.json` retains up to 100 timing records. These contain operation, worker PID, deadline, elapsed time, phase, completed operation counts/durations, exit/state/reason and Windows process-tree CPU/peak memory. They do not contain draft JSON or mesh contents.

Phases include `route.resolution`, `route.proposal`, `geometry.construction`, `boolean.cut/fuse/intersect/distance/clean`, `hydraulic.contacts`, `hydraulic.opening`, `hydraulic.net_geometry`, `hydraulic.cross_net_geometry`, `tessellation`, `validation`, `step.export`, `step.round_trip`, `review.generation`, `drawing.projection`, `result.serialization` and `worker.startup`. Timings are inclusive; nested phase durations must not be added as independent totals. Interrupted operations remain visible in the phase stack and elapsed job time, rather than being counted as completed checks.

A Windows reader can briefly lock a diagnostic file during its replacement. Such diagnostic write failures increment `diagnostic_write_errors` and do not abort engineering. Exceptions from the engineering check itself still propagate and reject the result; this distinction has a regression test.

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/engineering/status | ConvertTo-Json -Depth 8
.\.venv\Scripts\python.exe -m pytest tests/test_cad_execution.py -q -s
node --test --test-isolation=none tests/preview-queue.test.mjs
.\.venv\Scripts\python.exe -m manifold prove
```

## Measured evidence

The exact historical ten-minute hang was not reconstructed from a captured native stack. An equivalent CPU/GIL-monopolizing condition was deliberately reproduced in a real disposable process, and two existing saved projects were exercised without modifying their source files. Measurements are local Windows samples, not timing guarantees for every manifold.

- [Slow-worker / build evidence](evidence/cad-slow-worker-profile.json): a worker consumed about 0.59 CPU seconds in 0.6 seconds while health/projects/save remained available. Save & Validate preempted it and completed a feasible automatic route in about 3.9 seconds. Construction, validation, STEP export, STEP round trip and review generation each ran once; the route-selection evidence contains one exact attempt. Build includes startup overhead.
- [Existing-project preview evidence](evidence/cad-preview-profile.json): 3 features / 2 automatic nets returned exact preview in 4.68 seconds; 120 features returned in 10.06 seconds. For the larger model, 46 concurrent probes measured health at at most 0.0047 seconds and projects at at most 0.016 seconds; saving took 0.0095 seconds. It built once and tessellated 122 parts, with no exact route-selection validation or STEP work in transient preview. Its 6.01-second tessellation cost is explicitly visible.
- `tests/test_cad_execution.py` covers active CPU/GIL work, health/projects/save, authoritative preemption, stale request/cancellation ordering, orphan watchdog cleanup, native crash after writing a result, subsequent recovery, stale commit rejection, cold/warm engine identity, optimization, cancellation of drawing calculation and large JSON transfer.
- `tests/preview-queue.test.mjs` covers successive edits, immutable coalescing, obsolete results, abort, timeout, retention and recovery. Existing V1 exact routing/sizing/refinement and V2.3 drawing regressions remain in the suite.
- Browser interaction in `tests/cad-reliability.run.js` deliberately held an exact response beyond the client deadline, verified error feedback and usable controls, recovered after successive edits, and completed a PASS build. Screenshots at `output/playwright/cad-timeout-retained.png` and `cad-recovered-build.png` were visually checked: stock opacity 37%, Hydraulic Nets mode, and the front camera remained consistent after the camera fix. The existing sizing/refinement browser regression was also run.

Transient diagnostic files are now an intentional side effect. Tests continue to prohibit transient writes to project, build, route-selection and optimization evidence. Exact circuit/wall/opening checks and the actual STEP round trip were not weakened. PASS remains limited to the documented engineering rules and is not manufacturing or pressure certification.

Final verification: the complete Python suite passed **244 tests** in 550.94 seconds (`output/reliability-verified-tests.xml`). The preview queue and route alignment JavaScript checks passed **10 tests**, and the production frontend build completed. The exact proof at `output/proof/20260914-195654` retained the invalid case with 6 failures and passed the corrected case with 238 passes / 0 failures, including STEP evidence.
