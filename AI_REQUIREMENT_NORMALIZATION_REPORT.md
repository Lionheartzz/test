# AI requirement normalization correction

Starting HEAD: `8174740bd183b60f89b7d3b519dcb3ce6171704f`.

## Confirmed failure

The saved run `518dc441a82c4e3e9ea96f994e59a5e2`, created on 2026-10-09 at 11:08:34 +08:00, failed after 29.95655 seconds with `NORMALIZATION_FAILED / user_quote_not_exact / requirements[0]`. Its original engineering requirements were empty. HTTP returned 200, finish reason was `stop`, the stream completed, and no structured-output validation errors were recorded. There was one provider request. This is a different failure from the preceding Observation shape errors.

The provider response nevertheless contained a RequirementReading. Normalization unconditionally treated every such item as a user instruction. Its exact-quote check then rejected the entire schematic analysis. The request also previously appended project-unit metadata directly below the empty original-requirements heading, leaving their boundary unclear to the model. The raw response is not retained, so its exact unsupported quote or content cannot be recovered or attributed to any particular drawing annotation.

## Correction

- Send original requirements as a separate JSON string and unit context as explicitly separate metadata. Prompt v10 requires an empty requirement list for empty/whitespace-only input and excludes drawing annotations, reference context and prompt examples from user requirements.
- Before creating requirement evidence, reject any returned instruction whose quote is blank or not an exact substring of the real original input. Discard its entire proposed design intent, including mounting fields; retain a visible review item saying it was not applied.
- Record only the safe category and original requirement ordinal in `normalization_omissions`; no response body, unsupported quote/value or credential is added to diagnostics.
- Preserve exact quotations and spans for admitted requirements. The existing original-clause coverage loop continues to flag genuine instructions that the model omitted or paraphrased. No fuzzy quotation repair, fabricated evidence or replacement engineering constraint is introduced.
- Observation source, document/page and hydraulic topology validation remain strict. An observation falsely citing a user requirement still fails the existing evidence check; this handling applies only to optional extracted RequirementReading entries.
- Existing results, inputs, provider settings and engineering database remain unchanged. Reanalysis is allowed; only concurrent analysis is blocked by the existing job ownership rules.

## Verification and limits

Per the user's earlier verification restriction, no tests were added or run, and no paid AI request was made. Verification consists of saved-record inspection, static control-flow review, Python syntax/module loading, local/LAN service loading and `git diff --check`. No frontend source changed, so no Vite build or browser test suite is needed for this correction.

The previous failed record stays failed. Its raw response is absent, so this is not a claimed successful replay of that run. A subsequent user-initiated analysis uses v10; other genuine source/topology/provider failures can still be reported.

Protected SHA-256 values checked before and after:

- Engineering DB: `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2`.
- Provider configuration: `2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a`.
- Original failed record: `1889dffe4a3025ff09932c4ffdc4337ae5021df6413fabab0920e1608932b3aa`.

Changed files: `manifold/ai_design/semantic.py`, `remote.py`, `diagnostics.py`, `docs/PROVIDER_DIAGNOSTICS.md` and this report. Final commit and verified remote HEAD are reported in the completion reply.
