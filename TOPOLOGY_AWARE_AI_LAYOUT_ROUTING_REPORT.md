# Topology-aware AI layout and routing correction

**Engineering acceptance: UNRESOLVED. The bounded search has not produced a mutually isolated eight-valve manifold. Do not manufacture this candidate.**

Starting HEAD: `ea48596420207d9e3b0b2af1d3c992b9b9d0a129`; branch `codex/sqlite-domain-reset`. Implementation commit and verified remote SHA are supplied in the delivery message. The original working tree was clean.

## Source-reviewed topology and adoption

The original schematic, normalized run, prior source review, execution-safe Cartridge/Cavity relationships and source hydraulic windows were retained. This is a source-reviewed engineering proposal, not a claim that every connection has received engineer approval. The seven isolated pilot nets are not deleted to hide failures: their real traced connections form the eight circuits below. DSCS port1 retains its source machining and its documented unused interface disposition.

| Net | Reviewed schematic terminals | Source evidence |
|---|---|---|
| MA | C1P2, C2P1, C3P1, EXT1 | Left vertical rail x182: RDDA top left port2, RDDA middle left port1, CBCG left top port1. |
| MB | C1P1, C2P2, C4P1, EXT2 | Right vertical rail x321: RDDA top right port1, RDDA middle right port2, CBCG right top port1. |
| A_DC | C3P2, C4P3, C5P2, C6P1 | Left work line x182 y434..631; CBCG right port3 diagonal reaches x245 y479; DSCS port2; directional A. |
| B_DC | C3P3, C4P2, C5P4, C6P2 | Right work line x321 y434..631; CBCG left port3 diagonal reaches x270 y479; DSCS port4; directional B. |
| P | C6P3, C8P1, EXT3 | P boundary x136 y871..783, directional P vertical x270, LRHC port1. |
| T | C7P2, C8P2, EXT4 | T boundary x458 y871..783, RBAA port2 vertical x458; LRHC port2 at x321 y783. |
| T_DC | C6P4, C8P3 | Directional T x284 y687..727, elbow to x324 y727..783; LRHC external control port3. |
| SHUTTLE_OUTPUT | C5P3, C7P1 | DSCS port3 x258 y546..588 then x399 y588..688; RBAA port1. |

C4 printed observations were reversed: C4P1 is physical window 1, C4P3 is window 3. DSCS nose port1 is unused per the previously retrieved official Sun catalogue, printed page 161; no internal pilot drilling is invented. C6 remains a source-backed mounting interface, separately from an unresolved commercial product identity. Flow, pressure, complete threaded-port machining and other retained review facts are not manufactured from valve function.

Normal adoption: open the completed analysis, expand **Review / correct hydraulic net assignments**, import `docs/engineering/eight-valve-topology-review.json`, review the before/after table and click **Apply reviewed topology**. It is bound to task/run/input revision and normalized-result SHA. Preview writes nothing. Apply uses the existing optimistic-revision-guarded local API and stores corrections separately from the immutable run. Existing explicit net corrections are not silently overridden; current interface bindings remain explicit choices. No paid AI call or recognition rerun is needed. Browser interaction was deliberately not run.

## Confirmed algorithm defects and corrections

1. The old eight layouts were independent swaps/one-axis shifts from a compact baseline. They did not coordinate opposing source depths, four-terminal trees, external entry diameters, source columns, installed bodies and shared drilling corridors.
2. Connection-topology candidates only covered three terminals. Four-terminal roots/common junctions now use the same physical drilling generator, with the existing 48-attempt topology bound. A coordinate-bound branch strategy provides a shared junction and uses genuine eligible deep-end bores; source stop depths/eligibility and zone protection are unchanged.
3. One global entry direction could not express mixed per-hole entries. A bounded source-aware refinement screens both actual external entries with their bound generic closure, retaining manual/frozen/committed obstacles. The established two-terminal shortlist is retained; multi-terminal refinements get the same final 16-candidate simplification bound.
4. Candidate preparation could remove a genuine connector in favor of a near-tangent contact. The observed A_DC shortcut had only 0.03132 mm³ overlap, below the required 0.1 mm³. Conservative inscribed-sphere overlap now protects the full connector. Exact contact/opening verification remains mandatory and authoritative.
5. Newly introduced adaptive entry decisions could regenerate a different cut when a previously selected mutable net was present. Stable branch regeneration and preparation now use fixed source geometry only. Whole-combination compatibility independently checks mutable automatic nets. The iteration-order regression test covers this boundary.

The same common bounded compatibility/objective solver is reused by analytic AI screening and exact routing. Calling it with analytic pools never sets connectivity_verified or engineering acceptance. No axial score bonus or scalar replacement of Design Priority was introduced.

## AI-owned layout search and ownership

Only `ai_design.generation._plan_generated_layout()` calls the new generation-local planner, on the newly compiled candidate copy. It coordinates independent source columns, permitted opposite/orthogonal mounting faces, source-ordered corridors, functional port entry diameters, actual source installation footprints and measured block growth. The transverse family requires distinct face-open source windows; an offset alone never classifies a cavity as a mounting pattern.

A two-parent progressive queue retains coordinated parent changes and tries implicated interface positions, real source-pattern rotations, permitted mounting faces and branch planes. The limits remain 8 layouts, 32 analytic route samples / 8 retained options per net, 1000 combination states and 4000 pair screens. No wall-clock deadline or full-CAD-per-layout loop was added. The final selected layout has source-clear individual pools but no compatible retained complete combination.

Explicit faces, envelope constraints and linked/user-owned axes remain binding. Manual, frozen or committed machining prevents automatic rearrangement. `origin.method` grants no authority. Model Preview/Reroute/Optimize/Validate/Build/Save/Reload do not invoke the AI planner. Existing Model layout alternatives remain reviewable proposals with explicit Apply. The original authored project was not moved or resized.

## Selected offline proposal (not applied)

| Interface | Face | U mm | V mm | Rotation |
|---|---|---:|---:|---:|
| C1 | top | 103.375000 | 58.465000 | 0 |
| C2 | bottom | 23.875000 | 58.465000 | 0 |
| C3 | top | 63.625000 | 58.465000 | 0 |
| C4 | bottom | 143.125000 | 58.465000 | 0 |
| C5 | top | 182.875000 | 58.465000 | 0 |
| C6 | front | 166.175000 | 169.391370 | 270 |
| C7 | top | 225.800000 | 58.465000 | 0 |
| C8 | top | 275.075000 | 58.465000 | 0 |
| MA-PORT | left | 88.690000 | 104.665000 | 0 |
| MB-PORT | left | 109.740000 | 104.665000 | 0 |
| P-PORT | left | 144.615000 | 104.665000 | 0 |
| T-PORT | left | 193.315000 | 104.665000 | 0 |

The block is **310 × 245 × 230 mm**. Growth follows source machining depths, source-column widths, functional entry spacing, and the mounting-pattern installed footprint plus closure access. This is a failed engineering proposal, not an endorsed stock size or proof that this amount of space is sufficient.

## Actual Exact CAD comparison

| Metric | Previous corrected candidate | Final bounded candidate |
|---|---:|---:|
| Block mm | 275 × 175 × 115 | 310 × 245 × 230 |
| Generated drillings | 41 | 49 |
| Plugged accesses | 39 | 45 |
| Total depth mm | 3946.751208 | 8109.502798 |
| PASS / WARNING / FAIL | 3326 / 17 / 115 | 4202 / 38 / 39 |
| Unintended cross-net pairs | 31 | 13 |
| Required source-to-route connectivity | Not all proven | All 8 nets verified |
| BRep | Invalid; 3 solids | Valid; 1 solid |
| STEP | Valid reimport; 3 solids (FAIL) | Valid; 1 solid (PASS) |
| STEP volume delta mm³ | 0.000098097 | 0.000000018626 |
| Manufacturing-ready | false | false |

Final analytic generation: 72.875 s, 8 layouts. Final fixed-layout authoritative evaluation: 15.422 s, one exact candidate. Previous fixed corrected-case evaluation took 352.562 s. This is not an exhaustive-optimization timing comparison: the final offline run checks the preselected branch templates once (`max_attempts=1`). Normal authoritative eight-attempt architecture is unchanged. Re-evaluations during development checked this same case after proven pruning/regeneration fixes; no full CAD sweep across layouts was performed.

The retained single-net source-clear counts are: MA=12, MB=11, A_DC=2, B_DC=10, P=17, T=13, T_DC=5, SHUTTLE_OUTPUT=12. These counts are obstruction evidence only. Exact verification separately proves positive physical connectivity for every required source window; flow-opening adequacy remains unknown where no flow was specified.

## Remaining failures: exact physical attribution

All 39 remaining FAIL rows are the three existing checks on each of the 13 actual cross-net intersections: circuit_intersection, declared_connection and unintended_cut_intersection. Source-protected, connectivity, production topology and STEP checks have no FAIL in this candidate. No validation severity or threshold was changed.

| Net pair | Exact feature pair | Fluid intersection mm³ |
|---|---|---:|
| A_DC ↔ MB | `R-702e7749-4` ↔ `R-1d09f6fa-AX2` | 0.03132 |
| A_DC ↔ SHUTTLE_OUTPUT | `R-702e7749-5` ↔ `R-f623208d-4` | 341.33333 |
| A_DC ↔ B_DC | `R-702e7749-6` ↔ `R-309be2fb-5` | 341.33333 |
| A_DC ↔ B_DC | `R-702e7749-7` ↔ `R-309be2fb-6` | 341.33333 |
| A_DC ↔ B_DC | `R-702e7749-8` ↔ `R-309be2fb-7` | 341.33333 |
| A_DC ↔ B_DC | `R-702e7749-9` ↔ `R-309be2fb-8` | 341.33333 |
| A_DC ↔ SHUTTLE_OUTPUT | `R-702e7749-9` ↔ `R-f623208d-2` | 341.33333 |
| B_DC ↔ T_DC | `R-309be2fb-4` ↔ `R-8e428e23-3` | 183.12468 |
| B_DC ↔ MB | `R-309be2fb-7` ↔ `R-1d09f6fa-AX2` | 0.03132 |
| B_DC ↔ T_DC | `R-309be2fb-8` ↔ `R-8e428e23-2` | 183.12626 |
| MA ↔ MB | `R-f0055891-1` ↔ `R-1d09f6fa-3` | 341.33333 |
| MA ↔ MB | `R-f0055891-5` ↔ `R-1d09f6fa-3` | 341.33333 |
| MB ↔ T_DC | `R-1d09f6fa-AX2` ↔ `R-8e428e23-3` | 200.99777 |

| Cutting feature | Face | U mm | V mm | Cylinder depth mm |
|---|---|---:|---:|---:|
| `R-1d09f6fa-3` | front | 103.375000 | 104.665000 | 113.740000 |
| `R-1d09f6fa-AX2` | top | 143.125000 | 58.465000 | 151.492133 |
| `R-309be2fb-4` | left | 174.515000 | 196.630000 | 186.875000 |
| `R-309be2fb-5` | front | 63.625000 | 194.250000 | 178.515000 |
| `R-309be2fb-6` | front | 143.125000 | 59.570000 | 178.515000 |
| `R-309be2fb-7` | back | 151.075000 | 159.091370 | 234.880000 |
| `R-309be2fb-8` | back | 182.875000 | 196.630000 | 190.535000 |
| `R-702e7749-4` | back | 151.075000 | 179.691370 | 234.880000 |
| `R-702e7749-5` | back | 182.875000 | 149.790000 | 190.535000 |
| `R-702e7749-6` | top | 63.625000 | 163.415000 | 129.335000 |
| `R-702e7749-7` | bottom | 143.125000 | 163.415000 | 108.665000 |
| `R-702e7749-8` | top | 151.075000 | 163.415000 | 129.335000 |
| `R-702e7749-9` | top | 182.875000 | 163.415000 | 129.335000 |
| `R-8e428e23-2` | right | 212.115000 | 193.191370 | 174.025000 |
| `R-8e428e23-3` | back | 139.975000 | 193.191370 | 234.880000 |
| `R-f0055891-1` | left | 88.690000 | 104.665000 | 107.375000 |
| `R-f0055891-5` | top | 103.375000 | 88.690000 | 129.335000 |
| `R-f623208d-2` | back | 182.875000 | 172.830000 | 190.535000 |
| `R-f623208d-4` | bottom | 182.875000 | 125.815000 | 176.830000 |

Physical limitation of the retained families: the MA/MB shared-height transverse trunks and their vertical branches still cross; A_DC/B_DC source branches compete with each other and with deep MB accesses, T_DC and the shuttle branch. The exact pair table identifies those real cuts. Near-tangent cross-net contacts still FAIL; the small volumes are not ignored. A common single-junction branching family is not sufficient to isolate this coupled topology in the sampled placements. Eight analytic layouts were exhausted; this does **not** establish geometric impossibility or exhaustion of all legal manifold arrangements. No successful arrangement is claimed.

Remaining warnings: drill_reach=27, engineering_review=7, port_machining_form=4. These include deep-drilling ratio, incomplete port machining and unresolved engineering review facts. Neither pressure qualification nor manufacturing approval is claimed.

## Protected artifacts and verification

SHA-256 before/after were equal for the original saved project, active SQLite v8 DB, previously successful independent route candidate and immutable normalized AI run. Exact resolution made no changes to the supplied candidate’s authored source placements. No SQLite, source definition, manual route or committed/frozen cut was altered.

- `projects\saved\2b93c6c68df24d5ebe543215e8e91c99.json`: `450ff90ca5ae82b958fae5e45558cf57c37be7ce5c9468aa13072934fed43f2a`
- `data\pmc_engineering.db`: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`
- `output\runtime-checks\ma-preview-eb4a637705d3460193f437117048d7e5\interior-selected-proposal.json`: `4258f0abfd8d8a17df84232d7b4fb1a24d38d333714f034d93f46b0475a1a292`
- `output\ai-design\343f91fdb98c435296b6e78322157433\current.json`: `89f9a31c14687a91daa5914302bc2fb7ba674fc7a30e073a5adcc98e48ae4094`

Focused verification:

- 20 focused Python cases passed: source-bound review preview/apply/API revision guards; branch/root connectivity; stable entry regeneration; tangential connector protection; offset-cavity classification; ownership; priority metrics/pruning; manual/frozen retention.
- Two incremental axial dependency cases passed after preserving the established two-terminal shortlist (port move only T; cavity move only T/B). Total distinct focused Python cases: 22.
- Two topology-review JS tests passed. An additional existing capacity UI test fails its old text assertion; the identical failure was reproduced against starting HEAD. Its unaffected handoff test passes. No new failure was accepted.
- `python -m manifold prove`: exit 0; invalid fixture 295 PASS / 2 WARNING / 6 FAIL; corrected fixture 268 PASS / 1 WARNING / 0 FAIL. Final proof under `output/proof/20261011-234100`.
- `git diff --check`: passed. No broad suite, Vite build, browser automation or paid AI call.

Evidence remains local under `output/runtime-checks/eight-valve-layout-routing/`: generated-layout-proposal.json, generated-layout-evidence.json (all bounded layout evaluations), corrected-selected-proposal.json, corrected-validation.json, corrected-acceptance.json, evaluation-trace.json, production STEP and proof logs. Historical evidence was not overwritten. CAD/large generated outputs and the active DB are not committed.

Changed files: `manifold/ai_design/{generation.py,generation_models.py,intent.py,service.py,layout_search.py}`, `manifold/{routing.py,cavity_access.py,schema.py}`, `web/ai-generation.js`, the source-bound review JSON, three focused test files, and this report.

**Release boundary:** software corrections are deliverable; the eight-valve production manifold remains explicitly unresolved because 13 unintended fluid intersections persist. The original saved project remains untouched.
