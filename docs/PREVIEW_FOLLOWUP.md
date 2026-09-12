# Preview follow-up after 8df9f68

Verified 2026-09-12. This supersedes the earlier preview scheduling and stock-context behavior described in the V1 acceptance record.

## Behavior

- Transient exact preview and draft refinement resolve the current route proposal without the bounded candidate search. Exact preview still builds OCCT cuts, machining voids, same-net unions and separate cross-net collision geometry. Its status explicitly says **current proposal, not validated / not optimized**. Save & Validate and explicit optimization retain their search behavior.
- One queue owns fast and exact requests. It captures an immutable draft snapshot, debounces edits for 350 ms, and waits another 450 ms after fast resolution before starting exact geometry. New edits replace queued work. In-flight responses cannot update a newer draft or project. Drag gestures defer preview requests until release. Repeated inspection of an unchanged draft reuses its exact result.
- The queue does not abort a fetch and immediately start more CAD work: disconnecting a request would not cancel the server's OCCT computation. The next request waits for the current request to finish.
- Current failures display their actual field-validation or resolution reason, clear the loading overlay and restore the last usable view. Obsolete failures are ignored. Successful editing resumes the pipeline.
- Hydraulic Nets shows the real production solid as translucent context, using **Stock opacity** (default 22%, zero for network-only inspection). Solid remains opaque; Machined void, Feature layers and explicit X-ray retain their meanings. Model replacement preserves camera, view mode, opacity and circuit visibility.

## Evidence

- Backend/API/geometry/project tests: **30 passed**; workflow/routing tests: **16 passed**. Logs: `output/preview-followup-tests.log`, `output/preview-followup-routing-tests.log`.
- Queue tests: **3 passed**, covering immutable snapshots, burst coalescing, obsolete 422 responses, edits during in-flight CAD, cancellation and cache reuse.
- Real application test: three rapid property edits produced exactly **one fast request and one exact request**. A held obsolete 422 did not launch concurrent work or replace newer results. A real `block.length` validation error preserved the last view and cleared loading; valid input recovered. Stock opacity 37%, zero and Solid's opaque state were exercised.
- Six real-browser BRep fixtures verify translucent stock context, zero opacity, stable camera/mode/circuit visibility and the prior exact topology/tip/collision checks. Continuous-drag browser regression also passed.
- `python -m manifold prove --out output/proof/preview-followup-final`: invalid fixture **264 PASS / 6 FAIL**, corrected fixture **238 PASS / 0 WARNING / 0 FAIL**, including STEP round trip. Both immutable results retained.
- Frontend production build and whitespace checks passed. The existing Vite large-chunk advisory remains.

## Reproduce

```powershell
node --test tests/preview-queue.test.mjs
.venv/Scripts/python.exe -m pytest tests/test_v1_engineering_views.py tests/test_store_api.py tests/test_product_projects.py tests/test_workflow.py tests/test_review_followup.py -q
.venv/Scripts/python.exe scripts/export-v1-view-fixtures.py
node scripts/check-engineering-views.mjs
node scripts/check-viewer-lifecycle.mjs
npm run build
# With this checkout running locally on 127.0.0.1:8765:
node scripts/check-preview-followup.mjs
```

The application regression creates a separate local QA project; it does not edit an existing user project. Its two deliberate HTTP 422 responses are expected browser console entries, not unexplained failures.
