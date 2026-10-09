# AI source normalization correction

Starting HEAD: `954240dd19c326fbe023690c075ea5b9ac5be2c2`.

## Real failure

The operator-started v12 run `2d5d9eea871544148ca25f73462919e9` took 94.38612 seconds: two planned HTTP 200 requests, complete streams, no retries. Its first stage retained 12 original captions, including RDDA / T-10A, CBCG / T-11A, DSCS / T-31A, RBAA / T-3A and LRHC / T-17A. Local lookup found 1,295 reference records in 5.438 seconds. The second stage passed the model-facing schema and failed normalization at `components[0].ports[0]`.

The old normalizer required every schematic source to contain a nonblank textual quote, including graphical hydraulic connections. It also used net provenance for the port display label. Missing quotes and invalid optional source boxes were both reported as generic topology failures. The saved run contains neither the second-stage typed reading nor detailed source errors, so the exact quote/box that triggered this particular failure cannot be recovered. The retained caption count also rules out the separate maximum-port-claim overflow for this run.

## Correction

- Graphical/page evidence may have no text quote. Incomplete non-null source readings are retained as uncertain with a review item; they do not become confirmed engineering facts.
- Missing identity text can be supported only by explicitly linked, same-document/page captions containing the literal value. Product, cavity and mounting fields remain independent. There is no fixed-format splitting, fuzzy identity admission or catalogue-generated source quote.
- Invalid optional boxes are omitted without guessing coordinates. Document/page errors, exact user-instruction checks and graph contradictions still reject the attempt. No CAD, geometry, routing or execution policy is changed.
- Port labels use independent display metadata. The same normalized net observation drives both port and connection claims, preventing uncertainty from being lost during grouping. No port, disposition or net membership is invented, dropped or merged.
- Caption context uses one claim with its separate evidence references, within the existing canonical bounds.
- Fixed field/reason/error-path diagnostics and bounded omission counts are retained. Future normalization failures may preserve one private rejected typed input for local investigation, never as a completed or executable analysis.
- Already read source annotations remain visible on failed runs, with an explicit incomplete-analysis notice.

Prompt v13 keeps the existing two-stage pipeline. Provider/model/key, output budget, reasoning, streaming, JSON mode, timeout and retry settings are unchanged. No paid provider request was issued during this correction. The old failed run is unchanged, and no fresh model response is claimed to have succeeded.

## Verification

Syntax/module loading, Vite build and `git diff --check` passed. Localhost and LAN (`192.168.253.117:8765`) health returned HTTP 200 after loading the corrected service; the existing provider registered successfully without a provider call. Read-only Chrome interaction on localhost opened the actual failed run and expanded all 12 captions, including the distinct product/cavity annotations and the incomplete-hydraulic-interpretation notice. No analysis/save/generation action was performed. Protected hashes below remained identical after these checks.

Verification respects the existing no-tests instruction: no tests were added or run; no CAD/prove or synthetic production analyses were used. Vite retains its existing runtime-font and bundle-size warnings. Delivery SHA and verified remote HEAD are recorded in the completion reply.

Protected SHA-256 values:

- Active DB: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.
- Provider configuration: `2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`.
- Original failed run: `a9ab25c0735b17718c8fd4ee92f98395daf775412941e3e6d922748e10a0f7a6`.
