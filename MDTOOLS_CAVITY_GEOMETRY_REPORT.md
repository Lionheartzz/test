# MDTools cavity geometry conversion audit

Source: `D:\Project\Manifold\PMC_MDTools_Library\PMC_MDTools_Master_Library_2026R2_Merged`. Before: `data\pmc_engineering.db`. Rebuilt staging: `output\mdtools-geometry-20260928\staging-delivery.db`.
Both databases were read only for this report. The current runtime database was not replaced.

## Source interpretation

Circle1–11 give ordered form diameters at cumulative depths from the locating shoulder. An explicit LSMinDepth defines that datum; otherwise a CV uses a shallow Circle0Depth as its entry datum. If Circle0 extends beyond the entire form sequence, it is an independent bore and adds no datum. Circle0 is an independent entry cut on ordinary profiles. With the MDTools IsSunCavity profile flag, Circle0 is socket/tool access and is excluded from the fixed form cut. Circle12 is a predrill: its transition cone is fixed on a CV, while the long pilot reach is a machining reference for a future connection. On ports, direct holes and bolt/locator footprints, an explicit pilot is a fixed cut. STEP0 and STEP12 retain their source dimensions and carry tool_clearance/pilot_reference roles where they are not executable cavity stock removal. Hydraulic windows use the same CV datum and a zero-size nose port uses the final form land. Source inch fractions such as 7/8 and 1-1/16 are converted numerically. A nominal cone is limited to the next declared STEP depth when the source angle and depth disagree. Footprint BH/DH/LP Circle rows with explicit DRILL/TAP operations remain offset machining cuts; EnvelopDimensions remains a mounting boundary, not a subtraction.

The SUN first-party general-information drawing identifies Ø31.8 mm as socket-wrench clearance (not included on the form drill), a separate locating shoulder, and Ø13.49 mm as a maximum nose dimension: https://www.sunhydraulics.com/sites/default/files/media_library/tech_resources/uk_bm_geninfo.pdf

## Before / after

- Matched imported definitions with changed stage or primitive geometry: **6829** (6383 cavities, 446 external ports).
- Unchanged matched definitions: **46**.

| Manufacturer | Name | Unit | Old max depth / Ø mm | New max depth / Ø mm | ID |
|---|---|---|---:|---:|---|
| Sun Hydraulics | T-10A | metric | 130.91 / 31.75 | 51.80 / 25.40 | `cav_550b3810cce6a57d70c0` |
| Sun Hydraulics | SC-08-04 | inch | 68.33 / 30.00 | 56.60 / 20.60 | `cav_15965a00ddf0fdfd7440` |
| HydraForce | HVC06-2 | inch | 40.24 / 24.87 | 26.44 / 24.87 | `cav_9a4d5e5643f6de9646f7` |
| Parker | CAVT11A | inch | 94.43 / 31.75 | 76.43 / 25.40 | `cav_5971a0c0548b09fd450c` |
| Danfoss (Comatrol) | CP04-2 | inch | 40.01 / 15.88 | 32.98 / 15.88 | `cav_03c502f724a7ca74219a` |
| Eaton | A12196 | inch | 89.11 / 35.99 | 65.62 / 35.99 | `cav_f8a5c247fdbed8e6010d` |
| Bucher Hydraulics | AA | inch | 39.81 / 20.17 | 26.59 / 20.17 | `cav_aba1b6720195cd4ce6c7` |
| Rexroth | 003 | inch | 84.31 / 42.01 | 52.90 / 42.01 | `cav_4c2981602c49e6c10529` |
| HYDAC | 03030 | metric | 35.90 / 15.00 | 30.00 / 15.00 | `cav_e4e29aea03454e074166` |

### SUN T-10A (metric) stage sequence

| Stage | Old start–end / Ø mm | New start–end / Ø mm |
|---:|---|---|
| 1 | 0.00–33.32 / Ø31.75 | 0.00–7.93 / Ø25.40 |
| 2 | 33.32–38.68 / Ø25.40 | 7.93–11.93 / Ø21.85 |
| 3 | 38.68–44.45 / Ø21.85 | 11.93–12.36 / Ø21.16 |
| 4 | 44.45–48.41 / Ø20.66 | 12.36–16.22 / Ø20.66 |
| 5 | 48.41–57.15 / Ø20.00 | 16.22–24.63 / Ø20.00 |
| 6 | 57.15–76.61 / Ø18.59 | 24.63–44.64 / Ø18.59 |
| 7 | 76.61–84.32 / Ø17.48 | 44.64–51.80 / Ø17.48 |
| 8 | 84.32–127.00 / Ø13.00 | — |

Raw MDB parity checked: `MMVESTMDToolsLibrary.mdb:CavityTable59 / CavityIndex 30` and `InchVESTMDToolsLibrary.mdb:CavityTable41 / CavityIndex 34` match the merged Circle0, Circle1, Circle12 and LS source fields.
LSCircleNumber 2 points to Circle2Dia 21.85 mm, matching the SUN drawing’s Ø21.82–21.87 mm locating shoulder. LSMinDepth 0.8 mm supplies the surface offset; Circle0Depth 33.32 mm is the separate socket/tool access depth.
Thread note `M20x1.5` remains present; installation/tool clearance Ø31.75 mm is retained outside cutting_primitives. Machining rows preserve STEP12 as pilot_reference and STEP0 as tool_clearance.

## Whole-library structural scan

- Definitions scanned: **6875**; resolved source STEP operands checked: **26928**.
| Check | Count | Representative IDs |
|---|---:|---|
| `stage_start_at_or_after_end` | 0 | — |
| `nonsequential_stages` | 0 | — |
| `negative_depth` | 0 | — |
| `nonpositive_diameter` | 0 | — |
| `unexplained_main_depth_jump` | 0 | — |
| `primitive_beyond_stage_profile` | 0 | — |
| `machining_step_mismatch` | 0 | — |
| `interface_outside_axial_cut` | 0 | — |
| `interface_without_mapped_cut` | 0 | — |
| `unbounded_cv_pilot_executed` | 0 | — |
| `socket_envelope_executed` | 0 | — |
| `empty_profile` | 0 | — |
| `stage_start_gap` | 0 | — |
| `diameter_increase` | 0 | — |
| `invalid_primitive_interval` | 0 | — |
| `source_backed_footprint_extension` | 514 | `cav_042b65803e284454ac60`, `cav_e84916e2a12254f39068`, `cav_c49b17d549d70aa49368`, `cav_5b864317acd9d96bfca7`, `cav_6f98446c2761a65fffcf`, `cav_ccdef1b4ee7bd45b7843`, `cav_851ec1eb84a61b862f1c`, `cav_a002bb0f378afee63519` |
| `preserved_legacy_profile` | 3 | `legacy_9e748479eff74f9d1ffd`, `legacy_f4b13572b03496a8aa64`, `legacy_5921e2deebdeaf4bc313` |
| `source_angle_depth_conflict` | 86 | `cav_9e0896541dea93f14330`, `cav_604ad133e9f196337f44`, `cav_c56102d6c1b338e648ec`, `cav_e57b1691af3e42a058fc`, `cav_fb66d60619204314da21`, `cav_fc5749b712285c9178b1`, `cav_c3d7053740b146cf2d11`, `cav_606b90fa2b815551acfc` |
| `pilot_diameter_exceeds_source_max` | 0 | — |

`source_backed_footprint_extension` is informational: offset child BH/DH/LP cuts may be deeper than the main cavity axis, and their source_ref identifies the actual child row.
`preserved_legacy_profile` identifies read-only custom/legacy rows copied unchanged from the prior DB.
`source_angle_depth_conflict` counts source rows where a nominal taper angle would pass the next declared STEP depth; the executable cone is bounded by the source depth so machining STEP endpoints remain aligned. These source inconsistencies remain visible for engineering review.
Stages are conservative axial envelopes of the main-axis cylinders/cones; primitives include source-backed offset footprint cuts and are the CAD subtraction shapes. This scan checks conversion structure, not pressure or manufacturing certification.

## Verification

- Fresh `staging-delivery.db`: 6,426 imported cavities, 446 external ports, 15,005 cartridges and 15,272 KB evidence relations. Schema v3 validation and `PRAGMA foreign_key_check` passed. Three `legacy_*` cavity definitions were copied unchanged from the current database.
- With `PMC_ENGINEERING_DB` pointing at the delivery staging DB, 102 focused importer, knowledge, engineering, routing, store/API and portability tests passed. The separate current-DB engineering tests also passed (27 tests).
- `python -m manifold prove` passed against both the unchanged current DB and delivery staging DB: corrected fixture 268 PASS, 1 WARNING, 0 FAIL; deliberately invalid fixture 6 FAIL. The development proof derives its A/T window and available drill diameter from the active SQLite cavity definition, so neither DB requires weakened validation.
- Real browser at `127.0.0.1:8766`, using an isolated copy of the delivery DB: [T-10A Machined void](docs/mdtools-geometry/t10a-delivery-machined-void.png), [T-10A Source machining info](docs/mdtools-geometry/t10a-delivery-source-info.png), and [HydraForce Machined void](docs/mdtools-geometry/hydraforce-delivery-machined-void.png). The exact preview completed; the UI dimensions matched the rebuilt SQLite stages. This visual check is not an engineering approval.
- No frontend code changed, so a Vite build was not required for this conversion task. `git diff --check` passed.
