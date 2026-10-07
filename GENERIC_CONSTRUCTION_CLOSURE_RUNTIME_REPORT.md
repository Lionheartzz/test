# Generic construction closure runtime — Phase 2C

## Delivery

Starting HEAD: `fe21171abff032a7d9cfab20d3a151979d0ca4bb`, branch `codex/sqlite-domain-reset`; no reset or unrelated edits.

The active database now has **14 usable generic machining definitions**, **38 optional products / 38 mappings**, **24 legacy-ID aliases**, and the unchanged **443 knowledge targets**. All 38 former product IDs remain loadable. Routing, machining, plug exclusion and construction validation use the generic definition; no product selection is required and an absent SKU creates no warning.

The delivery commit and verified remote HEAD are provided in the final delivery message and `output/closure-runtime/phase2c-delivery.json`. The commit includes this report, code and focused tests, not databases or source archives.

## Finite source inventory and disposition

Original R2 and legacy MDB library-name indexes and all named plug-class tables were read with ACE `Mode=Read`. The merged master was also scanned for explicit `PlugPort` flags, footprint names, application names and source comments, not only filenames containing “plug”. The converted raw/index data, runtime external-port definitions, linked thread definitions and machining-modifier inventory were inspected.

| Source class | Legacy raw inch / metric | R2 raw inch / metric | Merged source records | Existing runtime ports | Eligible source interfaces |
| --- | ---: | ---: | ---: | ---: | ---: |
| Expander Plug Ports | 7 / 23 | 35 / 38 | 35 inch + 41 metric | 76 | 38 metric → 14 distinct definitions |
| SAE Plugs | Absent / absent | 9 / 9 | 18 | 18 | 0 |
| Orifice Plugs | 5 / 12 | 5 / 5 | 17 | 16 | 0 |

Source locations are `PMC_MDTools_Library/PMC_MDTools_Master_Library_2026R2_Merged/raw/{legacy,2026-R2}/{InchVESTMDToolsLibrary,MMVESTMDToolsLibrary}.mdb`, their `LibraryNameIndex` and indexed cavity tables, plus `cavities_master.jsonl`. R2 uses `CavityTable23` for expanders, `CavityTable33` for SAE, and `CavityTable58` / `CavityTable60` for inch / metric orifices. Legacy table names come from its own index rather than R2 table numbers.

Both PLUG MDBs' `ConPlugTable` and `PlugFilePath` contain 0 rows in both releases. Converted metric/inch `plugs_index.json` are empty. This does **not** imply the source lacks machining interfaces: the populated cavity tables above supply them.

Additional explicit flag/comment hits: **21 Short Ports**, **18 Short SAE Ports [M]**, and one each in **Winner Hydraulics**, **Eurofluid**, **SPECIAL**, **Sun Hydraulics**. These 42 additional records bring the finite reviewed set to **154**. A service-style port or a `PlugPort=1` flag alone does not establish a complete construction-closure role or occupied geometry. Cavity/valve text mentioning a plug is likewise not proof of a construction closure.

| Non-admitted source-record reason | Count | Engineering disposition |
| --- | ---: | --- |
| Missing verified engagement / installed envelope | 38 | 35 inch expanders and 3 legacy-only metric SPD records remain reference-only |
| Incomplete thread machining | 18 | SAE construction interfaces have threads/installation dimensions, but linked threads lack explicit source-backed TAP DRILL dimensions; do not substitute a nominal thread cylinder |
| Non-construction role | 17 | Orifice/restrictor interfaces do not close construction access |
| Unproven construction role | 39 | Short port definitions remain ordinary port data, not automatically promoted |
| Not a construction access | 4 | Other valve/cavity/special references remain unchanged |

The three non-admitted metric expander records are `MB-700-060 [SPD] [M]`, `MB-700-090 [SPD] [M]`, and `MB-700-120 [SPD] [M]`. Zero or absent `InsertionDepth`, hole depth and `PlugHeadHeight` are not treated as interchangeable engagement facts. No additional threaded family is admitted merely to increase coverage. Existing threads (833), o-ring-groove modifiers (191) and undercuts (135) are unchanged.

The full per-record identity, unit, active source-table reference, role and reason inventory is retained locally in `output/closure-runtime/phase2c-final-source-audit.json`; original MDB counts are preserved there. These source scans run only as explicit operator work, never during routing or server startup.

## Generic/product separation and compatibility

Schema v7 adds only `closure_products`, `closure_definition_products` and `closure_definition_aliases`. Existing `closure_definitions` columns are reused. Product model is no longer the runtime display identity; examples now read **Expander Plug Ø9 · entry 9.8 / engagement 10 mm**. Manufacturer, part number, setting stroke and product installation data live in the optional product layer. Unknown pressure ratings remain unknown.

38 original rows collapse to 14 only after matching the complete physical profile/tolerances, unit, occupied depth and installed envelope. Nominal diameter alone is never used to merge. Canonical IDs retain the first established default-family definitions; the remaining 24 IDs resolve through explicit aliases that also retain their original source-port references. Product mappings still contain all 38 exact identities.

By usable definition type: **expander 14; threaded 0; SAE 0; other 0**. Unit system: **metric 14, inch 0**; no inch product or geometry is invented. Existing inch-context projects can still use explicitly metric nonthreaded definitions under the established millimetre CAD contract.

The prior automatic family and ordering are preserved. New generic definitions are not implicitly marked as automatic defaults; incompatible or unresolved choices do not silently switch technology. Runtime queries use only the normalized catalogue and aliases, never PDFs, archives or 443 knowledge rows.

All 38 old IDs were checked for loading, alias resolution, unchanged effective dimensions/engagement/envelope, and retained compatible product identity. Geometry and manufacturing resolve aliases consistently; browsing an old selection does not edit the stored project. No project JSON was migrated or rewritten.

## Geometry / preview / real acceptance

The existing source machining adapter remains authoritative. No cavity geometry, hydraulic sizing, minimum wall, protected-region checks, routing objectives or CAD kernel was changed. Alias normalization precedes manufacturing lookup so exports use the same selected generic interface as geometry.

The geometry-switch regression selects two genuinely different compatible generic entries on one 8 mm construction access. ID, engagement, entry cut volume, Feature layer vertices and Machined void volume all change; the hydraulic bore stays **8 mm**. Both selections produce valid single-solid geometry and manufacturing PASS. A frontend regression confirms the two selections send distinct snapshots through the exact-preview pipeline rather than reusing stale cached geometry.

Without any optional product mapping, a selected generic definition still reaches `construction_closure=PASS`, `manufacturing_ready=true` and `unresolved_plug_entries=[]`. No product-level selection policy or warning was invented. Mapped products are subordinate information in Library detail and the inspector; there is no mandatory purchasing choice.

The existing real two-T-10A automatic proposal was reproduced before edits and checked against final staging and active data:

| Result | Before | Final |
| --- | --- | --- |
| Plugged construction accesses / resolved | 11 / 11 | 11 / 11 |
| PASS / WARNING / FAIL | 638 / 0 / 0 | 638 / 0 / 0 |
| Manufacturing ready | true | true |
| Unresolved plug entries | [] | [] |
| BRep / solid count | valid / 1 | valid / 1 |
| STEP / solid count | valid / 1 | valid / 1 |
| STEP volume delta | 0.0017379187047481537 mm³ | 0.0017379187047481537 mm³ |

The original route proposal and drilling dimensions are retained. Final active exact geometry/rules/STEP verification took **20.45 s**, compared with **22.36 s** before; these single runs are not a performance benchmark or repeated global optimization timings. Detailed elapsed results are in `phase2c-before-acceptance.json`, `phase2c-final-staging-acceptance.json` and `phase2c-active-acceptance.json` under `output/closure-runtime`.

## Database activation and preservation

Migration was explicit, with a read-only v6 source, separate staging clone and acceptance before final activation. No startup auto-migration exists. The active v6 backup is `output/closure-runtime/phase2c-active-before-v6.db`.

- Schema: **v6 → v7**.
- Active hash before: `b03c98523113cbca26258ce6c48dda491ff589a5ef38635a9e4ab93cc86e14d7`.
- Active hash after: `93f256aea9305c9895ec82dec38c3ee2b28e1d17476d1c0468fd2ebf3aefada5`.
- Active size delta: **57,344 bytes**; final standalone staging delta: **45,056 bytes**. SQLite page allocation differs after the intermediate reconciliation; logical rows match final staging.
- **46 protected tables unchanged**, including every REV2 relation, Cartridge Technical, Material Technical, Main Station knowledge, external-port and thread table. Full sorted row hashes are retained in `phase2c-final-migration.json`.
- External-port additions/changes: **0**. Thread additions/changes: **0**.
- Foreign-key check: **0 violations**. Integrity check: **ok**.

Activation checked exact final closure/product/mapping/alias tuples against accepted staging inside a transaction. It changed only this task's closure data and schema metadata.

## Verification / remaining gaps

- Focused Python: **30 passed** (`test_generic_closures.py`, `test_closure_runtime.py`, `test_route_plug_screen.py`).
- Focused JavaScript: **12 passed** (`closure-selector.test.mjs`, `library-ui.test.mjs`).
- Vite: PASS; only existing font-runtime / bundle-size warnings.
- `python -m manifold prove`: PASS. Deliberate invalid fixture retains 6 FAIL; corrected fixture retains 0 FAIL and its original unresolved manual-closure WARNING.
- `git diff --check`: PASS.
- Active health, definitions, optional product mappings and Library **14 definitions · 443 knowledge** API checks: PASS.
- Browser screenshots / visual interaction acceptance: left to the user under the prior explicit instruction to inspect personally. Automated exact preview/layer and UI-path tests were performed; no real-browser visual PASS is claimed.

Remaining source gaps are the non-admitted records above. No arbitrary thread adapter, inferred engagement, pressure rating or product approval was added. No separate user closure-family setting was introduced. Geometry for the working subset is unchanged; other technologies need complete source facts and an exact machining adapter before admission.

Changed files: generic migration and inventory modules; closure runtime/engineering queries; read-only Library schema validation compatibility; compatible-choice API; alias-aware manufacturing lookup; existing selector and Library UI; focused tests and this report. Restart the running service and refresh the page before manually inspecting the updated UI.
