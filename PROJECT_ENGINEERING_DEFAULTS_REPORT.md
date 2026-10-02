# Project engineering defaults and Net overrides

Delivered from `81ab514b65adbcc5850bdb643d2ba1971479d327` on `codex/sqlite-domain-reset`. The engineering master and its 24,948 valid cartridge/cavity pairs are unchanged.

## Project Settings and schema

**Project → Project Settings** now owns:

- Name; Metric/Imperial unit preference; optional minimum/maximum X/Y/Z envelope.
- Optional default pressure and flow; default velocity; pressure safety factor.
- Optional minimum wall/ligament floor and preferred wall margin.
- Design Priority and default drilling mode.

Block Inspector retains dimensions, engineering material, raw stock and actual block machining. It has no pressure rules, material stress, generation face preferences or evidence panels. Legacy explicit stress appears only in Advanced Project Settings while active. Material changes preserve all project criteria/defaults and explicit legacy stress, clear incompatible stock, and invalidate engineering output.

Project JSON is **schema 3**, adding `project_defaults` and making Net velocity/drilling mode nullable overrides. `rules.minimum_wall` and `constraints.preferred_wall_margin` are nullable. No SQLite migration or runtime master write occurs.

The pure `upgrade_project_v2()` adapter distinguishes old concrete defaults from new inheritance: v2/versionless old inputs preserve their old 7 mm floor, 4 mm preferred margin, 6 m/s velocity and orthogonal mode when omitted. Explicit values remain explicit; the input is not mutated. Reading a project does not rewrite its file. Explicit Save/Validate writes normalized v3. All new UI/generator creation paths emit v3, whose blank floor/margin really remain null. Old preference fields remain loadable; they do not move authored geometry.

## Inheritance and engineering calculations

`manifold/engineering_conditions.py` is the authoritative resolver. Routing, sizing, Validate, manufacturing flow output, Engineering Review, preview, AI context and the read-only `/api/engineering/conditions` response use it. Net UI displays backend effective values and their source; it does not calculate inheritance itself. The endpoint uses the existing bounded JSON, local request header and same-origin protection.

| Condition | Project default | P override / effective | T override / effective |
| --- | --- | --- | --- |
| Pressure | 250 bar, then 300 bar | null / 250, then 300 | 30 / 30 bar |
| Flow | 60 L/min | null / 60 | 80 / 80 L/min |
| Velocity | 6 m/s | null / 6 | 4 / 4 m/s |
| Drilling mode | orthogonal | null / orthogonal | simplest / simplest |

Inherited values remain null in authored Net JSON, including after routing resolution and saving. Project changes invalidate current output and automatic proposals; manual/frozen geometry stays authored geometry.

Strength requires one exact runtime material identity and an applicable, resolved `SOURCE_BACKED`, engineering-usable yield or 0.2% proof property. Tensile, generic, unresolved/conflicted and research-only values are never substituted. PMC design strength is that source property divided by the project safety factor. Legacy `allowable_stress_mpa` takes precedence and retains its previous **pre-factor basis / safety-factor** calculation, rather than changing old results.

Router and Validate share the existing thick-cylinder ligament formula. For a 12 mm bore at 250 bar, safety factor 2 and no floor:

| Exact material identity | Sourced yield MPa | PMC design strength MPa | Required local ligament mm |
| --- | ---: | ---: | ---: |
| MAT-CORE-DURABAR-65-45-12 | 310.264078185 | 155.132039093 | 1.059185844 |
| MAT-CORE-DURABAR-80-55-06 | 379.211651115 | 189.605825558 | 0.850927998 |

The same actual BRep feature pair with 0.95 mm separation fails the first material and passes the second; the router and validator agree. A 6 mm project floor raises either requirement to 6 mm; a 0.1 mm floor cannot lower either calculated value. Preferred margin changes ranking only; changing it leaves validation checks unchanged. Unspecified pressure remains unspecified. Specified pressure without applicable strength fails pressure adequacy and route screening; no hidden 7 mm or material strength is used to claim adequacy. Source-protected windows, hard non-intersection, source machining, tool/policy constraints and CAD-safe BRep/STEP gates remain authoritative.

## AI and mixed standards

Generation setup contains Auto/face choices for valve/cartridge and external port placement. These are request-only options. Required faces still win. An isolated, transparently marked local test analysis generated an actual source VC08-2 draft with front cavity and left ports. The later preference change to back/right changed neither stored nor live authored Face/U/V. No paid model was called and no production mock/configuration was added. New drafts do not populate legacy stress or persist layout preferences as engineering constraints.

AI analysis receives structured project criteria, source strength basis, explicit Net overrides, effective values and source markers. The generation path retains inherited defaults without copying them into Net overrides.

Real browser additions and saves verified Imperial + Metric mounting/ISO 6149, and Metric + UNC mounting/NPT. Opposite-unit catalogs stay available. Switching preference retains mm dimensions. Separate real source-definition/API/BRep tests cover both unit directions. Localhost interaction and visual checks passed; LAN `http://192.168.253.117:8765` showed `isSecureContext === false`, Project Settings and the preserved legacy 7 mm floor.

## Real project regression

Project `6e57fdcccb174b87a72c32f3069bb285`, final immutable build `726d39fff18d409e934cdf34fe36cbbd`:

- **450 PASS / 12 WARNING / 0 FAIL**, matching pre-task build `cf13565c6bef41bcaf30448fb2becbe9`.
- Authored block/features/engravings/modifiers, rules/constraints and explicit Net conditions are identical. Only the explicit save/build normalizes JSON from v2 to v3 and adds defaults.
- P: `axial_1_0:yxz:nearest`; T: `axial_1_0:xyz:nearest`; A: `xyz:nearest:offset_y_m`; B: `yzx:nearest:direct` — unchanged.
- 11 automatic drillings / 8 plugs / total drilling depth 1091.244266 mm — unchanged.
- Valid production BRep, one solid, passing production STEP round-trip; volume delta 0.00097897 mm³ — unchanged.
- Final Validate **57.094 s**, 2 exact candidates. Candidate 1 → alternate → candidate 2 → production STEP → completion remained visible, monotonic and below 100% until the result arrived. Duplicate Validate was blocked. Final engine revision `9ccdecc173e8bc4fd795b45855aee34de9663903fa3bd7db007740cbc78aa52a` matches the loaded source.

## Verification and artifacts

- **76 Python passed**: new project conditions/material/ligament tests, core materials, store/API, Validate progress, CAD-safe fallback, incremental preview and AI generation. Additional focused Design Priority checks: **3 passed**, including all four objectives.
- **36 JS passed**: Project Settings, material preservation, Home creation, Validate progress, preview, AI handoff and Library boundaries.
- Vite build passed; `python -m manifold prove` retained the intentional failing case and corrected **268 PASS / 1 WARNING / 0 FAIL**. `git diff --check` passed.
- Three failures encountered in expanded related sizing/AI checks were reproduced unchanged at the starting HEAD: `test_freeze_displayed_proposal_without_resolution_and_later_flow_change`, `test_construction_access_uses_route_size_and_missing_flow_is_unresolved` (OCCT null-shape failures), and `test_existing_external_port_is_open_exact_terminal_after_move` (existing 1.47975 mm wall vs 7 mm). They remain accepted baseline exceptions, with logs at `output/project-engineering-baseline*.log`. No assertion or engineering rule was weakened.
- Engineering DB SHA-256 unchanged: `4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`; SQLite user_version 4 unchanged; valid compatibility count 24,948 unchanged.

Local screenshots: `output/playwright/project-engineering/project-settings.png`, `net-overrides.png`, `mixed-inch-mounting.png`, `mixed-inch-port.png`, `mixed-metric-mounting.png`, `mixed-metric-port.png`, `ai-generation-preferences.png`, `ai-generated-model.png`, `ai-authored-face.png`, `lan-project-settings.png`, and `run-1-complete.png`. Test/browser logs and final progress events remain in `output/project-engineering*`; immutable project/proof artifacts are retained. No broad unrelated audit was run.

Changed scope: central conditions/schema, their existing engineering consumers and AI request/generation paths; Project Settings/Block/Net UI and new-project entry paths; focused tests and this report. Drawing, source cavity geometry, minimum-overlap/STEP tolerances, KB policy, compatibility data and SQLite are unchanged. Delivery commit, verified remote HEAD and clean-tree status are supplied in the completion message.
