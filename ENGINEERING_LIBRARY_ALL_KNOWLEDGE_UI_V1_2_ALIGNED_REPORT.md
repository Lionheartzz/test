# Engineering Library — All Knowledge, V1-2 aligned

Starting HEAD: `db17f0b4baf5bd932d216e233634a0bb0d42a105` on `codex/sqlite-domain-reset`. No reset. Final commit is the commit containing this report; literal final/remote SHA is recorded after push in `output/library-ui-v1-2/delivery.json` and the delivery message.

## Visible Library cards

One Engineering Library dashboard, one card template and one **Browse** action per card. Existing eight categories retained; twelve engineering categories added. Counts come from active SQLite, not UI constants.

| Card | Runtime definitions / identities | Knowledge | Default browse |
|---|---:|---:|---|
| Cavities | 6429 | 63 | Definitions |
| Cartridges | 15665 | — | Definitions |
| External Ports | 446 | 271 | Definitions |
| Threads | 833 | 122 | Definitions |
| Materials & Stock | 12 | — | Definitions |
| Tooling | 412 | 15 | Definitions |
| Closures & Plugs | 0 | 443 | Knowledge |
| Machining Modifiers | 326 | 18 | Definitions |
| Seals & O-rings | — | 1138 | Knowledge |
| Fittings & Adapters | — | 130 | Knowledge |
| Fasteners & Mounting | — | 84 | Knowledge |
| Hydraulic Fluids | — | 24 | Knowledge |
| Surface Treatments | — | 105 | Knowledge |
| Standards | — | 177 | Knowledge |
| Cross References | — | 415 | Knowledge |
| Inspection & QA | — | 12 | Knowledge |
| Manufacturing & DFM | — | 9 | Knowledge |
| Production Documentation | — | 15 | Knowledge |
| Commercial & Cost | — | 9 | Knowledge |
| Manufacturers & Suppliers | — | 9 | Knowledge |

**18/18 Main Station domains mapped exactly once: YES.** CAD is excluded. Unknown future domains get the neutral Additional Engineering Data card. No global research-progress panel or second Library dashboard.

## Engineer-facing presentation

- Friendly manufacturer/model, standard, designation and human-readable names. Generated/internal keys never render; an opaque navigation key is used only for fetching selected detail.
- Detail contains Engineering Data, with explicit field adapters rather than original-record dumps. Thread family distinctions remain; seals keep actual dimensions/units; tool dimensions stay attached to the named product; commercial prices remain dated supplier/quantity snapshots.
- Partial targets show **Partial data**. Research quality never changes runtime usability.
- Mixed categories use compact **Definitions / Knowledge** controls. Runtime definitions default first; Closures opens 443 knowledge records because runtime closure count is zero. Each mode retains independent search/page/scroll state through detail and return.
- Cartridge keeps compatible cavities and engineering properties; technical catalogue values are presented as model/series/option data where applicable. Relation-only identities show **Technical data not available**. Supplements show friendly identity and unavailable machining geometry, with no action.
- Material keeps properties and runtime stock. Treatment information and dated supplier catalogue sizes remain practical read-only data, separate from runtime stock.
- Dashboard uses one compact category request. Counts fail locally; if that summary fails, existing runtime category counts fall back without a blank page. Knowledge lists are paginated; details load only the selected item.
- Existing category CSS/grid/tokens retained; buttons bottom-aligned, no extra audit rows. Empty/nonmeaningful browse columns are omitted.

## Hidden from normal UI

| Content | Exposed |
|---|---|
| Evidence | NO |
| Sources | NO |
| Verification Scope | NO |
| Findings | NO |
| Conflicts / Variants | NO |
| Raw JSON | NO |
| Research gates / hashes / archive paths | NO |
| Internal record IDs | NO |

Underlying research and technical records remain intact. The prior relationship-audit component is no longer called by ordinary Library UI. No audit drawer or extra evidence buttons were added.

## Execution and data boundaries

- Selection workflows unchanged: explicit cavity/external-port selection bypasses knowledge endpoints, opens runtime definitions directly and retains existing callbacks, query defaults, management actions and usable checks. Knowledge rows have only View; no Place/Use/Bind/Generate/Select.
- Kernel changes: **NONE**. No AI, routing, placement, geometry, CAD, Drawing, project-schema, cost or validation-rule changes.
- No re-import, schema migration, execution-table writes, launcher change or production switch.
- Active database: `D:\Project\Manifold\data\pmc_engineering.db`, schema **v6**.
- Starting and final SHA-256 identical: `930531e852c73985a04415069253fda569045d332740201262b8ef226f5019a9`. Byte-for-byte equality proves all Library, technical, runtime and REV2 relation tables unchanged.
- Integrity before/after: `ok`. Foreign-key checks before/after: zero violations.
- Confirmed runtime counts: cavities 6,429; ports 446; threads 833; tools 412; closures 0; modifiers 326. Materials: 14 stored, 12 precise identities displayed (legacy behavior retained); runtime stock 268.
- Cartridge identities 15,665; technical Cartridge identities 15,005; relation-only 660. REV2 relations 16,066; execution-eligible 13,068; valid physical pairs 26,081. Generic knowledge targets 3,059.

## Read-only APIs

- `GET /api/engineering-library/categories`
- `GET /api/engineering-library/knowledge` (category, search, status and bounded pagination)
- `GET /api/engineering-library/knowledge/{key}`
- `GET /api/engineering-library/cartridges/{identifier}`
- `GET /api/engineering-library/materials/{identifier}`

Only UI-shaped fields are returned. Database opens read-only, SQL arguments are parameterized and input/page sizes are bounded. No archive/document access at runtime.

## Focused verification

- Focused Python/API: **6 passed** (`tests/test_library_presentation.py`, `tests/test_library_categories.py`). Temporary databases used for mutations; active v6 APIs additionally checked read-only.
- Focused Library JS: **12 passed** (`tests/library-ui.test.mjs`, `tests/library-knowledge-ui.test.mjs`). Includes cards, counts, tab/detail state, selection bypass, stale-response guard, local count failure, material return and Cartridge audit hiding.
- Vite build: **PASS** (existing bundle-size/runtime-font warnings only).
- `git diff --check`: **PASS**.
- Browser/screenshot/visual acceptance: **not run, delegated to user per explicit request**. No claim that desktop/1366/1100 screenshots were verified.
- No full Python/JS regression suite, CAD/prove or long Validate run.

## Remaining UI-only limitations

- Presentation intentionally uses an explicit engineering-field whitelist. Records with only identity or unresolved fields stay browseable and say additional engineering values are unavailable; unsupported pressure/compatibility is not inferred.
- Related commercial/tool examples are bounded to keep detail compact. No source-document or raw-record browsing is exposed.
- Visual alignment and responsive acceptance remain for the user. Reload the page after restarting an existing server process if it still runs the previous backend version.
- Machine-readable acceptance: `output/library-ui-v1-2/acceptance.json`. Database/source archives and screenshots are not committed.
