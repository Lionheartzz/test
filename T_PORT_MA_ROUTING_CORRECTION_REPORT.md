# T-port / MA focused correction

Starting HEAD: `9e807545c7afc827f649791b029f21d3072db639`

Branch: `codex/sqlite-domain-reset`

## Matched current evidence

- Trace: `output/cad-diagnostics/255297a0e9bb4e18bcee35a9c5df5dee.json`.
- Trace SHA-256: `1f07cf3b9dd0a6a8f64499c4dcbc7651d042ca9eb74a1cc8839d5ed9a7f8fef4`.
- Matching authored Draft: `output/ai-design/343f91fdb98c435296b6e78322157433/generations/dc8b355ba77344988a6ba58267f8bf2e/authored-draft.json`.
- Canonical source SHA-256: `abc122d4cb600284804d96baf95aa6956b4efd78c41d79d84194211428710c03`, independently recomputed using stdlib JSON/SHA-256 and matched to Exact's source revision.
- Block: **275 × 175 × 115 mm**. Current proposal: **32 generated drilling features**, saved Exact elapsed **115.484 s**, production BRep marked valid.
- The old 255 mm / 417.42 mm³ evidence was not used as the current result.

## Exact T collision

Exact reports complete attribution of **246.50683011348195 mm³** to:

| Feature | Net | Face / U / V / diameter / cylinder depth, mm |
| --- | --- | --- |
| `R-489f6472-3` | MB_CBCG2_to_DSCS | back / 197.125 / 55.43 / 8 / 54.477073 |
| `R-e632b709-1` | T | right / 133.172927 / 57.83 / 8 / 161.375 |

These are perpendicular generated drillings. The first runs along Y from 175 to 120.522927; the second along X from 275 to 113.625. Their projections cross, with only **2.4 mm** between their Z centerlines versus a combined radius of 8 mm. This confirms the saved Exact attribution without generating geometry.

Selected variants were:

- MB_CBCG2_to_DSCS: `xyz:nearest:planes_1_124.522927`.
- T: `axial_1_0:xyz:positive:c0_y_133.172927`.
- MA: `yzx:nearest:offset_y_m`, explicitly unresolved.

This is not the older cavity-versus-T-stem collision. The current failure is a conflicting generated connector combination. T retained only one clear candidate; the MB branch retained 16. The complete combination search never started because MA had an empty pool. Progressive repair stopped at its 256-state budget with MA connectivity, this cross-Net conflict, and a separate A_DC/P installation-access conflict still present.

`propose()` also forced every external-port strategy through the same coaxial stem formula (window end + machining radius + route radius + planning wall), including axial connector variants. Connector detours could vary while that terminal approach could not.

## MA diagnosis and correction

MA requires all three terminals:

| Source terminal | World center, mm |
| --- | --- |
| `CV_b129dfad71d8883c543f:port1` (RDDA/T-10A) | 206.0263697733023 / 67.625 / 66.7775 |
| `CV_1dd54928cfffd2ef3ce2:port1` (CBCG1/T-11A) | 77.875 / 149.6763697733023 / 42.1625 |
| `PORT_b8c55d1f3e80d59408c1` | 12 / 108.65068488665115 / 54.47 |

The source-backed cavity windows are 7.155 and 7.185 mm wide, narrower than the 8 mm route bore. The existing router therefore uses drill-tip first-contact approaches. Those source dimensions and protection checks remain unchanged.

Saved MA diagnostics show **0 retained clear / 271 considered**, with **10 connectivity rejections**. Other rejection-rule occurrences include source_protected 794, installation_access 256, cross_net_wall 28 and plug_cut 129; these are rule occurrences, not disjoint candidate counts.

Static inspection established three defects:

1. Recovery was entered only when the *raw* source-clear shortlist was empty. A nonempty shortlist whose candidates all failed connectivity prevented redundant-cut recovery, even with unused simplification slots. Recovery now uses only the unused portion of the original 16-slot budget.
2. Simplification could reject a route using cylinder-only proxies that omit drill tips, or report connectivity without checking exact fluid contacts when no proxy node was removable. Admission and pruning now share cached exact fluid-contact/flow-opening edges. A disconnected generated island can be removed only if all required terminals remain connected and the island contains no authored, frozen, construction-access or externally referenced node.
3. Pinned variant regeneration discarded the simplifier's connectivity result; missing failure text could be interpreted as verified connectivity. The result is now propagated explicitly, and an unverified fallback remains unresolved.

The saved trace does not contain MA's individual failed drilling coordinates or contact graphs. It cannot establish which exact edge failed in each of those ten candidates, or prove that all ten failures have one geometric cause. Future bounded pool diagnostics now retain per-candidate drilling coordinates, exact contact edges, unreachable required terminals, discarded islands and attributed rejection features.

## Implemented changes

- `routing.py::port_turn_depth`, `propose`, `port_approach_candidates`, `route_from_variant`: retain the original stem and add explicitly encoded alternative junctions inside a sufficiently large real hydraulic window or beyond the actual machining body. The latter includes drill-tip/machining extent, bore radius and the existing planning wall. No new user setting or floating internal cut.
- A window approach must contain the full transverse bore in actual source geometry, including offsets/tapers/annuli. Thread-only ports with unknown thread depth do **not** acquire an invented side-entry window. The real T port has that limitation; its alternatives retain a coaxial continuation through its actual port machining.
- `cavity_access.py::axial_route` forwards the port junction to the shared proposal generator. Axial eligibility itself is unchanged.
- `routing.py::simplify_generated_route`, `route_options`, `_route_pool`, `_resolve_proposals`: correct connectivity admission, budgeted recovery and candidate diagnostics as described above.
- `_conflict_objective` and unresolved candidate/fallback ranking now prioritize connectivity, cross-Net conflicts, source protection, remaining wall/plug/tool feasibility, then manufacturing objective. Clear-pool admission still rejects every hard failure. Authoritative CAD/STEP feasibility gates remain intact.
- `layout_planning.py::saved_route_evidence`, `_evidence_focus`, `alternatives`, `plan`: read completed saved Exact evidence only on an exact authored-source hash match. Inspect bounded recent traces after a restart, with no caller-supplied file paths. Attribute generated cuts back to their owning nets and required source interfaces; include the empty-connectivity pool.
- Matching evidence prioritizes local face-coordinate proposals for implicated external ports/cavities, including T, CBCG2/DSCS and MA interfaces. Owners are sampled round-robin; unrelated cavity swaps and whole-block growth are not used for this evidence-guided sample. Other layouts retain the previous analytic behavior.
- `server.py::layout_proposals` supplies that evidence through the existing read-only endpoint. Existing before/after review, explicit **Apply to editable draft**, stale-owner guard and Undo behavior remain. No geometry moves on requesting suggestions.
- `schema.py` extends only the existing routing-variant string grammar so terminal strategies regenerate through the shared global/local router. No project schema version or SQLite change.

Existing budgets remain: 16 simplification slots, 1000 combination states / 4000 pair screens, 256 repair states / 4000 pair screens, 8 authoritative exact attempts, and 8 requested layout assessments. The new terminal family has a bounded 48-variant analytic generation sample; it does not increase exact attempts. No wall-clock timeout was introduced.

## Verification boundary

Performed: saved evidence/revision matching, read-only source-window inspection, static code review, Python AST parsing of changed modules, and `git diff --check`.

As explicitly requested, **no tests, Vite build, browser, CAD generation, routing execution or paid AI call** was run. No new route, relocation or zero-FAIL result is claimed. Actual MA connectivity, elimination of the T collision, proposed relocation feasibility, final CAD/STEP results and runtime performance remain unverified. The saved A_DC/P access conflict also requires a subsequent real calculation; it was not hidden.

Protected active DB SHA-256 unchanged: `1E3267BD6A6271CF819B5181ED52EAE55AB8B8B54A4A48CE45CC277175D7DAA2`. Provider configuration SHA-256 unchanged: `2585ED2E0E32FF5677CF0D3136FDD948F7A9C9CF951EB6683DF969CF742E190A`. No saved Draft, manual/frozen/committed machining, source cavity, wall rule, SQLite data or AI Stage 1 was altered.
