# MA / T connectivity admission correction

Starting HEAD: `51d049c28865db9185916bd60fe854ee93b571fc`

Branch: `codex/sqlite-domain-reset`. Starting worktree was clean.

## Current matched evidence

- Completed trace: `output/cad-diagnostics/d73674d607334c2bad12c062da360060.json`, elapsed **128.203 s**.
- Trace SHA-256: `da50a21cef44100720c471695f862bdeb57f81e518e49b13ca7292f2833b132b`.
- Matching authored Draft: `output/ai-design/343f91fdb98c435296b6e78322157433/generations/6af80b3259954680855dab75b9bbb463/authored-draft.json`.
- Canonical source SHA-256 independently recomputed and matched: `d30070b7649885c16820cd643ab4a4535543ba02433af46ec6730a8954c8d8f6`.
- **275 × 175 × 115 mm**, **26 generated drillings** in the reported real Preview; production BRep marked valid, Preview unvalidated.
- The earlier MB/T drilling pair was not reused as the current culprit.

## Actual MA / T collision

Exact attribution is complete: **339.2446075984192 mm³** total, with the attributed feature pair accounting for 339.24460759841907 mm³.

| Feature | Net | Face | U / V, mm | Diameter / cylinder depth, mm |
| --- | --- | --- | --- | --- |
| `R-f0055891-AX0` | MA | bottom | 197.125 / 149.6763697733023 | 8 / 61.122133 |
| `R-e632b709-2` | T | right | 149.67637 / 57.83 | 8 / 161.375 |

The MA axis runs along Z, and T runs along X from X=275 to X=113.625. They cross near **(197.125, 149.67637, 57.83)**, inside both cylinder spans. The plug occupied regions are at their exterior entries, away from this intersection.

Selected MA: `axial_1_0:xzy:nearest`.

Selected T: `port_0_clear:axial_2_0:yzx:positive:c1_z_39.806558`. After simplification its conflicting transverse hole remains; changing its functional-port stem alone cannot remove this intersection.

This is an incompatible *best-effort combination*, containing an explicitly disconnected MA route. The saved MA pool was **0 retained / 259 considered**, including **16 exact-connectivity rejections**. T's source-only pool retained 3 candidates; repair retained 2. Complete combination search did not start because MA was empty. Progressive repair stopped after 185/256 states and 351/4000 pair screens with MA connectivity and this MA/T contact unresolved.

The trace therefore does **not** prove that this MA variant entered a clear pool through the flow-unknown defect. It was retained as unresolved editable geometry. The unconditional admission path was separately confirmed by code inspection and is now closed.

## MA's actual missing connections

For the selected variant, the saved exact contact graph has three disconnected groups:

1. `CV_354eb861e2c6b965e0a9:port1` (RDDA/T-10A C1) ↔ `R-f0055891-AX0`.
2. `CV_4bbbcefef0a86bf001e1:port1` (CBCG1/T-11A C3) ↔ `R-f0055891-2` and `R-f0055891-3`.
3. `PORT_86baf4d8e7eef36f8838` ↔ `R-f0055891-1` ↔ `R-f0055891-4`.

There are no verified edges joining these groups. All 16 recorded MA candidates failed to join the required terminals.

`spanning_pairs()` chooses one Manhattan nearest-terminal tree. Here that fixes C3 as the intermediate terminal between the MA port and C1, including when C1 uses an axial terminal override. Source-safe narrow-window termination then prevents the presumed through connection: for example C3's left drilling stops at cylinder depth 68.135 mm, and its back drilling stops at 15.58363 mm. Neither forms the assumed trunk to the other groups. The existing stop-depth/protected-source rules are correct to prevent treating a narrow source window as an unrestricted transit hole.

The omission of alternative three-terminal trees is established by the fixed tree construction. It does not establish that any particular alternative is manufacturable in this placement.

## Corrections

- **Mandatory final candidate verification:** `_verify_route_candidate()` binds the final closure contour, uses cached individual fluid BReps, checks exact source/route connectivity and optional flow opening, and screens obstructions. `_route_pool()` now calls this gate for every admitted candidate, outside the conditional flow-sizing branch. It no longer assigns `connection_verified=True` after obstruction screening alone.
- **Separate facts:** source/obstruction safety, physical fluid connectivity, all-node connectivity, optional flow-opening adequacy, and full engineering validation are recorded independently. Unknown flow leaves flow adequacy `null`; full engineering validation remains `null` at proposal admission. Neither means PASS.
- **Real opening:** a fluid edge requires the existing minimum overlap volume plus a positive exact section opening using the existing numerical tolerance. Actual known flow additionally requires its existing flow/velocity area. No flow value or full-bore opening requirement is invented for unknown flow; a mere tip touch is not connectivity.
- **Stale-proof rejection:** `_candidate_admitted()` checks proof presence, current machining geometry and hydraulic conditions. Sizing invalidates old proof. Global combinations, clear fallback pools, progressive repair pools, authoritative alternative proposals and incremental local selection all fail closed on absent/failed/stale proof.
- **Pinned/fallback paths:** every selected proposal is verified after final sizing/binding. Progressive baseline connectivity is independently checked instead of inferred from an absent failure flag. The two-net replacement path no longer forces `True`; metadata no longer falls back to `True`.
- **Bounded topology alternatives:** default `spanning_pairs()` and old variants retain their meaning. For a three-terminal net, the shared Router can additionally generate three terminal-root trees and one common junction at the terminal bounding-box center. Branches become ordinary external-face drillings, with existing tip, closure, source, wall and obstruction rules. No synthetic hydraulic nodes or `connects_to` assertions are added.
- **Fair retention:** terminal-tree and common-junction families participate in the existing family shortlist. The finite analytic topology sample is bounded to 48 variants, retains entry-direction diversity, and still competes within the original 16 simplification slots. Global/repair/exact attempt budgets are unchanged.
- **Explicit unresolved state:** failed proposals keep their actual cuts and Exact collision diagnostics, with `UNRESOLVED_EDITABLE_GEOMETRY`. Connectivity diagnostics include exact physical edges, flow-qualified edges when applicable, disconnected terminal groups and nearest component gaps. A connected proposal still requires full validation.

Files: `manifold/routing.py`, `manifold/cavity_access.py` (forward topology only), `manifold/preview_routing.py`, `manifold/schema.py` (routing-variant string grammar only), and this report.

## Verification and limits

Performed only saved-artifact/graph inspection, canonical source-hash matching, static code review, in-memory Python syntax parsing/compilation, and `git diff --check`.

As requested: **no tests, Vite build, browser, CAD generation, route execution or paid AI calls**. The current collision and old graph are observed evidence; the new candidates have not been executed. MA connectivity, elimination of MA/T contact, final drilling/plug count, engineering/STEP results and timing remain unverified until another real Preview/Validate. No zero-FAIL result or physically impossible placement is claimed.

No AI Stage 1, SQLite, source cavity geometry, wall rule, manual/frozen/committed cuts or saved project was changed. Active DB SHA-256 remains `1E3267BD6A6271CF819B5181ED52EAE55AB8B8B54A4A48CE45CC277175D7DAA2`.
