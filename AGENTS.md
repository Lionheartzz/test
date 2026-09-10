# PMC Manifold

- Normal user projects live in `projects/saved/<id>.json`; each stores its design and build pointer. Respect project IDs and optimistic revisions. `projects/demo.json` is a legacy development/proof fixture, not the default user project. Preserve immutable build snapshots under `output/builds/` and schema version 1 compatibility.
- Read README engineering boundaries before changing geometry or validation. Demo library dimensions must never be represented as vendor-approved cavities.
- All CAD imports go through `manifold.cad`; its Windows DLL order is tested and prevents process-exit heap corruption.
- Circuit identities are engineering fields. Distinguish cutting solids from installed cartridge interface nodes. Never infer connectivity from colors or tessellated meshes.
- Geometry changes must run `python -m manifold prove` and the targeted engineering tests in `.venv`. Keep failing proof cases and final PASS evidence.
- Backend changes must exercise store/API tests. Browser changes require local browser interaction and a visual check.
- Never ignore exit codes, fabricate PASS results, weaken a rule to make a fixture pass, or imply pressure/manufacturing certification.
- Run locally at 127.0.0.1:8765. No AI API, cloud, database, login, deployment or external publication is needed.
