# Authoritative Validate progress

Baseline: `56a5489189d990b69065652a53c326c21a90c955`, branch `codex/sqlite-domain-reset`.

## Progress transport and UI

- The existing Executor and `timing.py` trace remain authoritative. A small read-only `GET /api/engineering/progress/{operation_id}?project_id=...` projects that trace into user stages. `/api/build` accepts and returns the client-generated secure operation ID; status must match both operation and project.
- Browser polls serially every 400 ms (observed median 406 ms). Trace publishing remains bounded at 150 ms; only a few actual milestone events were added, with no per-Boolean forced writes or extra CAD work.
- Compact progress sits between the existing status strip and Validation Results. It shows a native progress bar, current stage, candidate number, elapsed time and conservative ETA. Duplicate Validate is blocked. No modal or Cancel button was added.
- Percent follows actual milestones: setup 0–8; bounded exact-candidate slots 15–75; STEP 85/93; artifact/display/final serialization 95–99. Retries retain the high-water mark. 100 requires the completed authoritative response after the project commit; a worker finishing alone is insufficient.
- Current stages: Preparing design; Resolving automatic routes; Checking automatic route candidate; Building exact geometry; Checking engineering rules; Checking production topology; Trying alternate automatic route; Comparing automatic routes; Verifying production STEP; Finalizing validation; Validation complete. Raw internal phase paths remain in developer diagnostics only.
- Preview/preview-solid/refine have no Validate progress UI. Stale operation/project/scope replies are ignored. Navigation cannot apply the old result to another project; errors end progress and restore the existing controls. Completion collapses after 1.2 s.

## ETA

Session history contains at most six successful owned runs, each with at most 32 milestone timestamps. ETA needs two runs matching project, normalized design revision and engine revision. It estimates the remaining duration of the matching stage/candidate from those actual timings, takes the conservative maximum with 20% headroom and rounds up to 5 s. Missing/new candidate history or a run substantially exceeding its history returns Estimating rather than a false countdown. Elapsed time never drives the percentage.

## Real acceptance

Real project: `6e57fdcccb174b87a72c32f3069bb285`, localhost production service. Three final-code Validate runs: 49.235 s, 46.313 s, 46.703 s. The first two had no ETA; the third displayed an ETA learned from those real completed runs.

Observed flow: Preparing design → Resolving automatic routes → candidate 1 / exact geometry / engineering rules / topology → Trying alternate automatic route → candidate 2 / exact geometry / engineering rules / topology → Comparing automatic routes → Verifying production STEP → Finalizing validation → 100% / Validation complete.

Every run evaluated 2 exact candidates and retained **450 PASS / 12 WARNING / 0 FAIL**. Selected route variants, valid single-solid production BRep, STEP gate and all validation rules are unchanged. Final build: `71b36a3a724f444ebbcfdf6be9429a51`. No transient candidate FAIL was displayed. Duplicate clicks submitted one build per run; the browser remained responsive; simulated browser transport failure restored Validate and hid progress. Page errors: 0.

Screenshots: [candidate 2 and learned ETA](output/playwright/validate-progress/run-3-candidate-2.png), [real production STEP stage](output/playwright/validate-progress/run-3-step.png), [final unchanged validation](output/playwright/validate-progress/run-3-complete.png). Raw owned status and UI samples: `output/validate-progress/browser-result.json`.

## Focused verification

- 17 focused Python tests passed: 7 progress/ownership/timeout tests, 8 store/API tests, one streamed-preview separation test and the real CAD-safe fixture. Final stage/transport subset: 15 passed.
- 17 relevant JavaScript tests passed: progress lifecycle/ETA/stale/error behavior plus existing preview queue/stream checks; existing Validation Results assertions also passed. Vite build and `git diff --check` passed.
- One additional existing native-CAD test still fails its last geometry-count assertion (`3` expected, `2` actual). It failed identically in a read-only archive of starting HEAD `56a5489`: `tests/test_cad_execution.py::test_slow_preview_does_not_block_apis_save_or_exact_build`. Its responsiveness, save, exact build and process cleanup checks preceding that assertion passed. The assertion was not edited or xfailed; no new regression was introduced. Evidence: `output/validate-progress/baseline-test.log`.
- No broad audit, schema/material/geometry/routing-policy changes. Production SQLite SHA-256 remains `4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`.

Implementation: `manifold/timing.py`, `validation_progress.py`, `engineering.py`, `server.py`, trace milestones in `routing.py`/`store.py`/`cad_worker.py`; `web/validate-progress.js`, its small stylesheet, `web/main.js` and one Studio markup insertion in `index.html`. Focused tests and this report accompany the change. Commit SHA, remote HEAD and clean working tree are confirmed after push.
