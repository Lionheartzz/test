# Explicit construction-closure v8 deployment

Git carries the code, tests and `data/migrations/construction-closures-v8.json`.
It does **not** carry the active SQLite database. `git pull` alone does not install
this release's engineering data. Startup validates the database; it never migrates it.

The checked-in bundle contains the accepted normalized runtime additions, including
the source contour parameters needed by geometry. It is not an MDB, PDF, raw audit,
or a second runtime database. No source research or plug-family regeneration is
performed during deployment or normal routing.

## Another machine with the current v7 engineering database

Run from that machine's Manifold checkout. Keep its existing database and projects.
Use the release code before these commands. The source must be schema v7; the
command refuses existing output files and conflicting IDs or source interfaces.

```powershell
$taskDeployment = 'output/closure-v8-deployment'
New-Item -ItemType Directory -Path $taskDeployment -Force | Out-Null
.\.venv\Scripts\python.exe -m manifold.activate_closure_v8 stage `
  --source data/pmc_engineering.db `
  --output data/pmc_engineering.closure-v8.staging.db `
  --report output/closure-v8-deployment/staging.json
```

This clones the local v7 database and transactionally adds the accepted profiles,
optional products/mappings, threads and tools. It expands only the tooling CHECK
to support FORM PORT/TAP, retains named indexes, checks all foreign keys/integrity,
preserves every existing row, and compares logical hashes of unrelated tables.
Custom data is retained. A changed dependency is an explicit conflict requiring
review, never an excuse to overwrite the local library.

Inspect the staging report and verify it with the release checks. The ordinary
baseline has 103 usable definitions, 45 products, 73 mappings and 24 aliases;
local custom additions can increase counts. Manufacturer SKU remains optional.

```powershell
$env:PMC_ENGINEERING_DB = (Resolve-Path data/pmc_engineering.closure-v8.staging.db).Path
.\.venv\Scripts\python.exe -m pytest tests/test_closure_v8_integration.py tests/test_r1_closure_coverage.py -q
$env:PMC_ENGINEERING_DB = $null
```

Stop **all** Manifold backend/engineering workers before the next command.
`--server-stopped` records the operator's explicit confirmation; it is not a
process-discovery or service-stopping command. Use a new backup filename.

```powershell
$taskCandidateHash = (Get-Content output/closure-v8-deployment/staging.json -Raw | ConvertFrom-Json).candidate_sha256
.\.venv\Scripts\python.exe -m manifold.activate_closure_v8 activate `
  --candidate data/pmc_engineering.closure-v8.staging.db `
  --sha256 $taskCandidateHash `
  --backup output/closure-v8-deployment/pmc_engineering.pre-v8.db `
  --report output/closure-v8-deployment/activation.json `
  --server-stopped
```

Activation independently rechecks preservation, verifies the accepted candidate
SHA and the backup, checks exclusive SQLite access, and atomically replaces
`data/pmc_engineering.db` with verified candidate bytes. It refuses journal/WAL
files; checkpoint and stop the writer explicitly first. The production path does
not change. The original backup and staging candidate remain intact.

A rebuilt database may have a different **file** SHA due to SQLite page layout.
Use the verified staging report's SHA for that machine, not this workstation's
original candidate SHA. Runtime rows and protected table hashes must match.

Rebuild the frontend and restart normally without a staging environment override:

```powershell
npm.cmd run build
$env:PMC_ENGINEERING_DB = $null
.\.venv\Scripts\python.exe -m manifold serve
```

Check `/api/health`, Engineering Library, an existing project, manual selection
Save/Reload/Validate, and production STEP. The active DB is read by all ordinary
runtime APIs. Do not rerun `stage` against v8 as an in-place upsert.

## Transfer of an already accepted candidate

Alternatively, transfer the candidate SQLite file outside Git and use `activate`
with its independently verified SHA and a fresh backup path. The same complete
preservation checks apply; unrelated differences cause rejection. Prefer the
bundle workflow when the other machine has additional custom definitions.

## Scope and recovery

Ø76/Ø89 high-flow accesses are known unsupported closures: they remain unresolved,
WARN and not manufacturing-ready. Routing is not artificially capped. This release
does not claim universal closure or product pressure qualification.

Keep the activation report and v7 backup. Recovery must happen with services
stopped and account for projects that have since selected new v8 closure IDs;
blindly restoring v7 after such edits would leave those references unavailable.
There is no automatic rollback or startup repair.
