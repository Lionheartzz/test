# V2.3 implementation work record

Baseline ac238b5. Approved plan V1.1: section 16.1 required, section 16.2 non-blocking. User authorized committing and pushing this implementation to GitHub on 2026-09-13. The earlier reference-page prerequisite was withdrawn by the user on 2026-09-14. No Agnes or provider/configuration changes.

## Current result

Shared Customer / Manufacturing Drawing Workspace is implemented. Complete evidence and the required DoD matrix are in [V23_ACCEPTANCE.md](V23_ACCEPTANCE.md); operation guidance is in [DRAWING_WORKSPACE.md](DRAWING_WORKSPACE.md).

- Full Python regression: 228 passed, 4 warnings, 346.57 s after substantial completion.
- Final drawing/mounting focused set: 16 passed, 4 warnings, 16.31 s after finishing fixes.
- Additional source movement / replaced-ID regression: 1 passed, 4 warnings, 4.48 s.
- Existing frontend unit tests: 8 passed, 0 failed (Node --test-isolation=none).
- Production frontend build and git diff --check passed.
- Final engineering proof: output/proof/20260913-162632; intentional invalid 6 FAIL / 264 PASS, corrected 0 FAIL / 238 PASS. Earlier proof retained.
- Browser verified both drawing creation/edit/save/reopen/export flows, actual pointer drag, dimensions, undo/redo, source-change/update preview/apply, invalid section failure and recovery, A release/B revision/history, custom template reuse, dense drawing editing and table finishing.
- Dense source: 120 explicit plain bores, canonical PASS, 15 sheets / 318 annotations. Reused-build drawing generation 2.364 s and PDF 1.369 s. Final generated PDF 694898 bytes. Editing does not rerun CAD.

Final review fixes include immutable release preview/history PDF behavior, retained broken flags on copies, through-hole extent after parent face resolution, honest save-completion state, source-following captions, rotated offset machining information, cylindrical default-zero suppression, and pinned machining notes/tooling.

## Local evidence

All fixtures belong to this task. Primary Project cbd87da8584c43a895e33a747c794a67, current build afb5e8f3ac08437cbff611722e6d3af2, 35 PASS / 0 WARNING / 0 FAIL after adding a real plain through mounting hole at U20 V20.

- Customer drawing 0e37f666a6f04ec4b1164736d30be9ff: released A, now editable B, updated from latest source; note/manual diameter/top scale retained.
- Manufacturing e1eff2c896e64694be3c8ed499b6fe8e: created and finished via browser, 9 sheets, note dragged to 64.7 / 266 mm and persisted.
- Custom-template copy 372648d926ba42b0bc38861f4e86a77b.
- Dense Project d9cea672dfb946a89183fe7b773786e4 / Drawing 6de8adb6d64c446e928c13091c67902d; H1 leader manually adjusted and saved. Initial benchmark drawing retained too.
- PDFs / logs / screenshots: output/drawing-acceptance/. Reference renders: output/v23-reference-review/.

The local application runs at http://127.0.0.1:8765. Browser session pmc uses scripts/browser.ps1; local browser control requires the already-used sandbox escalation. Do not edit production projects or repeat the 120-hole CAD build unnecessarily: scripts.drawing-density supports --reuse-project.

## Manufacturing template correction — 2026-09-14

The user withdrew the earlier missing-reference-page prerequisite and requires PMC26-3069 as the default manufacturing template. The sparse manufacturing output described above is historical and superseded. New generation uses three A2 sheets, each with all six faces, source-driven PORTINGS and the measured PMC title/notes/company arrangement. Legacy saved documents remain intact.

See [PMC3069_MANUFACTURING_TEMPLATE.md](PMC3069_MANUFACTURING_TEMPLATE.md) for the implementation, final 24-test focused regression, browser checks and review PDFs. The 120-hole source now fits three sheets / 519 annotations. The new PDF is ready for user review. The user authorized committing and pushing the correction to GitHub on 2026-09-14.

Non-blocking enhancements are explicitly listed in V23_ACCEPTANCE.md: standalone SVG/DXF, advanced sections/layout/reconciliation, generic template designer, full Project packaging. Do not label these as shipped.
