# PMC design workflow evolution

Preserve the existing BRep builder, exact rule engine, STEP roundtrip and immutable build store. Version 1 files remain readable; new intent and library metadata are additive. Original build snapshots remain untouched.

## This delivery

The current startup is a local project library, not an automatically opened demo. Named projects have independent optimistic revisions, history and build pointers under `projects/saved/`; the legacy demo remains a developer fixture. New Manifold selects cavities/cartridges before placement, with unknown compatibility recorded for review. Direct generated-route inspection and refinement reuse the existing circuit geometry; conservative branch extension is followed by exact draft checks. Soft wall-margin ranking supplements, and never replaces, minimum-wall validation.

1. Named hydraulic nets, schematic components, constraints and pinned cavity revisions above physical drillings.
2. Local schematic assets with content hashes; an explicit Codex request package. The web app cannot call the tools of the currently running Codex task. A copied request references local assets and a revision-pinned project snapshot; Codex reads it and writes a proposal through the same project model.
3. Searchable shared cavity catalog and guided definitions; insert, replace, copy, remove, suppress and face change using normal UI. Parent offsets and rotation are inspectable.
4. Face-constrained dragging with envelope-aware limits, snapping, live position and dependent route preview. Release retains a local draft; Save & Validate performs the exact build and validation. Old PASS is historical immediately after an edit.
5. Relationship-derived orthogonal candidate routing with real construction drillings/plugs; manual overrides remain explicit. Candidate estimates are not validation results.
6. Exact schematic/net conformance, flow velocity screens, machining identifiers and derived machining/plug/meet lists.

## Functional references

- [MDTools i2025 command reference](https://www.vestusa.com/Help/MDTools-i2025/Part_Model_Commands.htm): library insertion, constrained parent/child movement, connections, relocation, net review and engineering checks inform the separation between intent and machining implementation.
- [MDTools 985 overview](https://www.vestusa.com/Manifold-Design_MDTools-for-SolidWorks.htm): working/dead-area review, tooling knowledge, velocity review and derived manufacturing information inform the next stages.
- [MDTools 985 cavity editing](https://www.vestusa.com/Help/MDTools-985/Edit_Cavity1.htm): keep exact machining values inspectable and distinguish component identifiers from machining identifiers.
- [VEST schematic export](https://vestusa.zohodesk.com/portal/en/kb/articles/exporting-manifold-data): keep component IDs, interface definitions and hydraulic net membership as structured intent rather than reconstructing them from drill colors.

## Later capabilities

Multiple selection/group dragging, general multi-terminal angled route search, detailed pressure loss and branch-flow simulation, pressure certification, vendor-specific threads/form tools, orifices, automatic application of every source O-ring/slot/undercut recipe, assembly STEP imports and dimensioned production drawings need dedicated engineering slices. This release supports exact manually authored straight angled drillings and bounded two-terminal angled proposals, plus optional alignment. It screens orthogonal detours and compares a bounded set with exact CAD validation; it does not promise to find a valid layout for every arbitrary move. Do not label unsupported calculations as passing. The additive metadata and parent links support these extensions without replacing the physical core.


## Editable project and native catalog extension

- Import/export uses additive schema version 1, complete pinned cavity definitions, origin metadata and structured review decisions. JSON admission is limited to 8 MB; schematic assets remain separate SHA-addressed files.
- Catalog data comes only from converted v0.5 engineering directories. Metric and Inch source records remain lossless. Footprints remain separately identifiable related records; their explicit cuts and interface offsets rotate with the parent cavity. Tools, grooves, envelopes and materials can be pinned as engineering resources.
- Source cylinders, conical seats and explicitly mapped annular cuts map to exact CAD primitives, including shifted/rotated footprint cuts. Standard Steps 1–11 use Step 0 depth as datum. Sun locating-shoulder records remain provisional; special features requiring additional interpretation remain draft projections. Threads and machining recipes are retained independently of geometric validation.
- `imported-dimensional` is checked against reproducible mapping from pinned native records, without a live catalog dependency. `engineer-mapped` and reviewed machining each require a recorded decision. A schema-valid record alone does not prove a physically correct cavity.
- Shared edits create content-addressed PMC revisions. Catalog deletion is reversible and does not delete old project/build pins. Editing a project pin changes the current draft only, requires new interface mappings, and marks affected schematic components unconfirmed.
- Exact route optimization retains each candidate, including CAD failures, under `output/optimizations/`. It does not commit the project or relax validation. The current search is bounded and incomplete.
- Source boundary role, shape type, raw syntax and hash are preserved. Closed line loops and verified full-circle records support exact faces/extrusions. Independent assembly envelopes require an explicit engineer-selected cavity association and role; unsupported syntax remains unmapped. See [source audit scope](MDTOOLS_SOURCE_AUDIT.md), including the pending original MDB inspection.

Depth convention references: [VEST cavity modeling](https://www.vestusa.com/Help/MDTools-775/Modeling_Cavities.htm) and [VEST Library Manager manual](https://www.vestusa.com/Download/MDTools-Library-Manager-2018-User-Manual.pdf). These explain source conventions; they do not certify this implementation or any imported dimensions.
