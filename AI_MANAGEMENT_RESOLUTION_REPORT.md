# AI Design management and engineering resolution

Implemented from `80ed6f17d3a62ea7da684f39eb8cb300a72c66e8` on `codex/sqlite-domain-reset`.

## Management

Studio/Home AI Design always opens **AI Design · Management**. Saved cards show title, document names/count, readable analysis status, generated draft count, updated time, Open and Delete. New AI Design and Provider Settings are primary actions. Detail navigation returns explicitly to Management. A completed analysis remains Completed when generation needs engineering decisions; the last checked preflight decision count is displayed separately in the session.

Dirty/new editors are retained in temporary Resume cards without auto-saving. Opening another analysis or starting another new editor preserves the pending editor. Upload/save completion and job completion cannot redirect Management into an old detail or lose newly uploaded document references. Async screen guards reject stale view updates.

`DELETE /api/ai-design/tasks/{key}` uses the existing local JSON/header/same-origin boundary. It validates the ID and resolved task-owned path, rejects queued/running analyze or generate jobs under the same guard used to enqueue jobs, then deletes the task JSON, task-owned analysis/generation directory and owned job result records. Shared assets, saved Manifold Projects/builds, SQLite and other tasks remain intact. Confirmation explicitly states that saved projects are unaffected; no title typing is required.

## Actual RDHA-LCN schematic

Used saved analysis `5c6769d0d15c4c78a81cd0fd4ef83217`, run `80cd97f2044247c29c7c659fdcdbf6c3`, original schematic asset SHA-256 `a6b511454517d487c04e96dc4974b223efc3ec0dca084021b67cea32896c4d3b`. The image was visually checked and the saved provider output was used unchanged; no new paid model call occurred.

- Recognized model: **RDHA-LCN**. Runtime match: **none**, diagnostic `cartridge_identity_missing`.
- Current runtime base identity **RDHA** exists: `cart_8e27b945035cfff5321ee1fe`, exact normalized model match.
- That base identity has one confirmed logical cavity, `ML:526d9a609824b717` / T-16A, with inch `cav_51d2bab12910069e6a83` and metric `cav_71a833387936be1b451d`. This relation is **not missing**.
- The missing connection is an imported, source-backed **RDHA-LCN → RDHA runtime identity/order-code alias**. Current linked full-part evidence establishes RDHA-LAN, not RDHA-LCN. RDHA-LAN resolves through that existing evidence to the same runtime ID. Source control/pressure/seal option lists and an XCN PDF rendering selector are not an explicit LCN identity connection; the resolver does not compose or strip suffixes.
- RDHA-LCN therefore has no automatically admitted cartridge ID/cavity choice. No compatibility was fabricated. The diagnostic identifies identity resolution rather than incorrectly claiming that the base cartridge lacks a cavity relation.
- The saved interpretation of **280** as component `crack_pressure` and both **12** values as `P1_bore`/`P2_bore` remains intact in analysis and preflight. The image states 280 bar and P,A:12 MM; the compact saved component facts do not retain those units, so no units or net pressure/rating claims were invented. Passage observations were not reinterpreted as BSPP nominal size.

Identity resolution is centralized: exact active runtime model/manufacturer, exact normalized runtime model, explicit sourced aliases/full-part applicability, and explicitly sourced base identity. Conflicted/unsourced aliases and generic product-family labels cannot establish a model identity. Multiple possible runtime identities remain ambiguous. Source-safe relationships continue to come only from the existing execution whitelist.

## G1/4 BSPP

`1/4 BSPP`, `1/4" BSPP`, `G1/4` and `G 1/4` normalize to **G1/4 BSPP**. Requested standard/nominal size and explicit pitch remain separate from passage dimensions.

Current DB results:

- **13** usable matching physical external-port records.
- **12** logical engineering-equivalence groups.
- One equivalent pair is `cav_8fb8e275d53f09bef99c` and `cav_e9f2fa58e420b75a4e36`; the canonical metric representative is **`cav_8fb8e275d53f09bef99c`** (stable ID tie-break).
- There is **no automatic overall canonical choice**, because other groups differ in actual machining/hydraulic/installation geometry or sealing family. For example, ISO 1179-1 variants have 20.7 mm versus 23 mm entry clearance and 25.4 mm/11 mm versus 20 mm/11.8 mm drilling recipes. Native inch versions also contain real geometric differences; unit preference does not erase them.
- P and A share one resolution object and one grouped decision. A browser selection of the canonical ISO 1179-1 group applied the same physical definition and one decision input to both ports.

The equivalence signature compares standard, nominal/pitch/thread-class semantics, source mm stages/cuts, hydraulic interfaces/offsets/clipping, sealing family, installation boundaries/clearance and required machining. It ignores display IDs/labels and primitive provenance names. Only equivalent executable choices are canonicalized by usability/activity, preferred native unit and stable ID. Different geometry, sealing or required tap classes remain distinct. Mixed standards remain available. Explicit user bindings win when compatible; an explicit BSPP requirement cannot become a straight bore or a different standard.

Default preflight decisions: **3 → 2** (one precise cartridge identity blocker + one grouped BSPP choice). After the explicit common BSPP selection: **1**, the LCN identity connection. No RDHA-specific relationship or fixed BSPP definition ID is hard-coded in the resolver.

## Verification

- **58 focused Python passed**, 2 CAD-heavy generation/preview cases deliberately deselected: management ownership/delete/queue guards, source-linked cartridge and port fixtures, actual saved analysis, existing AI admission/transport and manual binding tests.
- **13 focused JS passed**: management lifecycle/navigation/dirty state, async upload/save navigation, read-only technical facts and AI handoff/generation rendering.
- Actual isolated browser: Home and Studio entry, cards, Open/back/New, dirty Resume, Completed-versus-generation-decision status, queued/running deletion rejection, normal deletion, Project/shared asset/other-task preservation, actual RDHA-LCN grouped preflight and common BSPP selection. Screenshots under `output/playwright/ai-management/`: `management.png`, `rdha-resolution.png`, `grouped-port-choice.png`, `studio-management.png`.
- Vite and `git diff --check` passed. No long authoritative Validate, full CAD suite or proof run was performed.
- An adjacent existing Library-boundary JS assertion expects `unit=inch` catalog filtering. It also fails in a read-only archive of starting HEAD `80ed6f1`; it conflicts with the previously delivered mixed-standard preference behavior. Evidence: `output/ai-management/baseline-js.log`. This task does not change that workflow or weaken the assertion.
- SQLite schema remains **4**; valid compatibility pairs remain **24,948**; engineering DB SHA-256 remains **`4f208e1f9c6a9e263c5325a628a3df803677e3bc629e6e043cdfa168706384ba`**.

Changed scope: AI task service/jobs/API, centralized identity/library resolution and preflight, AI management/generation UI, focused tests and documentation. Routing, generation geometry construction, ligament/material/defaults, Project Settings, validation thresholds, STEP and Drawing are unchanged. Normal LAN service was reloaded while both lanes were idle. Commit, verified remote HEAD and clean-tree status are supplied in the delivery message.
