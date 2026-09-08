# PMC design workflow evolution

Preserve the existing BRep builder, exact rule engine, STEP roundtrip and immutable build store. Version 1 files remain readable; new intent and library metadata are additive. Original build snapshots remain untouched.

## This delivery

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

Multiple selection/group dragging and alignment, automatic exact candidate search around obstacles, angle/compound-angle drilling, detailed pressure loss and branch-flow simulation, pressure certification, vendor-specific threads/form tools, orifices, full O-ring/slot/undercut libraries, assembly STEP imports and dimensioned production drawings need dedicated engineering slices. This release ranks orthogonal proposals by length and plug count; it does not promise to find a valid layout for every arbitrary move. Do not label unsupported calculations as passing. The additive metadata and parent links support these extensions without replacing the physical core.
