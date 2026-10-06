# REV2 relationship replacement

The relation package and the cartridge/material technical package are separate inputs. REV2 replaces all active imported Cartridge↔Cavity evidence and its derived execution pairs in a new database clone. It does not rebuild MDTools geometry or technical research, delete classified master identities, infer specifications, or change projects.

Schema v5 adds logical/physical supplemental cavity identities, reference links, the pending audit registry and relation migration history. Supplemental identities have no runtime geometry and all placement/machining/routing/tooling flags remain false. An explicit future promotion must match logical identity and native unit to validated authoritative runtime geometry; startup never performs promotion or re-resolution.

Only the authoritative `cartridge_cavity_relations.csv` creates relations. `CONFIRMED`, confidence ≥ 0.85 and complete resolution to runtime cavities are required for imported execution compatibility. Geometry usability remains a separate execution check. Pending records, classification/denominator accounting and other `kb_relations.csv` relation types cannot change compatibility. The technical importer requires its target set to be a subset of runtime Cartridge identities; extra relationship-only identities receive no invented technical rows.

Run an explicit read-only preflight:

```powershell
.venv\Scripts\python.exe -m manifold.replace_relation_knowledge `
  --source data\pmc_engineering.db `
  --knowledge-package 'C:\Users\Zhou Ke\Desktop\KB_REV2_2026-10-05.zip' `
  --rev1-package PMC_MDTools_Library\KB_REV1_2026-09-26.zip `
  --report-dir .
```

For a replacement, add `--output data\pmc_engineering.rev2_relation.db` and `--report output\rev2-relation\import-a.json`. An existing output is refused. The command checks the input archive, writes the JSON/Markdown preflight before staging mutation, backs up the read-only source, replaces the active graph transactionally, compares preserved tables and old Cartridge rows, and checks integrity/FKs. Failure removes only the new incomplete clone. Repeat into another fresh output and compare logical sets; imported timestamps may make file hashes differ.

Runtime startup remains validation-only and requires schema v5. The preserved schema v4 production database is not automatically upgraded; after deployment of this code it requires an owner-approved promotion before normal default startup. Acceptance uses a process-scoped `PMC_ENGINEERING_DB` pointing at staging. Launchers are unchanged.

Read-only additions:

- Existing relationship queries include `supplemental_cavities`, independently of `resolved_cavities` and execution eligibility.
- `/api/knowledge/cavity-supplements?q=&offset=&limit=` lists supplemental identities with false execution flags.
- `/api/knowledge/pending-registry?q=&status=&offset=&limit=` lists audit records with their raw and query-normalized status.
- Technical summaries return `technical_record_present=false` for a real Cartridge lacking a technical row. Unknown Cartridge identities remain errors.

Engineering Library Cartridge detail shows compatibility, relationship evidence and the optional technical record in the existing Library. It never offers an execution action based on evidence-only or supplemental identities.

Final SQLite file SHA-256 is recorded in the external import report. A SQLite database cannot contain its own final file hash; the batch records its source hash and migration provenance instead.
