# SQLite engineering library

PMC Manifold Studio reads engineering definitions only from SQLite. The default runtime file is `data/pmc_engineering.db`; set `PMC_ENGINEERING_DB` to use another absolute or application-relative deployment path.

Initialization is an explicit operator action. Current schema v4 includes REV1 relationship evidence and REV2 technical knowledge, and
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
copied into the new v4 artifact. Read-only v3/v4 custom sources are also accepted. The command reports cavity, external-port,
Cartridge, compatibility, evidence, unresolved and policy-hold counts. Zero active
footprints alone does not make a cavity unusable; the importer evaluates the
cavity's own executable cutting data. A KB package is optional for small MDTools
test fixtures, but an engineering baseline should be built with the REV1 package.

Test the staged database by setting `PMC_ENGINEERING_DB` for the process, for
example `$env:PMC_ENGINEERING_DB='data/pmc_engineering.rev1.db'`. Do not replace
the active database during staging. A v2/v3 database is deliberately rejected by
v4 application startup; startup does not migrate or reimport it. The KB evidence
endpoints are read-only. Automatic AI and design compatibility continue to use
only `cartridge_cavities.valid=1`; evidence-only records do not grant compatibility.

REV2 integration copies an existing v3 engineering database to a **new** staging
file, then explicitly creates v4 technical tables. A freshly initialized v4
engineering baseline with entirely empty technical tables is also accepted.
An existing output or already populated technical source is rejected.

```powershell
.\.venv\Scripts\python.exe -m manifold.import_technical_knowledge `
  --source data\pmc_engineering.db `
  --knowledge-package PMC_MDTools_Library\PMC_Manifold_Global_Cartridge_Technical_Handoff_2026-10-01.zip `
  --relationship-package PMC_MDTools_Library\KB_REV1_2026-09-26.zip `
  --output data\pmc_engineering.rev2.db `
  --report output\rev2-import.json
```

Omit `--output` for read-only package/baseline validation. Every supplied manifest
file hash, source/evidence/conflict reference and target disposition is checked
before output creation. All previous engineering domain tables are compared
byte-for-byte as sorted logical rows before/after import. The production database
and all compatibility eligibility flags remain unchanged.

The normalized `technical_*` tables share a domain key for Cartridge and Material
research. Identities reference existing Cartridge IDs; research material IDs stay
separate from executable `materials`/`material_stock`. Source records are
deduplicated by their declared IDs and aliases. Shared/base-model evidence uses
explicit identity links with visible scope. Independent dataset observations,
original scopes, raw values and field-gap outcomes remain available. Source-review
and identity evidence never become technical parameter values. Conflicts preserve
both linked sides and the supplied resolution; no preferred winner is inferred
from prose. Supplier records use complete-record stable keys where an exported ID
collides across thicknesses, preserving original IDs and every source row.

Read-only API paths are `/api/cartridges/{id}/technical`, `/technical/evidence`
and `/technical/conflicts`, and `/api/materials/technical/{id}` with `/evidence`,
`/conflicts` and `/stock`. Evidence and conflict lists paginate. The existing
`/api/materials` remains the executable material/stock catalog. Engineering Library
adds separate research-grade cards. Technical search is opt-in for the Library API;
existing AI identity search and compatible/logical-cavity queries keep their prior
semantics. No routing/design consumer reads the new technical values.

For acceptance, set `PMC_ENGINEERING_DB` only on the test/server process to the
staging path. Production promotion and launcher default changes are separate work.

Application startup only validates the configured database. It never creates a database, scans either MDTools JSON directory, imports source data, repairs from backups or creates an empty replacement. A missing or invalid database stops startup with an actionable error.

Saved schema-1 projects are converted explicitly after the database import:

```powershell
.\.venv\Scripts\python.exe -m manifold.migrate_saved_projects `
  --staging projects\migration-staging `
  --backup projects\legacy-backup\schema1 `
  --install
```

The converter maps identical executable definitions to existing IDs and inserts materially different project geometry as stable `legacy_*` definitions. It removes embedded definitions and guided-template schematic placeholders. Backups are never runtime sources.
