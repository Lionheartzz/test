# Main Station Library injection on REV2

This is an explicit, non-executable research import. The source is the approved
schema-v5 REV2 relationship staging database, never schema-v4 production.
Production activation is a separate task.

```powershell
.venv\Scripts\python.exe -m manifold.import_library_knowledge `
  --source data/pmc_engineering.rev2_relation.db `
  --package PMC_MDTools_Library/PMC_Manifold_All_Useful_Knowledge_Main_Station_Handoff_2026-10-06.zip `
  --output data/pmc_engineering.rev2_relation_plus_lib.db `
  --report output/main-station-lib/import-delivery.json
```

The command refuses existing outputs and checks the reviewed source SHA by
default. It reads ZIP members without extraction, validates CRC and each consumed
structured member against the top-level manifest. Dataset/source-map disagreement,
malformed records, unsupported status upgrades, or protected-table changes abort
the import and remove only its exclusively created staging target.

Schema v6 adds `library_*` tables. It does not replace v5 runtime tables or the
specialized `technical_*` model. Runtime validation recognizes existing v5 and
combined v6; it never creates or migrates either. The existing explicit MDTools
and technical import commands retain their v5 contract.

The formal baseline supplies targets. Only designated Closure REV04, Port REV03,
and Thread RUN01 dispositions can change their research states. All referenced
evidence must resolve before an increment can claim VERIFIED. Both `|` and `;`
are supported as native evidence-ID separators. The proposed queue checks the
computed result; it cannot authorize an upgrade. Accepted Seal REV04 is audit-only
because baseline already contains it. Historical/legacy rows cannot override
current rows.

Every selected structured row is stored in `library_records`. Exact file hashes
deduplicate datasets and preserve aliases. Evidence/source canonical views use
domain baseline, then the unified baseline view, then designated increments.
Differing same-ID payloads remain in `library_conflicts` with dataset provenance;
all source rows remain inspectable. These are record-version discrepancies, not
automatic judgments about contradictory engineering facts. Native research
conflict/unresolved tables and field findings remain ordinary structured records.
No names are matched to runtime execution definitions by similarity.

`manifold.library_knowledge.browse()` and `detail()` provide read-only, paginated
research access to targets, evidence, sources, gates, findings and archive path
references. This phase adds no UI or HTTP endpoint. It grants no Place/Bind/Use
permission and makes no kernel integration change.

CAD target rows are excluded from the active denominator. No CAD or document bytes
are extracted or stored. Source path aliases, file hashes and sizes are metadata
only; documents and the input ZIP are not runtime dependencies.

Every pre-existing source table is hashed before/after import. Independent outputs
must have identical logical table hashes except `library_import_batches`, whose
report records each output path. Keep the original v5 source and production DB
untouched; do not change launcher configuration.
