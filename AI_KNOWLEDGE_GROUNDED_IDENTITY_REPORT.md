# Knowledge-assisted product and interface identification

Starting HEAD: `945aeb51073686b9fd7d84561e290856a6e0c6a5`.

## Confirmed cause

The real saved v11 run `9f2ff960c3114e968aeb39250cbb14e4` completed in 66.48894 seconds. Seven component `model` fields contained cavity codes; actual cartridge codes were absent even from their display labels. Those codes already exist in the current SQLite master. The previous correction only recovered an interface role after extraction; it could not restore product text that the model omitted.

Before this change, reference context was mainly materials plus a few cartridge identities queried from the user's engineering-requirements text. Schematic captions were not looked up before classification. Production admission also called a disconnected Knowledge Base placeholder.

## Implemented pipeline

The next operator-initiated analysis uses prompt v12:

1. The existing configured model reads complete original identity captions, including product codes, cavity codes, mounting/port standards and suffixes, without assigning their roles first.
2. A local read-only index retrieves exact and similar identity fields across the existing SQLite runtime, Technical and Main Station data.
3. The same model receives those references together with the source images and original requirements, then separately fills product model, cavity/mounting interface and function.

There are two planned AI requests. They share the original timeout and the original **total** contract-retry allowance. Current configuration remains 300 seconds / zero retries. No model, key, token, reasoning, streaming or JSON setting changed. No paid request was made during implementation.

Original source captions are retained separately and attached to component records through caption ordinals. They remain viewable even when a code is not classified; unassigned captions require review. Existing product facts are not replaced by an interface. Near matches, inactive records and evidence-only records are reference context, never execution authority. Function descriptions use the central engineering fact resolver; unresolved function data remain unresolved. Exact runtime identity admission replaces the disconnected placeholder. Compatibility, units, usable geometry and hydraulic port mapping retain their existing checks.

## Read-only lookup evidence

The index searched these actual table counts:

| Table | Rows |
| --- | ---: |
| cartridges | 15,665 |
| cavities / mounting interfaces | 6,429 |
| technical_identities | 15,022 |
| library_targets | 3,059 |
| library_records | 80,075 |
| external_port_definitions | 446 |
| thread_definitions | 901 |
| materials | 14 |
| closure_definitions | 103 |
| closure_products | 45 |
| tool_definitions | 546 |
| machining_modifiers | 326 |

Read-only queries using actual annotations from the supplied schematic found the correct separate roles for RDDA / T-10A, CBCG / T-11A, DSCS / T-31A, RBAA / T-3A and LRHC / T-17A. None is hard-coded into the implementation. Exact product fields rank before generic manufacturer matches. Standard interface aliases reuse the existing catalogue.

The final five-caption lookup measured approximately 4.264 seconds cold and 1.059 seconds warm. Earlier repeated field normalization was optimized with a bounded field-name cache. The per-process identity index is invalidated by engineering-DB path/mtime; no archive/PDF/MDB scan or second database is introduced. Retrieved text is bounded by role, with returned/total counts and explicit long-field truncation metadata; the original source captions retain their complete text.

## Verification and limits

Python syntax/module loading, relevant Vite build and `git diff --check` passed. Localhost/LAN health and provider-registration checks returned successfully. The existing saved run continued to load. Browser checking is limited to the real existing analysis and the two-stage entry explanation; no new analysis or synthetic production result is created.

No tests were added or run, no CAD/prove checks were run, and no paid AI request was issued, respecting the existing verification restriction. These checks verify local retrieval and integration, not the configured model's next response quality. The old v11 run remains unchanged; its missing product text is not fabricated into it. Fresh source reading requires the user's next Start analysis.

Protected before/after SHA-256 values:

- Active DB: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.
- Provider configuration: `2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`.
- Original v11 run: `dcd68a71f2004ef2511b7d841f43658ddc207b3e287f36a7019e85ea25ffc9cb`.

No SQLite schema/data, geometry, routing, Drawing or saved project changed. Final commit and verified remote HEAD are recorded in the completion reply.
