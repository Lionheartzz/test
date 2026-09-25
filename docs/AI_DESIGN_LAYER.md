# AI Design: schematic or requirements to an editable project

AI Design uses the same SQLite engineering database as the rest of PMC Manifold Studio. It may interpret an explicit schematic or a cavity-layout request, but it never creates cavity geometry or cartridge compatibility from model-name similarity.

## Runtime contract

- Library lookup reads `pmc_engineering.db` through the backend.
- Generated placements store `cavity_id` and optional `cartridge_id`; full engineering definitions are not copied into the project.
- Cartridge assignment is accepted only when the explicit SQLite many-to-many relationship is valid.
- A schematic component is created only when the input contains schematic intent. A cavity-layout request without intent produces placements, nets and ports with `schematic_intent=null`.
- Geometry, routing, wall, connectivity and STEP checks remain deterministic PMC operations.
- Provider interpretation objects may exist during one analysis run. The saved analysis and generated project retain only normalized operational input, selected IDs, unresolved items, job state, errors and performance diagnostics. They do not persist a claim/evidence/lineage graph.

## Provider and document boundary

Provider settings are stored locally in ignored `.pmc-local/ai-provider.json`. No endpoint, model or credential is preset. Selected documents and requirements are sent only to the configured provider when the user runs analysis. CAD, SQLite and saved projects stay local.

PDF/PNG/JPEG admission, bounded page rendering, cancellation, timeout handling and credential protection remain in force. Production exposes no mock-provider fallback; deterministic provider fixtures are test-only.

## Generation

1. Normalize the current request and any explicit schematic intent.
2. Resolve cavity, cartridge and external-port IDs from SQLite.
3. Stop with a clear unresolved item when identity, compatibility or interface mapping is ambiguous.
4. Generate a schema-2 project containing project state and engineering IDs.
5. Run bounded placement/routing candidates through the existing exact CAD and validation pipeline.
6. Open the chosen result as an ordinary editable draft. **Save Project** and **Validate** use the normal project workflow.

The result may still contain engineering failures or warnings and remains a Draft until the usual exact validation passes. Unsupported requirements remain visible; the generator does not infer vendor geometry, pressure certification or hydraulic-window numbering.

## Persistence

- Analyses: ignored `projects/ai-design/<id>.json`.
- Operational run output: ignored `output/ai-design/<id>/` and `output/ai-jobs/`.
- Generated projects: normal schema-2 records under `projects/saved/` after an explicit save.

The compact saved records are for current workflow recovery and diagnostics. They are not an engineering master or an audit reconstruction system.
