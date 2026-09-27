# SQLite engineering library

PMC Manifold Studio reads engineering definitions only from SQLite. The default runtime file is `data/pmc_engineering.db`; set `PMC_ENGINEERING_DB` to use another absolute or application-relative deployment path.

Initialization is an explicit operator action. Schema v3 includes KB evidence and
keeps the existing Cartridge compatibility table as the execution allowlist:

```powershell
.\.venv\Scripts\python.exe -m manifold.import_mdtools `
  --source PMC_MDTools_Library\PMC_MDTools_Master_Library_2026R2_Merged `
  --knowledge-package "$env:USERPROFILE\Desktop\KB_REV1_2026-09-26.zip" `
  --output data\pmc_engineering.rev1.db `
  --preserve-custom-from data\pmc_engineering.db
```

The output path must not already exist. The v2 database passed to
`--preserve-custom-from` is opened read-only; custom and legacy definitions are
copied into the new v3 artifact. The command reports cavity, external-port,
Cartridge, compatibility, evidence, unresolved and policy-hold counts. Zero active
footprints alone does not make a cavity unusable; the importer evaluates the
cavity's own executable cutting data. A KB package is optional for small MDTools
test fixtures, but a production v3 database should be built with the package.

Test the staged database by setting `PMC_ENGINEERING_DB` for the process, for
example `$env:PMC_ENGINEERING_DB='data/pmc_engineering.rev1.db'`. Do not replace
the active database during staging. A v2 database is deliberately rejected by
v3 application startup; startup does not migrate or reimport it. The KB evidence
endpoints are read-only. Automatic AI and design compatibility continue to use
only `cartridge_cavities.valid=1`; evidence-only records do not grant compatibility.

Application startup only validates the configured database. It never creates a database, scans either MDTools JSON directory, imports source data, repairs from backups or creates an empty replacement. A missing or invalid database stops startup with an actionable error.

Saved schema-1 projects are converted explicitly after the database import:

```powershell
.\.venv\Scripts\python.exe -m manifold.migrate_saved_projects `
  --staging projects\migration-staging `
  --backup projects\legacy-backup\schema1 `
  --install
```

The converter maps identical executable definitions to existing IDs and inserts materially different project geometry as stable `legacy_*` definitions. It removes embedded definitions and guided-template schematic placeholders. Backups are never runtime sources.
