# MDTools source relationship and envelope audit

## Scope — 2026-09-09

The historical converted-library inventory and raw export were produced by **direct ODBC extraction of the original MDB snapshot**. The original `.mdb` / `.accdb` files are **not currently present in the supplied repository/runtime**. The import manifest points to `PMC_MDTools_Library/MDTools Library`, but that directory currently contains importer scripts and documentation only. A new direct audit cannot be rerun until the original database files are available; this does not mean the historical databases were never inspected.

The available historical extraction was inspected separately: `reports/inventory.json` and the complete raw table JSONL files, rather than only normalized PMC cavity records. The inventory covers **8 databases, 367 tables and 9,969 rows**, extracted on 2026-09-08. Evidence: `output/mdtools-export-audit-v6.json`. The report explicitly labels its mode `historical-raw-export-only`; recorded MDB SHA values are historical identities, not current file verification.

## What the available extraction establishes

- No dedicated cartridge/valve model or manufacturer part-number relationship fields were found in the exported cavity/footprint schemas. Cavity names and library/OEM group names are not treated as compatible cartridge identities.
- `CavityIndex` / footprint parent references establish cavity-to-footprint relationships. They do not establish valve-to-cavity compatibility.
- Both plug databases expose `ConPlugTable.PlugModel`, but there are no nonempty model values in the available extraction. A plug model field would not establish cartridge compatibility in any case.
- The two assembly-envelope tables contain zero Inch records and three Metric records. Their columns are envelope ID, name, raw dimensions and, in the Metric table, shape type. No explicit cavity ID or valve part number is present in those exported tables.

These findings justify leaving imported cartridge compatibility unknown. They **do not prove that every original MDB version lacks such relationships**, nor do they replace inspection of original database metadata and values. No relationships have been inferred from geometry, similar names or catalog colors.

## Boundary meaning and implemented treatment

| Source evidence | Preserved meaning | PMC treatment |
|---|---|---|
| Footprint record `EnvelopDimensions` | Envelope linked to a footprint record | Preserve footprint source role, raw dimensions, type and SHA; map supported planar geometry without inventing a valve height |
| Independent `AssemblyEnvelope` row | Independent assembly envelope | Keep separate; no automatic association by name |
| `Custom`, `Circle`, or missing shape type | Shape classification only | Preserve verbatim; never translate it automatically into body/service/tool meaning |
| Closed `L` segment loop | Polygon outline | Exact planar face or explicitly declared extrusion |
| Explicit `Circle` with a verified four-quarter-arc loop | Full circle outline | Exact circular wire/face; browser sampling is display only |
| Other arc/mixed syntax | Unresolved source geometry | Preserve raw data; refuse automatic boundary assignment that would guess geometry |

An engineer can explicitly associate an independent envelope with a selected project cavity and choose mounting footprint, external body, service or tool role, height and a written decision. The association is marked `engineer-selected`; the original record is pinned separately as an engineering resource. Height zero remains a planar region. No default external body or service height is inferred from the envelope name or shape type.

## Finish the original-database audit

Once the original files are available, use a Python environment with `pyodbc` and the Microsoft Access ODBC driver:

```powershell
python scripts/audit-mdtools-source.py --source 'D:\path\to\original MDBs' --out output/mdtools-original-audit.json
```

The script uses `ReadOnly=1`, SELECT statements and ODBC metadata calls; verifies each source SHA-256 before and after closing; records driver limitations on foreign-key metadata; and refuses to write its report inside the source directory or overwrite prior audit evidence. Its original-database mode has not been run here because the files are unavailable. Review candidate fields and actual links before promoting any relationship to documented compatibility.
