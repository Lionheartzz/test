# Closure / Plug runtime integration

## Result

Starting HEAD: `8bdc443b1acb22c9f673568e65cee428a1811173`, branch `codex/sqlite-domain-reset`.

38 source-backed, usable closure definitions are now in the active `data/pmc_engineering.db`. The real `tests/fixtures/automatic-t10a.json` automatic proposal has 11 plugged construction drillings, all resolved. Final active-database exact verification: **638 PASS / 0 WARNING / 0 FAIL**, `manufacturing_ready=true`, `unresolved_plug_entries=[]`.

Production BRep is valid and contains one solid. STEP reimport is valid and contains one solid; volume delta is **0.0017379187047481537 mm³**, below 0.01 mm³. The final exact geometry/rules/STEP verification took **21.77 s**; this is not a full global route-search timing.

## Actual source admission

The original metric and inch MDTools R2 PLUG MDB files were opened read-only through the existing ACE reader. Both `ConPlugTable` and `PlugFilePath` contain zero rows in both files; the older converted plug index is also empty. However, the existing runtime external-port catalogue contains 41 usable metric MB-series plug-hole definitions. This integration reuses **38** of those exact construction definitions and adds **zero** construction ports.

Official SFC KOENIG product dimensions and installation evidence already linked in the handoff identify the matching current MB products. Admission requires exact product identity, complete dimensions, installation evidence, and an unambiguous usable construction-port match by model plus d2/l3/d3 geometry. VERIFIED alone is insufficient. Legacy-family references may point to a documented current product; that does not establish or promote the historical legacy product identity.

| Knowledge target classification | Target references |
| --- | ---: |
| Runtime-ready with unknown/conditional rating | 66 |
| Partial identity | 63 |
| Reference-only legacy identity | 41 |
| Missing machining, engagement or envelope | 273 |
| Total knowledge targets | 443 |

The 66 ready references deduplicate to 38 actual products; 28 duplicate references collapse. The remaining **377 target references** stay knowledge-only. Product counts and target-reference counts have different grains. Original knowledge states remain 380 VERIFIED and 63 PARTIAL; all 443 remain browseable.

Source PDFs were read directly from the existing handoff archive, without a knowledge reimport:

- `SFC_Koenig_Installation_Instructions_MB.pdf`: SHA-256 `d127bf46e35a33f7a7e2cfa2175ca7b01c4996668af7781f420074ab391433cd`.
- `SFC_Koenig_Catalog_4095_2024.pdf`: SHA-256 `a5ac43ed9df42e88b72af277f8460e04abd5733b42ffbf228f9e897355c9999a`; MB600 dimension drawing, PDF page 22 / printed page 20.

Engagement uses source **l1 sleeve/body length**, not setting stroke S. Entry machining uses source d2, minimum l3, maximum allowed d3, and the 120° transition. Installed-envelope height is zero because the sleeve must not protrude and the set ball lies below the surface. Its radial bound uses source d2 plus the documented 0.1 mm hole tolerance. The installed envelope does not claim a setting-tool clearance envelope. Proper setting tools and source installation conditions remain required; pressure rating is unknown rather than inferred from conditional material tables. No inch SKU is invented.

## Runtime behavior

Automatic construction holes bind a deterministic compatible closure before screening and when route variants are regenerated. The catalogue caches normalized runtime definitions; it does not scan 443 knowledge records per candidate. Unit/model/identity provide stable selection, without nearest-diameter guessing. Existing manual/frozen unresolved holes retain their behavior. An invalid explicitly selected closure is retained and fails rather than being silently replaced.

Selected source engagement drives plug exclusion. Source counterbore and transition are actual local cutting geometry. In the real example an 8 mm hydraulic bore remains 8 mm; MB600-090 supplies 10 mm engagement and a local 9 mm nominal entry with source tolerance and depth. The entrance is widened locally; the hydraulic bore is not enlarged throughout.

Resolved closures receive `construction_closure` PASS. Missing closures remain WARNING; incompatible/invalid selected closures FAIL. No warning suppression, universal dummy plug, minimum-wall change, cavity protection relaxation, or pressure certification was introduced.

The plugged-drilling inspector has a small friendly Closure / Plug selector. Selected engagement is authoritative. Library/API expose **38 definitions + 443 knowledge targets**. Private entry-profile metadata does not become ordinary Library machining clutter.

## Database preservation

The active database remains schema **v6**. Only 38 rows were inserted into `closure_definitions`; size growth is **77,824 bytes**. All other **46 tables** have identical sorted logical row hashes before and after activation. Foreign-key violations: 0; integrity check: `ok`.

Backup: `output/closure-runtime/active-before.db`.

- Admission source file SHA-256: `930531e852c73985a04415069253fda569045d332740201262b8ef226f5019a9`.
- Activation backup SHA-256: `d578386d7e277a3865a3a9527df24824aa6254ba1f63ffa9ae5623d849b98579`.
- Active file SHA-256 after activation: `b03c98523113cbca26258ce6c48dda491ff589a5ef38635a9e4ab93cc86e14d7`.

File hashes identify distinct physical SQLite snapshots; preservation is established by the 46 unchanged logical-table hashes, not byte identity between SQLite backups.

Activation, per-table hashes and actual acceptance results are retained locally in `output/closure-runtime/activation.json`, `admission-verified.json`, and `active-real-validation.json`. Databases, backups, PDFs, CAD and generated artifacts are excluded from the commit.

## Focused verification

- Python: `tests/test_closure_runtime.py` and `tests/test_route_plug_screen.py`: **16 passed**. Includes source admission, incomplete/ambiguous rejection, real geometry, legacy WARNING, invalid-selection FAIL, JSON roundtrip, deterministic binding, and API/Library counts.
- JavaScript: `tests/closure-selector.test.mjs`: **2 passed**, including stale-response guarding and legacy unselection behavior.
- Vite build: PASS.
- `python -m manifold prove --out output/closure-runtime/proof-release`: PASS. Original deliberate invalid case remains 6 FAIL; corrected case has 0 FAIL and its original manual unresolved closure WARNING remains visible.
- `git diff --check`: PASS.
- Active database health and closure browse APIs: PASS.
- Browser screenshots and visual interaction acceptance were not run, following the user's prior instruction to perform that inspection personally. No broad regression suite was run.

Incremental real-fixture P-port move: cold baseline **1.31 s**, final **1.72 s**. Only P recomputed; A/T/B remained byte-equivalent, without conflict expansion. Local source-shape caching and reuse of per-bore closure bounds removed repeated filesystem lookups. No global exact search or STEP export was added to drag preview.

## Changed files / delivery

Added `manifold/admit_construction_closures.py`, `manifold/closure_runtime.py`, `web/closure-selector.js`, and their two focused test files. Modified `manifold/engineering_db.py`, `geometry.py`, `manufacturing.py`, `route_state.py`, `routing.py`, `schema.py`, `server.py`, `validation.py`, and `web/main.js` only for closure admission, binding, local machining, checks and selection. Schema tables and version were not changed. Unrelated kernel changes: NONE.

The commit containing this report is the delivery commit. Its SHA and the verified remote HEAD are reported with delivery and saved locally in `output/closure-runtime/delivery.json`. Restart the running service and refresh the browser to inspect the new selector and definitions.
