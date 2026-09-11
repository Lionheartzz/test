# AI / engineer editable project contract

The deliverable is a schema-version-1 `.pmc.json` project that opens in PMC for further editing. STEP is an optional downstream artifact of exact validation. Any provider can produce this format; the local app currently makes no AI calls.

1. Start with the current exported project or supplied handoff snapshot. Obtain the actual schema at `GET /api/project-schema`. Preserve unrelated fields, existing engineering IDs and complete pinned library definitions. Use `POST /api/check-design` to normalize without saving, and `POST /api/import-project` to inspect the draft and missing local assets.
2. Read supplied schematic assets and preserve their SHA-256 identities. Record `origin.method`, `provider`, `model`, `author` and notes truthfully. Do not invent a provider, manufacturer, approved drawing or confirmed dimension.
3. Provide a useful editable draft when some information is missing. Represent unresolved choices as `review_items` with `id`, `kind`, `subject`, `description`, `proposed_value`, `severity`, `status: open`, and empty `resolution`. Use `blocking` for an unresolved premise that invalidates engineering use. Mark uncertain schematic components `unconfirmed`. Explain provisional dimensions explicitly; never derive a bore diameter from a nominal flange size without evidence.
4. Model intent with named `nets`, placed cavity `features`, exact `circuits` interface IDs, and schematic `components`. Every external port and installed hydraulic interface belongs to exactly one net. Physical cutting bores are distinct from installed cartridge interfaces. Colors and tessellations carry no engineering authority.
5. Query the same native catalog through `GET /api/catalog` with `q`, `unit`, `kind`, `manufacturer`, `cavity_type`, `thread`, `offset`, and `limit`. Fetch `GET /api/catalog/definition?id=...` and pin the complete returned definition. Keep source IDs, native units, source hashes, raw expressions and separate related footprint records. Do not flatten native cavities to guessed generic stages or silently replace an existing pin with a catalog head.
6. Source Metric / Inch values remain in `native.record`; internal stages, cuts and coordinates are mm. Native geometry and machining statuses are independent. Never set imported geometry or machining to reviewed merely because JSON parses. Engineer-mapped geometry and engineer-reviewed machining require explicit decisions. Unresolved `$STEP*` operands remain expressions and do not imply executable tooling.
7. Use normal editor operations after import. Review decisions and mappings must remain portable. Export through `POST /api/export-project` or the toolbar even before PASS; stay within the 8 MB project limit and provide schematic files separately when transferring machines.
8. Save Project persists in-progress work without requiring PASS. Named records live in `projects/saved/<id>.json`; use the selected project ID and its expected revision with `/api/projects` and `/api/build`, or `manifold.projects.save/build`. Save & Validate additionally creates an immutable build snapshot. Exact optimization preserves candidate evidence without committing the design; it requires an existing saved project as its revision baseline. Retain failures; never weaken a rule to obtain PASS. Geometry PASS is not pressure, vendor or manufacturing certification.
9. A genuinely new project starts with an empty library. Pin only selected definitions/resources. Never infer cartridge compatibility or independent assembly-envelope associations from names or geometry; preserve explicit relationship sources and unresolved review status.

Example review item:

```json
{"id":"BORE_DIAMETER","kind":"dimension","subject":"P","description":"Drawing omits finished bore diameter","proposed_value":"Provisional layout only; confirm from drawing owner","severity":"blocking","status":"open","resolution":""}
```

Use only known local paths and the current revision in a Codex handoff. No cloud, database, login, deployment or messages to other people are needed.

## V2.2 understanding contract

The AI Design foundation emits a separate `pmc-ai-analysis` packet containing document references, original engineering requirements, hydraulic understanding, proposed intent, source evidence, unresolved knowledge requests and engineer reviews. It is not accepted as this manifold Design contract. A future proposal stage must deliberately translate reviewed understanding into a Design and use the existing deterministic admission/build APIs. See [AI Design Layer](AI_DESIGN_LAYER.md).
