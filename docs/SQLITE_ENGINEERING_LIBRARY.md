# SQLite engineering library

PMC Manifold Studio reads engineering definitions only from SQLite. The default runtime file is `data/pmc_engineering.db`; set `PMC_ENGINEERING_DB` to use another absolute or application-relative deployment path.

Initialization is an explicit operator action:

```powershell
.\.venv\Scripts\python.exe -m manifold.import_mdtools `
  --source PMC_MDTools_Library\PMC_MDTools_Master_Library_2026R2_Merged `
  --output data\pmc_engineering.db
```

The output path must not already exist. The command reports cavity, external-port, Cartridge, compatibility, rejected, unusable and footprint-composition counts. Zero active footprints alone does not make a cavity unusable; the importer evaluates the cavity's own executable cutting data.

Application startup only validates the configured database. It never creates a database, scans either MDTools JSON directory, imports source data, repairs from backups or creates an empty replacement. A missing or invalid database stops startup with an actionable error.

Saved schema-1 projects are converted explicitly after the database import:

```powershell
.\.venv\Scripts\python.exe -m manifold.migrate_saved_projects `
  --staging projects\migration-staging `
  --backup projects\legacy-backup\schema1 `
  --install
```

The converter maps identical executable definitions to existing IDs and inserts materially different project geometry as stable `legacy_*` definitions. It removes embedded definitions and guided-template schematic placeholders. Backups are never runtime sources.
