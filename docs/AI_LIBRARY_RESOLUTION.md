# AI component identity to manifold draft

Successful hydraulic analysis is distinct from cavity selection. A recognized model name does not define its machining geometry or installed hydraulic interfaces.

The current path is:

1. Use confirmed schematic identity or an explicit engineer review. Inferred labels and selection preferences do not become authoritative product identities.
2. Look for a documented/engineer-confirmed cartridge relationship in available PMC/project definitions, or an exact confirmed source cavity designation in the converted catalog. Native footprint-to-parent links describe source machining/mounting records; they are not automatically cartridge compatibility declarations.
3. Require one usable, non-demo, dimensionally mapped candidate for automatic selection. Multiple matches or unreviewed geometry require a decision.
4. Require a complete, unique schematic-port-to-library-window mapping. Exact numbered labels can map automatically. Generic inlet/outlet labels cannot be guessed into port1/port2, and matching only the port count is insufficient.
5. Apply existing generation preflight, exact CAD validation and engineer review. Explicit manual choices still require their source hash, a complete mapping and an engineering decision.

## Current saved-analysis audit — 2026-09-12

The successful local Agnes analysis contains these source-backed model claims:

| Model | Model provenance | Source cavity | Saved schematic port labels | Current Library result |
|---|---|---|---|---|
| RDHA-LCN | Schematic / confirmed | Unknown | inlet, outlet | No matching record or trusted cartridge-to-cavity relationship |
| CA100 | Schematic / confirmed | Unknown | inlet, outlet | No matching record or trusted cartridge-to-cavity relationship |

The audit searched the current converted data across both units: 2,477 metric and 841 inch cavity records; 3,915 metric and 1,649 inch footprint records. Exact names/OEM names and catalog queries found neither model. There were no available preferred PMC or linked-project definitions for this task. Broad text occurrences resembling CA100 were checksum fragments, not product records. This is a statement about local coverage, not about whether these products exist in a vendor catalog.

The identity filter is not the blocker: both model values reach the resolver. Missing trusted relationships prevent choosing a cavity; generic port labels would additionally require documented window mapping even if a cavity were selected. No compatibility, family/suffix alias, dimensions or inlet/outlet numbering were invented.

The saved analysis can be reused, but cannot currently generate a complete manifold draft automatically. Supply/confirm the correct existing-library cavity for each product, document the cartridge relationship and verify all hydraulic windows. A new AI call is not required to resolve a Library coverage gap. Successful extraction does not establish that every symbol/port interpretation is correct; the saved analysis also retains its unresolved source-review items.

## User-facing preflight behavior

Each component now receives a resolution code, explanation and required action: identity needs review, relationship missing, ambiguous candidates, geometry needs review, window mapping required, resolved, or manual selection. Trusted unambiguous cases continue automatically.

Generate shows a checking state and prevents simultaneous edits during preflight. If blocked, it explicitly reports **Draft not generated**, lists the reasons, and moves focus to that explanation. It does not silently redraw the same screen or start a background generation job. Cavity search, candidate selection, mapping decisions and recheck remain available.

Local audit evidence is retained in `output/library-resolution-real-before.json`; real browser screenshots are under `output/playwright/library-resolution-*.png`. These local artifacts contain no new provider request or fabricated Library relationship.
