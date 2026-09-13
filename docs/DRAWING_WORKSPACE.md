# Drawing Workspace · V2.3

Start from a saved Project manifold. Use **Save & Validate** to create a build for the saved revision, then **Drawings → Create Drawing**. Choose **PMC Customer Drawing** or **PMC Manufacturing Drawing**. Both use the same paper editor. Drawing generation runs locally; it never calls an AI provider or reroutes the manifold.

## Engineering source and drawing data

`projects/drawings/<project-id>/<drawing-id>/current.json` stores a drawing document independently of the Project's engineering revision. It contains the immutable source snapshot, generated projection geometry, and a separate editable presentation. Source evidence identifies the authored design SHA, resolved build, CAD engine revision and the hashes of the build artifacts. Drawing saves use their own optimistic revision, so two windows cannot silently overwrite each other.

Engineering geometry comes from the saved `production.step`; dimensions and manufacturing rows come from the same build's `resolved_design.json`, pinned definitions and machining schedule. Exact OCCT hidden-line projection supplies the vector outlines. Curved edges are represented by vector segments with 0.002 mm model-space deflection. Measurements never use triangles or pixels. A failed source can produce a clearly marked review draft; it cannot be released.

Manufacturer/model/cavity data remains subject to the source model's Library and engineering-review boundaries. Unconfirmed component identity is shown as pending review. Table specifications and numeric dimension values cannot be replaced by client-supplied engineering facts. Drawing notes, table remarks and label overrides are presentation statements; they do not update Library data or CAD. Manual label text requires review at release.

## Finish and save a drawing

- Select an item directly on the paper or in **Sheet objects**. Drag to reposition it; use the Properties panel for precise paper offsets.
- Add dimensions using engineering anchors: block corners, feature axes and individual machining-operation start/end points. Pick anchors on the paper or select them in the dialog. Values follow the source. Choose X, Y, aligned, diameter, radius, depth or a feature-axis angle relative to Z. Linear dimensions belong on orthographic/section views, since isometric projections are foreshortened.
- Change dimension offsets, precision and text height. Delete unwanted generated dimensions; regeneration remembers their suppression.
- Add notes/text and leaders/labels. Edit text using explicit line breaks when necessary. Longer notes can go on another sheet.
- Move views, change scale, show/hide hidden geometry or centerlines, or place views on another sheet. Add an orthographic/isometric view or a straight X/Y/Z section, then use **Update from Manifold** to calculate its exact projection.
- Add/edit/reorder sheets. Choose the paper size and orientation; the PMC defaults use A2 landscape. Other sizes require layout finishing. Out-of-bounds content blocks release.
- Move tables, change widths/type size/row count, set source-row order, choose a readable source row to edit its remark, and continue a table on another sheet. Source values remain fixed. Automatic pagination accounts for wrapped text. Source updates preserve edited row ranges; extend them if the coverage check identifies newly added rows.
- Place the source Project's schematic and choose its page/crop. Layout preserves aspect ratio. PDF schematic pages retain their vectors; raster originals remain raster. Cropping controls layout and is not a redaction tool: the original source page content is embedded.
- Edit title metadata, PMC company presentation, logo visibility, standard notes and tolerances. Confirm that template notes apply to the specific drawing; confirmation never changes canonical engineering validation.
- Use zoom/pan, Undo/Redo and Save. A browser recovery entry preserves unsaved edits when available. Reopening the document reads its saved state. A save conflict retains local edits and requires reopening/recovery rather than overwriting another window.

**Save presentation as template** stores the sheet/view/table arrangement and standard company presentation for reuse. A template does not copy source identity, schematic assets, table remarks or an old drawing number. Template notes must be reviewed again for each drawing.

## Manufacturing drawings

The default manufacturing document includes an overview, six face views with native U/V datum dimensions, straight internal sections, porting tables and a paginated machining schedule. Repeated coordinates share a dimension. Coordinates use the same global axes as Manifold Studio; opposite-side views retain their outward orientation and explicitly mark their datum. The schedule includes source step diameters/depths, conical/annular geometry, offsets, angled drilling axes, drill-point information and known closure information where available.

Plain blind/through **Mounting Holes** are authored in Manifold Studio. They cut the actual BRep, participate in wall/interference checks, and never create hydraulic nodes. A through hole explicitly terminates at the opposite stock face. This does not assert a thread, fastener compatibility or a specific tool-point shape. Unknown thread/plug/tooling details remain unresolved; the Drawing Workspace does not fill in missing Library manufacturing data.

Dense drawings can require manual finishing. The editor identifies text overlap and content crossing the printable area; the generated schedule does not silently omit remaining rows. Basic straight sections are included. Offset/stepped sections, automatic detail views and sophisticated layout optimization are enhancement work.

## Source updates and history

When the source project revision or build changes, the drawing is marked **SOURCE CHANGED**. **Update from Manifold** prepares a preview; only **Apply update** replaces the drawing. Cancelling/failing a job or declining the preview retains the saved document. Positions, scales, independent notes, valid annotation offsets and suppression records are retained. Tables and source captions follow the new source.

Deleted features, face changes, replacement definitions and ambiguous operation identities produce explicit broken references. Broken dimensions are excluded from the current drawing and block release until rebound or deleted. Repeating an update or duplicating a document does not clear that state. The original engineering snapshot remains available in save history.

A Project can contain multiple drawing documents. Drawing duplication creates an independent draft. Project duplication retains the existing manifold-only behavior; use Drawing duplication for another document within the Project. Project archive makes its drawings read-only until restored. Confirmed permanent Project deletion removes its drawings and drawing history as well; shared assets, Library data and immutable CAD builds remain.

## Release and export

**Export PDF** exports the saved drawing at actual paper dimensions, with embedded fonts, engineering vectors, appropriate line weights and sheet numbering. The source company logo is a print-resolution raster presentation asset. The PDF can be printed at 100% / Actual Size; printer “fit to page” changes the physical scale.

Drafts can be saved and exported for review even when issues remain. Release requires a current source, canonical engineering PASS, valid references/projections/assets and usable page bounds. Open blocking engineering reviews remain blockers. Permitted warnings require a written, attributed decision. Release records exceptions visibly in the PDF and retains original checks; it never changes `manufacturing_ready`, resolves a source review or grants pressure/manufacturing certification.

Released PDFs and their source/release records are immutable through the application and checksum verified on download. Create a new revision to continue editing. **Revision history** exposes prior issued PDFs and recent saved states; a historical state can be copied as a new draft. The prior released PDF is served directly, never regenerated as the same issue.

PDF is the supported final export in this scope. SVG is the shared editing representation; standalone SVG/DXF export, advanced reconciliation, a general template designer and complete Project packaging remain non-blocking enhancements.

## Local storage and verification

- Drawings and release/save history: `projects/drawings/` (local, Git-ignored).
- Reusable templates: `projects/drawing-templates/` (local, Git-ignored).
- Focused tests: `tests/test_drawing_workspace.py`, `tests/test_mounting_drawing_source.py` and existing store/Project tests.
- Reproducible fixtures: `scripts/drawing-fixture.py`, `scripts/drawing-density.py`; run with the repository on `PYTHONPATH` in `.venv`.
- Runtime dependencies: ReportLab and pypdf, pinned in project requirements. All CAD imports retain the existing `manifold.cad` boundary.
