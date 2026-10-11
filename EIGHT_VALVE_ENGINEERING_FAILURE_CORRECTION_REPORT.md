# Eight-valve engineering failures: source review and admission correction

Starting HEAD: `80490e5afd2a8cfe00d49d193afa0509b1a53611`.
Branch: `codex/sqlite-domain-reset`; starting worktree clean.

**Overall engineering acceptance is NOT achieved.** The original nine failed
checks disappear in the corrected topology/MB-position proposal, but routing
that topology in the old layout produces new failures. That proposal is rejected,
not applied. No saved project, original analysis, database or previous successful
route candidate was changed. No zero-FAIL or manufacturing approval is claimed.

## Authoritative case and source

- Saved project: `projects/saved/2b93c6c68df24d5ebe543215e8e91c99.json`.
- Final original checks: `output/runtime-checks/ma-preview-eb4a637705d3460193f437117048d7e5/interior-engineering-validation.json`.
- Original independent route: same directory, `interior-selected-proposal.json`.
- Analysis task `343f91fdb98c435296b6e78322157433`, completed run
  `56b8948590f54068b01819b37a78f261`, generation
  `1e6e1a98e1624606b6d2799ec0edb30b`. The matching saved run and its generation
  options/mappings were read, rather than rerunning recognition.
- Original uploaded image: `projects/assets/c4c46210af107c60ae02b3c50cd15f6338ca450d2bd2e6a9b36a76e7d3be9a3c.png`,
  150193 bytes, verified against the task's SHA-256. Requirements text is empty.
- SQLite source cuts, zones, cartridge identities and `cartridge_cavities.valid=1`
  relationships were read directly. Those relationships establish compatible
  machining, not unconditional internal hydraulic joins.

Full check rows, source window dimensions, original member lists, compatibility
rows and corrected assignments are in
`output/runtime-checks/eight-valve-nine-fails/nine-failure-inventory.json`.
All output paths below are under that same new, independent directory.

Component aliases (the saved feature identities are unchanged):

| Alias | Saved feature | Product / machining interface |
|---|---|---|
| C1 | `CV_655e4e902088d9b3d1a4` | RDDA / T-10A, top symbol |
| C2 | `CV_2f5f4100438ea8dc43c7` | RDDA / T-10A, middle symbol |
| C3 | `CV_dd5023b2cc1f5540d5ca` | CBCG / T-11A, left |
| C4 | `CV_d1333085c2c3a05f37e2` | CBCG / T-11A, right |
| C5 | `CV_2f610693143c42689d69` | DSCS / T-31A |
| C6 | `CV_6f47e590ff80269d24f8` | AH4D102a/f / selected 4401-05-04-0-94 mounting interface |
| C7 | `CV_0265b7a321ed49f15fab` | RBAA / T-3A |
| C8 | `CV_e2172371eed05e894289` | LRHC / T-17A |

## Nine-row failure inventory

Every original `connected_interface` row has actual neighbours **0**, required
at least 1. Each listed original net has **one member**. These are actual
disconnections in the saved physical design, not merely display warnings.

| # | Exact rule / item | Original net | Source finding and correction in separate proposal | Re-evaluated original check |
|---|---|---|---|---|
| 1 | `connected_interface`, C1:port2 | `MA_RDDA1_pilot` | Category A. Upper RDDA's left port2 joins the MA vertical rail. C1:port1 instead joins MB; the old MA assignment to port1 was also wrong. | PASS, 1 neighbour |
| 2 | `connected_interface`, C2:port1 | `MA_RDDA2_pilot` | A. Middle RDDA's left port1 joins that same MA rail. C2:port2 remains MB. | PASS, 1 neighbour |
| 3 | `connected_interface`, C3:port3 | `MA_CBCG1_pilot` | A. Left CBCG port3 follows the descending diagonal to the right work line, directional B / DSCS port4 / right CBCG port2. It needs real B_DC drilling. | PASS, 1 neighbour |
| 4 | `connected_interface`, C4:port1 | `MB_CBCG2_pilot` | A, with an additional recognition/mapping error. The right symbol's top port is **1**, side port **3**. AI labelled C4P1 as 3 and C4P3 as 1. Correct labels and source-window mapping: physical port1 → MB, physical port3 → A_DC. | PASS, 1 neighbour |
| 5 | `connected_interface`, C5:port4 | `T_DSCS_pilot` | A. DSCS port4 joins the right work line B_DC. It is not an independent tank/pilot circuit. DSCS port2 joins A_DC. | PASS, 1 neighbour |
| 6 | `connected_interface`, C6:t_T | `T_DC` | A. Directional T runs down, right at the elbow, then into **LRHC port3**. Keep T_DC distinct from tank T; correct C8:port3 from P to T_DC. | PASS, 1 neighbour |
| 7 | `connected_interface`, C7:port2 | `T_RBAA_pilot` | A. RBAA port2 joins the right tank rail and LRHC port2. RBAA port1 instead joins DSCS port3 on a separate SHUTTLE_OUTPUT line. | PASS, 1 neighbour |
| 8 | `cavity_protected_region`, C2 / `PORT_5169719ee45688e50b29` | MB | Same physical contact as row 9. Exact source-window subtraction finds **0 mm³ outside port2**; the original 2.40552 mm³ protected result arose with no allowed declared window. Remove the unplanned tip contact by moving MB in the proposal, not by relaxing protection or adding a declaration. | No overlap; corresponding wall check PASS |
| 9 | `declared_connection`, C2:port2 / `PORT_5169719ee45688e50b29` | MB | Unplanned functional-port drill-tip contact, not an automatic route feature. No declaration was synthesized merely from matching MB labels. Same MB move eliminates this contact. | Contact absent |

All seven original rows are category A **after individual source tracing**;
they are not all pilot functions. No category B internal connection was assumed,
no extra external pilot port was invented, and no isolated net was deleted as a
warning-suppression measure. A separate category D interface exists at C5:port1.

## Source tracing and corrected topology

Pixel coordinates refer to the hash-verified 589 × 945 original image. Lines
were inspected locally; no paid AI recognition was invoked.

| Proposed net | Source line / junction evidence | Physical terminals |
|---|---|---|
| MA | Left rail x182 from top MA boundary through the two RDDA branches to CBCG left top | EXT1, C1:2, C2:1, C3:1 |
| MB | Right rail x321 from top MB boundary through the two RDDA branches to CBCG right top | EXT2, C1:1, C2:2, C4:1 |
| A_DC | Left work line x182, y434–631; right CBCG side diagonal reaches the left branch near x245/y479 | C3:2, C4:3, C5:2, C6:A |
| B_DC | Right work line x321, y434–631; left CBCG side diagonal reaches the right branch near x270/y479 | C3:3, C4:2, C5:4, C6:B |
| P | P boundary x136 to y783 and directional P vertical x270; LRHC left port1 | EXT3, C6:P, C8:1 |
| T | Tank boundary x458; RBAA right port2 and LRHC right port2 | EXT4, C7:2, C8:2 |
| T_DC | Directional T at x284 to y727, elbow to x324 and down to LRHC control port3 | C6:T, C8:3 |
| SHUTTLE_OUTPUT | DSCS lower port3 x258 to y588, across to x399 and down to RBAA left port1 | C5:3, C7:1 |

The crossed CBCG diagonals are not joined to each other. No valve's switched
functional flow path was treated as a permanent manifold drilling connection.

DSCS's four-window **cavity** does not imply four used cartridge connections.
The source symbol exposes 2/4/3. Sun's official
[International Shortcut Catalogue, printed p161](https://www.sunhydraulics.com/sites/default/files/media_library/tech_resources/Intl_SCComplCatalog_2009.pdf)
states: “Although this valve goes into a 4 port cavity, the nose (port 1) is not used.”
The official indexed catalogue text was available; direct full-PDF fetch returned
403. The independent proposal uses existing `terminated` disposition for
C5:port1, retaining all source cavity machining and its protected nose. It does
not add a plug or remove a physical source cut. `schematic_conformance` for C5
passes the exact re-evaluation. This finding was not imported into SQLite or
generalized to other four-port cartridges.

## Why the seven single-terminal nets existed

The saved normalized run already contains all seven unique net names, each with
status `uncertain`. Its port assignments were retained as unconfirmed source
observations, with source/location gaps and explicit topology uncertainty.
Normalization grouped equal supplied names; it did not establish a second
endpoint for these names. The AI also misread the two right CBCG port labels and
assigned several otherwise connected ports to the wrong work/return lines.

Generation previously checked only that a connected/unknown port had some net.
It promoted named unknown ports to connected, then accepted matching cavity
port counts/labels without checking isolated net membership. Thus a correct
machining identity passed admission with incorrect hydraulic intent. The shared
Router had no legitimate second terminal to connect on those seven nets.

`generation.topology_issues()` now blocks single-terminal connection intent
before CAD, retaining the port/net and identifying the exact port for the existing
decision navigation. It also checks confirmed source assignments against net
membership. Current request overrides and saved explicit engineer corrections
remain authoritative. Distinct net punctuation is preserved. No new confirmation
textbox or topology sign-off requirement was introduced. Replaying preflight
on the actual saved run reports exactly seven single-terminal blockers;
the separately reviewed topology has none.

Stage 1 is unchanged. Stage 2 instructions now explicitly require tracing other
endpoints, cross-pilot branches and junctions, and distinguishing unused interfaces
from unknown connections. Future provider recognition accuracy was not tested.
There is no model-specific correction table in runtime code.

## MB/C2 geometry and placement correction

C2 top origin: `(248.9513697733023, 67.625, 115)` mm, inward −Z.
Source port2 spans depth 21.445–43.675 mm; its hydraulic node is clipped to the
real source cuts, including the Ø18.59 mm stage at depth 24.63–44.09 mm.
Port1 spans 44.645–51.8 mm. The remaining seats/transitions/threads stay protected.

MB right-face origin: `(275, 67.625, 80.845)` mm, inward −X. The saved entry is
a source G1/2 thread-defined draft: tap-drill Ø19.05 × 12 mm, 118° point. Full
port sealing form, thread depth and fitting envelope remain unresolved.

Exact original measurements (`mb-contact-analysis.json`):

- Entire MB/C2 cut overlap: 2.4055172663122417 mm³.
- Overlap within actual C2:port2: the same 2.4055172663122417 mm³.
- Outside that window: **0 mm³**.
- Full cylindrical MB hole overlap with the window: **0 mm³**.
- Characteristic opening from the tip contact: 1.4390201937389957 mm²;
  no operating flow was supplied, so flow adequacy is not established.

The original validation's protected-region rule subtracts only declared same-net
windows. With no declaration it subtracts none, hence both FAILs describe the
same unplanned contact, not proof of a separate seat/land intrusion. Neither
rule was changed, and the contact was not automatically authorized.

Initial placement averaged window target coordinates and screened face-plane
footprints. Cavity cuts entering from the top were absent from the right-face
occupied list. The analytic layout assessment also omitted fixed functional
ports from its fixed-cut conflicts. Both placement omissions are corrected:

- `layout.placement_conflicts()` reuses source machining primitives and the
  shared finite-profile separation screen: offsets, cones/drill points, threads,
  modifiers, required wall and known installation envelopes. Unknown fitting
  height is never invented. This is conservative screening, not Exact approval.
- `source_safe_port_positions()` proposes positions on the same face and within
  the existing block, checking source cuts and available installation clearance.
- AI compilation explicitly opts into this screen. Layout assessment includes
  functional entry conflicts, and explicit layout proposals prioritize local
  source-separated port positions. Existing count budgets stay unchanged.

Minimal separate proposal: MB right U/V `(67.625,80.845)` →
`(51.62499999999999,72.67499999999998)` mm. Block remains 275 × 175 × 115;
all eight cavity positions and other authored ports remain unchanged.
Exact new MB/C2 overlap is **0 mm³**, shortest cutting-solid separation
**6.081897985023153 mm** (`corrected-mb-contact.json`). Actual operating pressure
is still unknown; this is not a pressure-wall certificate.

## Focused offline result and remaining engineering work

Only the same eight-valve case was routed/validated offline. The real library,
shared Router, exact production construction, authoritative checks and STEP
round trip were used; no provider call or repeated schematic recognition occurred.

| Measure | Original independent accepted route | Corrected topology, minimal MB move |
|---|---|---|
| PASS / WARNING / FAIL | 1849 / 15 / 9 | **3326 / 17 / 115 — rejected** |
| Seven old isolated-interface checks | FAIL | PASS individually |
| Old MB/C2 contact | 2.40552 mm³, undeclared | 0 mm³ |
| Cross-net intersection checks failing | 0 | 31 |
| BRep | valid, 1 solid | invalid, 3 solids |
| STEP | valid, 1 solid | reimport valid, **3 solids**, FAIL |
| STEP volume delta | 0.0012824619188904762 mm³ | 0.00009809713810682297 mm³ |
| Generated drillings / plugged accesses | 26 / 23 | 41 / 39 |
| Generated total drilling depth | 2280.3239763199067 mm | 3946.7512076599537 mm |
| Manufacturing ready | No | No |

The small STEP volume difference does **not** excuse the three-solid failure.
The corrected fixed-layout search took **352.562 s**, one exact complete candidate
of the unchanged up-to-eight budget. Normal and expanded pools retained no
source-safe route for **A_DC, B_DC, MA, MB, T**. Progressive repair stopped at its
existing bounded neighbourhood. The fallback remains explicitly unresolved;
its unsafe cuts are not a safe proposal or an admissible production result.

New FAILs by rule: circuit_intersection 31, declared_connection 31,
cavity_protected_region 19, unintended_cut_intersection 12, plug_engagement 10,
installation_access 6, boundary_access 3, solid_validity 1, solid_count 1,
step_round_trip 1. Full feature attribution is preserved in
`corrected-validation.json` and `evaluation-trace.json`.

A separate **AI-owned generation** used the reviewed normalized result and
existing initial-layout planner, with no saved-project writes or CAD builds.
Its eight analytic layouts took 58.313 s. The best sample still has blocked
A_DC/B_DC/MA/T corridors and competing-net conflicts, although fixed functional
port machining conflicts are empty. It is saved as `ai-owned-layout-proposal.json`
with `ai-owned-layout-evidence.json`, explicitly **unvalidated / not applied**.
No further CAD was spent on that already unresolved analytic sample.

This establishes neither physical impossibility nor that a larger block alone
will solve the corrected circuit. A source-safe complete layout/route combination
for the now four-terminal work/load nets remains unresolved. The old MA/MB route
algorithm and successful independent candidate remain intact, but they cannot
certify this changed terminal allocation. **MA/MB non-regression is confirmed
for code/data preservation only, not claimed as successful routing of the new
topology.** No broad Router rewrite was made to conceal this result.

Required engineering facts also remain open: actual pressure/flow, complete BSPP
thread depth and sealing/installation form, material application suitability, and
the directional valve's precise product/order identity. Product pressure ratings
were not substituted for operating conditions.

## Ownership, verification and delivery

All corrected files are independent review artifacts, requiring explicit review
and Apply/import before any saved geometry changes. No normal Model Preview,
Reroute, Optimize, Validate, Build, Save or Reload gains resizing/repositioning.
The AI source-screen opt-in is a transient generation function argument, not a
persisted permission or an `origin.method` test. Manual new-project packing keeps
its previous screening path; manual/frozen/committed cuts retain existing guards.
Exact Validation and the shared Router are unchanged.

Protected hashes before/after match (`protected-before.json`,
`corrected-acceptance.json`):

- Saved project: `450ff90ca5ae82b958fae5e45558cf57c37be7ce5c9468aa13072934fed43f2a`.
- Active database: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.
- Previous independent route: `4258f0abfd8d8a17df84232d7b4fb1a24d38d333714f034d93f46b0475a1a292`.
- Original normalized run: `89f9a31c14687a91daa5914302bc2fb7ba674fc7a30e073a5adcc98e48ae4094`.

Twelve focused Python checks pass: six new topology/placement boundary tests,
two existing AI admission/disposition checks, and four store/API revision,
unchanged-save, error and origin guards. Exact case failure evidence is retained;
it is not described as a passing regression. No broad suite, browser automation,
Vite build, unrelated CAD benchmark or paid AI call was run. Static syntax and
`git diff --check` pass.

Changed code: `manifold/ai_design/generation.py`,
`manifold/ai_design/semantic.py`, `manifold/layout.py`,
`manifold/layout_planning.py`; focused tests:
`tests/test_ai_topology_placement_admission.py`; this report.
Large diagnostic/CAD files and active databases are not committed.

The delivery commit SHA, verified remote HEAD and worktree status are recorded
after push in `output/runtime-checks/eight-valve-nine-fails/delivery.json` and
the final task response. This report ships in that commit.
