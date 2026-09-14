# Common PMC title block correction

2026-09-15. Implemented against `780a3628719156f7c7d4194cf1b4ce0926fff536`, verified equal to GitHub `main` before editing.

## Change

The Customer default previously used the legacy title renderer. It now uses the PMC26-3092 first-page arrangement and the same PMC standard furniture as Manufacturing. `pmc_standard.py` owns the one shared implementation of the frame, stock summary, logo/company block, tolerances, alteration/revision grid, design signoff and title cells. `pmc3092.py` and `pmc3069.py` own their respective arrangements; `pmc_portings.py` shares source grouping, wrapped rows and continuation logic.

Customer uses six compact orthographic views and ISO, the source schematic in the upper-left, a two-column PORTINGS table lower-right, customer notes lower-left and an editable **FOR CUSTOMER REFERENCE ONLY** annotation above the title band. Dynamic values remain tied to the selected Project/build. Only actual table overflow adds sheets. Manual table placement is checked against the actual company block, so the lower-left drawing area remains usable.

Choose **Create Drawing → PMC Customer Drawing** for the new default. Previously saved/custom layouts and issued PDFs are retained, as with the prior Manufacturing correction. Source-update operations do not silently replace an engineer's chosen layout. No CAD geometry, canonical validation, Library data, provider configuration or isolated CAD execution was changed.

## Verification

- Drawing workspace and Store/API tests: **26 passed**. Subsequent table-placement checks: **2 passed**; default source-schematic/vector-PDF checks: **2 passed**. Four existing dependency deprecation warnings remain.
- Regression coverage checks identical furniture primitives for Customer and Manufacturing, A2/mm enforcement, dynamic metadata, customer-only body content, vector source schematic placement, source immutability, save/reopen, unchanged source-update/release guards, and lossless Customer PORTINGS continuation.
- `npm run build` passed. Only the existing font-URL and chunk-size build warnings were reported. No geometry implementation changed, so the full CAD proof/regression was not repeated.
- Actual browser: create Customer, edit title/quantity/notes, move the height dimension, undo/redo, save, switch drawings, reopen and verify retained notes/offset, download PDF. Screenshot: `output/playwright/customer-pmc-final.png`.
- The final browser PDF is one **594 × 420 mm** vector sheet, 152,878 bytes, and equals a fresh export of its saved drawing. Its layout was visually compared with PMC26-3092 page 1. An additional saved-source schematic example was rendered to verify the upper-left schematic slot.
- Re-exporting the existing three-sheet Manufacturing example through the common renderer produced a **byte-for-byte identical PDF** to `output/pmc3069-review/manufacturing.pdf`.

## Review artifact

`output/customer-pmc-review/customer.pdf` is the browser-exported review example. Project `8454af08a5744abc8c20bb26b1b95851`, Drawing `27f6d2146f1748f9b39d21a408886c0c`. The original Manifold/build is retained. This example uses explicitly illustrative Library definitions and remains Draft with the tolerance-review warning; it is a drawing-format review artifact, not an engineering release. Its source has no schematic, so no unrelated schematic is inserted.


## Local cleanup (2026-09-15)

The user requested deletion of generated test drawings and mock/sample data. The local review PDFs, test drawing documents, QA projects and acceptance template described above have been removed. The verification results above are historical; those example download paths are no longer available. Production drawing templates and automated regression coverage remain.
