# Engineering Home redesign — 2026-09-27

Baseline: `7620e320cd0c7fcc5e96078d9d6fa2bb5860fbd9`, branch `codex/sqlite-domain-reset`. Implements the supplied `PMC_Guided_Home_Redesign_Plan_Codex.md`. This report supersedes the earlier, uncommitted marketing-style Home design and its screenshots.

## Exact files

| File | Change |
| --- | --- |
| `web/project-library.js` | Home composition, existing command proxies, Quick Setup prefill, recent-project table, search/pagination, native More popover and original project management contracts. |
| `web/home-view.js` (new) | Home-only navigation, service status, Quick Setup, AI entry and read-only Library search. |
| `web/home.css` (new) | Scoped engineering launchpad layout, table, responsive icon rail and inline SVG styling. |
| `web/main.js` | Import `home.css` only. |
| `web/library-ui.js` | Permit existing Library browsing without a draft; disable placement with a reason, guard optional project context. No new editor. |
| `web/workflows.js` | Guard remembering/placing definitions when no draft exists. Existing workflow architecture retained. |
| `tests/home-browser.run.js` (new) | Isolated real-browser acceptance for Home. |
| `scripts/check-home-browser.mjs` (new) | Reproducible browser runner, service/data isolation check, screenshots and JSON evidence. |
| `tests/library-ui.test.mjs` | Exercise both existing-draft and no-draft Library access. |
| `tests/interactive-preview.run.js`, `tests/preview-followup.run.js`, `tests/sizing-refine.run.js` | Replace old project-card selectors with search + table-row Open CAD. |
| `tests/phase4-browser.run.js`, `tests/phase5-6-browser.run.js`, `tests/studio-shell.run.js` | Update Home labels, search role and table navigation only; engineering assertions unchanged. |
| `README.md`, `docs/HOME_REDESIGN_ACCEPTANCE.md` | Usage and actual acceptance record. |

No changes to `index.html`, Studio/Drawing styles, Viewer, guided workflow internals, AI internals, backend, schema or SQLite records. The two Library guards above are the only existing-workflow code edits beyond Home wiring.

## Layout and command mapping

48px Home header; 190px desktop sidebar; remaining width for Quick Setup / AI, five project rows per page and Engineering Library search. At 900px the sidebar becomes a 62px icon rail with accessible names and native tooltips. Smaller screens stack the starting cards and scroll the project table within its own frame. Home styles hide the existing Studio header only while `body.home` is present. The Home sidebar is hidden during native workflow dialogs, absent from Drawing, and hidden upon entering Model.

| Entry | Existing destination |
| --- | --- |
| Home | Focus/scroll the current Home heading; no project reload. |
| New Manifold | `#project-new`, existing five-step guided workflow. |
| Model | Return to current draft, or `#project-new` when no draft exists. |
| Drawing | `#drawings-open`, preserving its save-before-navigation behavior. Disabled without a draft. |
| AI Design / Open AI Design | `#ai-design-open`; original upload/provider flow. |
| Hydraulic Nets | `#nets-open`; disabled without a draft. |
| Engineering Library | `#library-open`; browse without a draft, placement requires a draft. |
| Schematic | `#schematic-open`; disabled without a draft. |
| Engineering Review | `#review-open`; disabled without a draft. |
| Import Project | `#project-import`. |
| Return to current draft | Remove Home presentation and focus the existing Block command. |
| Project row Open CAD / Drawing | Original project-load / project Drawing URL, retaining dirty departure confirmation. |

Proxies invoke the original button once and honor its disabled state. Native dialog cancel behavior remains in charge; close returns focus to the visible Home trigger. More uses a native popover with keyboard navigation. Its rename/duplicate/archive/restore/delete commands retain expected revisions and exact-name deletion confirmation.

## Data and authority

Quick Setup defaults to the current guided dimensions, 160 × 100 × 100 mm. Unit switching preserves millimeters internally and presents mm/in consistently. Name, unit context, envelope and a selected real material's `display_name` are assigned to the existing first-step controls by accessible label and normal change events. Unit context is set first because the original workflow redraws its fields. The original five steps create the draft; Home creates no design and does not bypass net, port, cavity, mapping or review steps. If an expected field is unavailable, the existing workflow shows a visible fallback message.

| API | Home fields used |
| --- | --- |
| `/api/health` | Verified `service`, `network.mode` for LOCAL/LAN; failure is unavailable. |
| `/api/catalog/manifest` | Returned `schema_version` confirms the validated engineering DB response; no invented counts. |
| `/api/materials` | Active records' `id`, `display_name`; no hard-coded material catalog. |
| `/api/projects` | `id`, `name`, `block.length/width/height`, `features`, `status`, `updated_at`, `archived`, `revision`, `error`. |
| `/api/catalog?q=…&limit=6` | Real cavity names, family/thread, usability/reason. |
| `/api/cartridges?q=…&limit=6` | Real manufacturer, model and function. |
| `/api/threads?q=…&limit=6` | Real thread display names and family. |

Project dimensions are explicitly shown in stored mm, including inch-context projects. PASS, FAIL, STALE and SAVED DRAFT remain the backend's values; unreadable rows show UNREADABLE. Features use the existing total. No wall/clearance estimate, fake project template, pressure claim or dynamic CAD thumbnail is added.

Library quick search debounces and ignores outdated responses; at most six typed records are shown. This version uses the plan's permitted read-only result list plus **Open Engineering Library** fallback, without injecting a second query/editor workflow. Partial service failure is named explicitly. No summary endpoint was needed or added.

## Executed verification

| Command / check | Actual result |
| --- | --- |
| `npm.cmd run build` | Exit 0; Studio and Drawing built. Existing runtime Drawing-font URLs and large-chunk advisory remain. |
| `node --test --test-isolation=none tests/product-regressions.test.mjs tests/library-ui.test.mjs` | Exit 0; 11 passed. |
| `node scripts/check-home-browser.mjs` | Exit 0; five acceptance groups passed; zero page errors. |
| `git diff --check` | Exit 0. |

Browser groups exercise:

1. Desktop/narrow layout; five project rows and pagination; real material options; project mm dimensions, features and status; no initial Home preview/build requests or project writes.
2. Quick Setup name/unit/material/dimensions prefill; original New Manifold, AI and Import dialogs; native Escape/focus return; no-draft Library access and placement protection; real thread search with all three APIs and six-result limit.
3. More keyboard navigation; rename/duplicate/archive/restore; active/archive filter; cancelled/mismatched/exact-name deletion.
4. All five guided steps; draft creation; Home/Model return; dirty CAD and Drawing cancellation; explicit save; saved-project Open CAD; actual Drawing navigation; Home sidebar exclusion.
5. Project-service failure/retry preserving form input; no-match/empty states; delayed stale response; unavailable service/database/material fallbacks.

The browser runner supplies confirm/prompt answers in its isolated tab because native JS prompts interrupt Playwright CLI batches. Production prompt handlers are unchanged. Native `<dialog>` Escape is exercised normally. No external AI analysis is initiated. Drawing authoring/PDF, full import-file processing, native `beforeunload` acceptance, full engineering/browser suites and Python/prove were not rerun. Older browser scripts only received Home selector updates; their full flows are not claimed as newly verified.

## Data isolation and visual evidence

All browser writes use `127.0.0.1:8766`, the existing isolated server helper and `output/home-isolated/` (separate project/output paths, SQLite copy and provider configuration). Live Home at `127.0.0.1:8765` is inspected read-only. No normal saved project or immutable build was changed. Test data and screenshots are ignored local evidence, not tracked deliverables.

```powershell
.\.venv\Scripts\python.exe scripts/phase4-isolated-server.py --data output/home-isolated --port 8766
node scripts/check-home-browser.mjs
```

Both required screenshots were opened and visually inspected. At 1366×768 and 900×800, Quick Setup, AI entry, five project rows and the Library search are visible in the initial viewport, without whole-page horizontal overflow. The 900px icon rail does not squeeze the project action buttons out of view.

- [Home 1366×768](../output/playwright/home-redesign/launchpad-1366x768.png)
- [Home 900×800](../output/playwright/home-redesign/launchpad-900x800.png)
- [Live Home 1366×768, read-only](../output/playwright/home-redesign/live-home-1366x768.png)
- [Machine-readable acceptance](../output/playwright/home-redesign/acceptance.json)

Model, Drawing, AI and engineering workflow layouts were not redesigned. Save/Validate, optimistic revisions, build pointers, geometric calculations, project schema and SQLite engineering schema remain unchanged.
