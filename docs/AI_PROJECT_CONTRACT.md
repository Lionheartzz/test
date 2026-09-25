# AI / engineer editable project contract

The deliverable is a schema-version-2 `.pmc.json` project that opens in PMC Manifold Studio for further editing. STEP is produced later by exact validation.

1. Obtain the current schema from `GET /api/project-schema`. Use `POST /api/check-design` to normalize without saving and `POST /api/import-project` to inspect a draft.
2. Store project state only: block, rules, constraints, cavity placements, optional `cartridge_id`, `interface_nets`, external ports, nets, routes, optional schematic intent and review items that represent real unresolved work.
3. Reference cavities, cartridges and external-port definitions by SQLite ID. Do not embed full engineering definitions or invent a compatibility relationship.
4. Keep `cartridge_id=null` valid. When no schematic intent exists, set `schematic_intent=null` and create no schematic components.
5. Every external port and cavity interface belongs to one named hydraulic net. Physical cutting geometry remains distinct from installed hydraulic interfaces and schematic intent.
6. Record `origin.method`, provider, model, author and notes truthfully when they are useful operational metadata. Do not persist a claim/evidence/provenance graph in the project.
7. Represent truly unresolved project decisions as `review_items`. A cavity-only placement is not itself an unresolved decision.
8. **Save Project** persists in-progress work without requiring PASS. **Validate** creates an immutable exact build. Retain failures and never weaken an engineering rule to obtain PASS.
9. Geometry PASS is not pressure, vendor or manufacturing certification.

AI Design uses this same contract. It queries the backend SQLite library and creates schematic components only when its input contains actual schematic intent.
