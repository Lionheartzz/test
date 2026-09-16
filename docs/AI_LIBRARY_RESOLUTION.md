# AI library resolution

AI library resolution queries the same runtime SQLite database as Library, New Manifold, CAD, manufacturing and Drawing Workspace.

## Rules

1. Resolve a cavity by its database ID or a user-confirmed database selection.
2. Resolve a cartridge by its database ID. A model string alone does not prove identity or compatibility.
3. Accept a cartridge/cavity pair only when `cartridge_cavities` contains a valid explicit relationship.
4. Require an explicit, complete schematic-interface mapping when schematic intent exists. Generic inlet/outlet names are not guessed into numbered interfaces.
5. Leave unresolved choices visible and block generation when a required engineering reference is missing or ambiguous.
6. Keep `cartridge_id=null` valid. This skips compatibility checks and does not create a schematic component.

The resolver never scans the merged MDTools directory, `PMC_Library_Converted_v05`, `projects/library`, or embedded project definitions. Missing SQLite data is reported as unavailable; there is no legacy fallback.
