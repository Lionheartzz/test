# PMC26-3069 Manufacturing Drawing correction

2026-09-14. Supersedes the earlier sparse manufacturing layout. The user's latest correction makes the supplied three-page PMC26-3069 the default manufacturing template and withdraws the earlier missing-reference-page prerequisite.

## Implemented layout

- A2 landscape, 594 × 420 mm; frame at 2 mm. Canonical dimensions and the template tolerance bands are millimetres, including when the source Project was authored in inch context.
- Three default sheets: overview, machining coordinates, internal drilling. Each contains top/left/front/right/back/bottom views together, plus ISO at the upper right. No per-face sheets or automatic separate machining-schedule sheets.
- Reference-measured view regions, stock summary at `(399, 2)`, PORTINGS at `(313, 247)`, company/logo at `(450, 364)`, and the bottom tolerance/ownership/alteration/design-signoff/title cells at `y=383` (top-origin paper mm).
- The Project's associated schematic, when available, occupies the reference's upper-left slot on all three sheets. No unrelated schematic is substituted for a Project without one.
- Overview stock dimensions and feature labels use PMC magenta. Coordinate sheets use associated ordinate dimensions, rotated X numbers, jogged extension lines, arrowheads and A–F face identifiers. The internal sheet renders the exact projected hidden edges. The ISO is vector linework; the reference's shaded colour ISO is represented by monochrome internal linework.
- Three repeated identifier/specification pairs in PORTINGS. Pinned definition names/catalogue identifiers and thread notes, explicit bore depth/point angle and unresolved plug-entry information follow the selected source. Different schematic and machining identifiers are cross-referenced in the same cell. Identical specifications may be grouped; every source feature ID is retained for coverage checks. Only actual wrapped-table overflow creates continuation sheets.
- Dynamic number/title/material/size/quantity/revision/signoff fields. No source hash, build ID or application acceptance state is printed on normal manufacturing sheets. The application retains source and review diagnostics. Attributed release exceptions still accompany an issued PDF when applicable.

## Preserved engineering boundaries

The correction changes Drawing generation/presentation only. It does not change source CAD, Library definitions, route solving, canonical validation, AI configuration or engineering review decisions. All dimensions remain computed from source anchors; presentation fields cannot override measured values. Missing manufacturing information still requires engineering finishing/review before release. The pre-existing machining-coverage check remains; using a catalogue cavity reference does not prove the complete factory process is documented.

Previously saved legacy layouts and issued PDFs are retained. Choose **Create Drawing → PMC Manufacturing Drawing** to obtain the new default. Regeneration of an existing document preserves its chosen template and manual layout; it does not silently replace it with the new template.

## Verification and review files

- `python -m pytest tests/test_drawing_workspace.py tests/test_store_api.py -q`: **24 passed**, four existing dependency deprecation warnings. Final log: `output/pmc3069-review/focused-tests.log`.
- Includes three-sheet grouping; precise A2 vector PDF; numeric datum coordinates; rotated dimensions; save/update retention; legacy documents; source immutability; invalid unit/paper rejection; canonical release rejection; repeated original vector schematics; 225 distinct table groups and wrapped-row continuation; lossless 120-hole grouping.
- `npm run build` passed. No engineering geometry implementation changed, so the prior CAD proof and full V2.3 regression were not redundantly rerun for this layout-only correction.
- Actual browser: create default manufacturing drawing, edit title and quantity, move an ordinate dimension, undo/redo, save/reopen, verify retained offset, and export PDF. Screenshots: `output/playwright/pmc3069-coordinates.png`, `pmc3069-internal.png`.
- All three final sheets were rendered and compared with PMC26-3069. Iteration fixed material wrapping, coincident feature labels, unnecessarily created continuation sheets from floating-point paper rounding, rotated overall dimensions and hidden-line/arrow appearance.

Main review PDF: **`output/pmc3069-review/manufacturing.pdf`**, exported through the browser. Project `8454af08a5744abc8c20bb26b1b95851`, Drawing `90484dc1b3934a1f90dca8a4a5e2b6f8`, 3 sheets / 21 views / 115 annotations. It uses a task-owned copy of an existing local hydraulic example, with actual validated geometry and explicitly illustrative Library definitions. It is a drawing-format review example, not a claim that the demo cavities or unresolved plug entry are vendor-approved for manufacture. Its source has no schematic, so that slot remains empty.

Density PDF: **`output/pmc3069-review/dense-manufacturing.pdf`**. Existing 120-hole source reused without rebuilding; 3 sheets / 21 views / 519 annotations. Project `d9cea672dfb946a89183fe7b773786e4`, Drawing `dc0faff70c04446ea39165c5d6dab5c8`. Both main and density documents have no layout errors or text-overlap warnings; their engineering finishing warnings remain visible in the app.

Additional source-schematic integration evidence: `output/pmc3069-review/schematic-manufacturing.pdf`, from a task-owned copy of the existing AI workflow fixture. It repeats that Project's synthetic schematic on all three sheets and preserves its uncertain material/review status. It is not a new Agnes analysis or an approved production drawing.

Original Projects and immutable build snapshots were retained. No Agnes call or provider-setting change was performed for this correction. The user authorized committing and pushing this correction to GitHub on 2026-09-14. The generated PDFs are ready for the user's visual review.
