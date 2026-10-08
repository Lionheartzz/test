# Real AI Design structured-output failure correction

## Scope and starting point

- Branch: `codex/sqlite-domain-reset`.
- Starting HEAD: `9fe5d8fab7e6c1250a87f84ed76789b2ecdee7cd`; working tree initially clean.
- Investigated the saved real analysis, not the Studio screenshot's unrelated previous-build closure warning.
- No paid AI calls, retries, provider configuration changes, tests, browser checks, frontend build, CAD work or library changes were performed.

## Recorded evidence

Analysis: `PMC25-2977 ( CETOP 5)`; uploaded image: `64c86f6d-b915-43b1-867b-f1165914342d.png`.

Saved attempt: `output/ai-design/07ef7ef765254da8b846787618099489/current.json`.
Run: `072ab5e6f3f844f0974ebe01574c4fa5`, created `2026-10-08T17:07:44.182321+08:00`.

| Recorded field | Value |
| --- | --- |
| Provider / model | `configured-multimodal` / `agnes-3.0-flash`, real provider |
| Run status / error | failed / `INVALID_STRUCTURED_OUTPUT` |
| Failure phase | `structured_output_validation` |
| Run elapsed / HTTP attempt elapsed | 162.59578 s / 162.093 s |
| Requests / configured retries | 1 / 0 |
| HTTP / finish / stream completion | 200 / `stop` / true |
| Content / reasoning characters | 9,515 / 0 |
| Validation errors | 1 semantic `value_error` |
| Exact path | `components[5].manufacturer` |
| Safe explanation | Unknown observations must have a null value. Do not assert a value while marking it unknown. |
| Normalization error | null; normalization was not reached |
| Output control / timeout | `max_tokens=65535` / 300 s |

The current configuration has JSON mode and streaming enabled, streaming usage requested, no contract retries, and provider-default reasoning controls. Historical diagnostics independently record streaming, budget, timeout and retries; they do not independently record JSON mode. The configuration file was not changed.

## Root cause and classification

The provider returned JSON readable enough for nested semantic validation, with a complete stream and `finish_reason=stop`. The saved evidence does not indicate transport truncation or a library-resolution failure. Optional usage-final metadata is not stream-completion evidence.

The sixth component's manufacturer observation had a non-null value while its effective status was unknown. `Observation.unknown()` correctly rejected that contradiction. The existing `recover_unknown_identity()` accepted only the missing-provenance error on optional manufacturer/model/cavity observations; it excluded this equally discardable unknown/value contradiction. Consequently a recoverable optional identity inconsistency rejected the entire analysis before normalization, engineering admission and library resolution.

The response was semantically inconsistent, rather than proven malformed JSON. The schema invariant remains appropriate; the defect was the overly narrow optional-identity recovery and the uninformative UI message.

Neither the raw response nor the rejected value/component label is retained. The affected item can truthfully be described only as **Component 6 · Manufacturer**. One recorded nested error does not establish that the rest of the response would pass later global validation.

## Correction and safety

- Extend the existing recovery to the exact unknown/non-null invariant, only at `components[index].manufacturer`, `.model` or `.cavity`.
- Discard the unsupported value and certainty, leaving null/unknown. Preserve any explicit source on this newly recoverable case for existing source/document/page/quote checks.
- Revalidate the complete `CircuitReading`, then use unchanged normalization and engineering admission. Mixed errors, malformed observations, hydraulic conflicts and other semantic/schema failures still reject the attempt.
- Keep unsupported identity unresolved, with a field-specific review item using the validated component label where available. No inferred product, cavity, compatibility or source-backed identity is created.
- Display fixed, safe failure explanations and a known field/component/port ordinal instead of the generic unreadable-observation message and raw machine error code. Existing normalization diagnostics remain separate. No raw values, JSON, internal IDs, exception dumps or credentials are shown.
- Keep topology, page/document references, exact requirement quotes, selection-preference separation and authoritative identity/library gates unchanged. No connection is added or confirmed by this correction.

## Expected behavior and limits

When a future response contains only this safely recoverable optional identity error, the received response is corrected locally without another provider request. Analysis can complete only if full revalidation, normalization and admission also pass; manufacturer remains unresolved for engineer review. A rejected legacy attempt now receives a specific explanation identifying Component 6 / Manufacturer, without inventing its label.

The original failed attempt remains immutable. It cannot be replayed from the saved diagnostics because the raw response was not retained. No real provider rerun was performed, and original-case success is not claimed. Tests and frontend rebuild were explicitly prohibited; browser/runtime behavior is not claimed verified, and an existing built frontend requires its normal rebuild before these source changes appear there.

## Changed files and verification

- `manifold/ai_design/identity_admission.py`: narrow optional identity recovery.
- `manifold/ai_design/semantic.py`: truthful labeled unresolved-review description.
- `manifold/ai_design/validation_details.py`: fixed explanations for existing hydraulic connection invariants.
- `web/ai-diagnostics.js`: safe, actionable failure categories and locations.
- `web/ai-design.js`: remove redundant raw error-code paragraph.
- `docs/PROVIDER_DIAGNOSTICS.md`: document recovery and diagnostic boundaries.
- This report.

Verification is limited to saved evidence, static pipeline/diff inspection and `git diff --check`. No tests were added or run. Delivery SHA and verified remote SHA are recorded in the completion response.

## Preserved-file SHA-256

These files were verified unchanged during the task:

| File | SHA-256 |
| --- | --- |
| Active engineering database | `1e3267bd6a6271cf819b5181ed52eae55ab8b8b54a4a48ce45cc277175d7daa2` |
| Provider configuration | `2585ed2e0e32ff5677cf0d3136fdd948f7a9c9cf951eb6683df969cf742e190a` |
| Original analysis workspace | `ab6c33065e3600fd624701696bd5ef6c8f1f096322bafc88c9991993e1569b25` |
| Original failed attempt | `f6f6450c08efd4fedcaa0ab062c3f968b9a304bdfa0bccb68d7e78bbd8573e76` |
