# Saved routing is project geometry

Project JSON schema 4 adds `route_state` (`unresolved`, `proposal`, `committed`,
`stale`) and an actionable `route_issue` to each net. Actual automatically
generated drillings remain in `Design.features`, with every existing Feature
field, route ownership, contacts, plug/closure data and construction access
identity. `routing_variant` is provenance. Automatic nets remain automatic.

Save copies only a current visible proposal belonging to the same draft signature
and project epoch. It cannot start route search. Incomplete routing asks the user
to wait. A retained view from an older draft cannot be committed. Save merges
generated cuts without flattening authored parent placements.

Open displays saved cuts first, seeds preview ownership from them, then reuses an
available matching exact build. Engine changes make validation stale, not route
geometry. Exact preview can regenerate the same cuts asynchronously. Neither
committed nor stale routes are enumerated or simplified on this path.

Validate/Build use `validate_current_design`: one exact current-design BRep,
contact authorization, the unchanged engineering rules, and the production STEP
round-trip gate. They never run alternate route selection. They may persist the
same visible unsaved proposal passed by the editor. A real invalid current model
remains a real failure; Validate cannot repair it behind the user's back.

Reroute releases the selected net. A moved/reassigned feature releases its
dependent automatic nets and retains the other cuts; actual obstruction conflicts
may expand that dependency set. Optimize explicitly releases automatic nets for
the existing bounded CAD/STEP search. Its result is a dirty proposal until Save.
Manual/frozen geometry is retained.
Its real stored geometry is included as the exact baseline within the same attempt
budget; a searched result cannot replace it with a worse exact score.

Names and display labels do not route or rebuild geometry. Pressure/flow/velocity
defaults affect only nets inheriting them. Pressure screens existing cuts. Flow
or velocity may resize their existing centerlines, using source tool sizing and
actual axial stop-depth geometry. Analytic protection screening runs first; the
existing exact preview BRep supplies an exact resize check before publishing the
resized proposal. Failed resizes restore previous cuts and mark the net stale.
No alternate route search runs for these settings. Changed routing policy retains
cuts and asks for explicit Optimize/Reroute.

Schema 2/3 adapters are pure reads. Existing persisted owned cuts become committed.
For legacy automatic nets lacking cuts, a build is used only when its authored
`design.json` matches this saved design and its original revision matches the
pointer. Its `resolved_design.json` supplies the route. Recovery does not write
project files. Without matching evidence, initial routing remains a proposal;
Save commits it once. SQLite is unchanged.

Read-only real legacy example inspected: project
`85a5799c71764a59abfc95ffb0d162a9` is schema 3 with zero saved generated cuts.
Build `27921e96c7de463fa7b35d3aeff666f5` has the same authored JSON and two generated
cuts, with N1 `axial_1_0:xyz:positive` and N2 `simple_0`. The loader's original
revision gate remains required before admitting these as recovered geometry.
The project/build files were not changed by this task.

## Existing diagnostics, inspected before changes

Newest diagnostic: `1ca147e4488d4135a64fc74553b0d672.json`, preview timeout at
30.031 s, CPU 29.875 s. No worker phase trace was published; its bottleneck cannot
be assigned from this record.

Newest complete preview: `5ffb0e5eda4340dfa09e565d25e0925c.json`, 13.094 s wall time.
Timings overlap (inclusive parent phases), so do not sum these rows.

| Phase | Recorded seconds |
|---|---:|
| worker.startup | 1.906 |
| route.resolution | 8.906 |
| route.proposal | 8.890 |
| route.simplification (64 calls) | 2.987 |
| hydraulic.net_geometry | 0.656 |
| hydraulic.cross_net_geometry | 0.016 |
| geometry.construction | 0.343 |
| geometry.production_boolean | 0.141 |
| review.generation | 1.219 |
| tessellation | 0.953 |
| mesh.occt_tessellate | 0.767 |
| result.serialization | 0.047 |

Measured bottleneck: route proposal, with repeated simplification contributing.
The committed reuse path eliminates that search. Explicit search reuses immutable
definition/tool/sizing data within its existing proposal snapshot; existing cut,
obstruction and pruning caches remain. No candidate families or checks are removed.
Project open, completed settings changes and Reroute skip the 1.5 s idle delay;
dragging/typing keep it. Server exact preview ceiling is 180 s, browser 185 s;
authoritative calculation remains 300 s.

The warm worker remains killable. Superseding an active OCCT operation still stops
that process, losing its warm imports; safely interrupting OCCT in-process is not
assumed. Exact Boolean geometry, hydraulic unions and tessellation remain necessary.

Review for this task is code inspection and Git diff only. No tests, browser,
build, proof, CAD runs or new benchmarks were executed. No new timing measurements
or runtime acceptance results are claimed.

## Changed files

- Backend: `manifold/schema.py`, `manifold/route_state.py`, `manifold/projects.py`,
  `manifold/store.py`, `manifold/routing.py`, `manifold/preview_routing.py`,
  `manifold/optimization.py`, `manifold/cad_worker.py`, `manifold/engineering.py`,
  `manifold/__main__.py`.
- Editor: `web/main.js`, `web/committed-routing.js`, `web/preview-routing.js`,
  `web/preview-queue.js`, `web/project-settings.js`, `web/engineering-inputs.js`,
  `web/kinematics.js`, `web/workflows.js`.
- Documentation: `docs/COMMITTED_ROUTING.md`.
