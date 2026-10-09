# AI product and machining-interface role correction

Starting HEAD: `8a847481829de09630e29252d542dfbecd9647b7`.

## Actual cause

The operator's saved analysis `0c5a6f0af9b349349cf64cd2bbcd9b9f` completed in 44.08024 seconds using prompt v10. In seven component instances, the model put a cavity designation in the confirmed `model` observation and left `cavity` empty. Product codes such as RDDA and CBCG appeared only in display labels. The resolver trusted the observation field's role and queried only the cartridge catalogue for those designations, so every one reported `cartridge_identity_missing`.

T-10A is a machining cavity designation. A component is the mounted physical valve instance; its product model and cavity are independent identities. Renaming the error alone would not resolve this mismatch.

## General correction

- A confirmed complete model-field designation with no runtime product match is also checked against the existing typed cavity/mounting-interface catalogue. An exact interface match uses the same direct engineering-interface resolution already supported for explicit cavity declarations.
- This is not a special Sun/T-10A branch, a caption splitter, fuzzy search or a new compatibility relation. Known/ambiguous product identities retain their product semantics; ordering suffixes are not stripped. Display-label text and unconfirmed/inferred identity are never promoted to an executable identity.
- Explicit cavity/mounting declarations are intersected with any recovered interface designation. Conflicts, multiple physical variants, unavailable units, unusable geometry and unmapped hydraulic ports retain their existing blockers.
- Generation no longer presents or carries the recovered cavity designation as the product model. The analysis GET response adds separate current `identity_interpretations` metadata, and the analysis UI labels the observation as a machining interface. Saved source analysis and exported original facts are not rewritten.
- Candidate cards show unit, imported/custom/legacy definition category and actual profile machining depth. Unusable candidates have no Use action. This makes different same-name definitions distinguishable without hiding them or choosing an arbitrary geometry.
- Prompt v11 reinforces separate product/cavity observations even when a product code also appears in the display label, and distinguishes local port numbering from global hydraulic net names. Free-form drawing layout remains supported.

## Same saved analysis, before and after

No AI request or CAD generation was made during this correction. The same current input/run/revision was used for read-only API preflight.

| Instances | Old result | Current result |
| --- | --- | --- |
| RDDA upper/lower, T-10A | No product match, no choices | Cavity recognized; physical-definition choice required |
| CBCG left/right, T-11A | No product match, no choices | Metric cavity and numbered interfaces resolved |
| DSCS, T-31A | No product match, no choices | Cavity recognized; hydraulic mapping needs review |
| RBAA, T-3A | No product match, no choices | Cavity recognized; hydraulic mapping needs review |
| LRHC, T-17A | No product match, no choices | Metric cavity and numbered interfaces resolved |
| AH4D102a/f | No product match | Still no product/mounting identity supplied by this run |

Seven cavity instances now have real physical choices. The original nine generation decisions become six; the complete design is still not generation-ready. This report does not claim otherwise.

Remaining decisions: topology review; two T-10A physical-definition choices; DSCS and RBAA hydraulic mappings; AH4 mounting-interface selection. T-10A has two metric definitions with different geometry: imported profile depth 51.8 mm and legacy profile depth 130.905594 mm, plus an inch imported definition. They are not deduplicated by name. The source analysis also uses P/T on the RDDA and RBAA instances while the actual cavity windows are numbered; no automatic letter-to-number mapping is invented. AH4 has six extracted ports, so selecting an unobserved four-port mounting standard would not by itself resolve its topology.

## Verification and protected state

Python syntax/module loading and `git diff --check` passed. Vite build passed with its existing runtime-font and bundle-size warnings. Localhost and actual LAN health endpoints returned HTTP 200. The current run GET returned seven separate role interpretations; real browser interaction confirmed machining-interface labels in analysis and candidate/definition states in preflight. No test suites, added tests, provider calls, CAD builds or prove run were performed, respecting the prior verification restriction.

Before/after SHA-256 values are unchanged:

- Active engineering DB: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.
- Provider configuration: `2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`.
- Current real saved run: `c843bf8c77039dc871a2bf5e054edf67b542c7f7537d03b67aa813a5e6606646`.

No SQLite, routing, geometry, Drawing, model settings or compatibility policy changed. Final commit and verified remote HEAD are recorded in the completion reply.
