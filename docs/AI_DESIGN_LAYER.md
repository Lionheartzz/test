# AI Design: schematic to editable manifold draft

AI Design accepts PDF/PNG/JPEG schematics together with the original engineering requirements, interprets them through a configurable multimodal provider, and compiles the reviewed hydraulic representation into the existing schema-version-1 Design. Geometry, routing and validation remain deterministic PMC operations.

## First run

1. Run PMC locally at `http://127.0.0.1:8765/`, open **AI Design**, then **Provider settings**.
2. Enter your API base URL, multimodal model ID and API key. No vendor, endpoint or model is preset. The current transport is Chat Completions with inline image content; use a model/server supporting that contract. Enable the provider and save. HTTPS is required except for a loopback model server. Anonymous access is an explicit option for servers that need no key.
3. Create an analysis, upload your schematic and enter requirements such as port faces, block dimensions, prohibited drilling faces, operating flow and pressure. Select the configured provider and **Analyze & create manifold draft**.
4. Review source evidence, ambiguous connections and requirements. When a cavity cannot be resolved from existing evidence, choose an existing library cavity, map each source hydraulic window to one schematic component port and enter your engineering decision. A model number alone does not establish cavity compatibility.
5. Generate the draft, inspect the attempted candidates and exact validation results, then **Open draft in Manifold Studio**. Save it as an ordinary project. Edit positions, reroute, undo/redo and Save & Validate through the normal Studio controls.

The application exposes only the configured real multimodal provider. Without a ready configuration, analysis requires Provider settings; there is no mock fallback or synthetic-schematic action. Deterministic provider fixtures live under tests only and are injected explicitly by regression tests.

## Provider and document boundary

Settings are server-side in ignored `.pmc-local/ai-provider.json`. The key is stored locally, is not encrypted by PMC, and is excluded from public settings, projects and exports. Changing the endpoint requires a new key; clearing the key disables the provider. Settings access requires the server's loopback interface. Selected documents and original requirements are sent to the provider when analysis runs; CAD and saved projects remain local.

PDF pages are rasterized locally in an isolated renderer process; PNG/JPEG images are decoded and resized. Cached page images retain source SHA-256 and page identity. Default page budget is 12, configurable up to 24; exceeding it fails explicitly instead of silently dropping pages. Upload limits remain 20 files, 20 MB per file, 100 MB total. Original documents are hash-checked before analysis and generation. Source review supports rendered PDF pages and normalized region boxes.

The provider sees a bounded semantic extraction schema and untrusted source evidence, never CAD tools. PMC computes internal identities, validates claims, source references, original requirement quotes and topology, and rejects extra fields or invalid units/numbers. Max output tokens accepts any positive integer or blank (omit the parameter); there is no PMC token ceiling or hidden 2 MB response ceiling. Existing semantic structure and document admission limits remain unchanged. Remote failures use bounded classifications; raw response/error bodies and credentials are not stored in diagnostics. Transport tests use a local HTTP server. Operator real-provider trials reached the API but failed with truncation/timeouts. The integration follow-up uses isolated HTTP fixtures and does not automatically repeat paid calls. See `docs/PROVIDER_DIAGNOSTICS.md` for findings and next-test settings.

## Generation and engineering authority

Generation is limited to four cartridges, forty hydraulic terminals and sixteen nets. Existing native/PMC/project definitions are read without modifying libraries and pinned by definition SHA. Automatic cavity resolution requires existing compatibility evidence or explicit source cavity identity with an exact interface mapping. Manual choices and topology/face overrides retain the engineer's decision. Demo definitions retain their demo status.

Supported requirements include block min/max/exact dimensions, external-port and component mounting faces, forbidden cross-drilling faces, routing priorities, material metadata, flow screening and pressure metadata. Required faces and dimensional/drilling constraints persist into subsequent manual editing and validation. Unmatched target labels are left for review. Explicit, confirmed terminal operating flow/working-pressure claims with supported units can populate their net; component ratings, settings and AI-inferred loads are not treated as design loads. Pressure loss, valve sizing, thermal behavior and material/rating suitability are not computed.

A bounded sequence of layouts uses the existing router and exact OCCT checks. Each attempted design, resolved route and validation report is retained. The selected result may still contain engineering failures or warnings and is labeled Draft. No buildable candidate produces a recoverable result; adjust the topology, library mapping or constraints and rerun. This is a finite candidate search, not a general layout optimizer.

Unspecified external-port machining definitions become visibly provisional unthreaded bores requiring review. The generator never invents vendor cavities or implies machining/pressure certification. Unsupported requirements remain in the execution report and engineering-review items, including blocking review for unsupported hard requirements.

## Persistence and recovery

- Analyses: ignored `projects/ai-design/<id>.json`; immutable runs and generation attempts: `output/ai-design/<id>/`.
- The compiler does not overwrite an existing project. Opening a generation creates an unsaved draft; normal project saving uses `projects/saved/<id>.json` and existing optimistic revisions.
- Every draft carries `origin.ai_trace`, analysis/run/generation identities, input/result hashes and verbatim requirements. The generation record also retains engineer decisions, requirement dispositions and semantic-to-feature/terminal mappings.
- Project export preserves the trace and requirements. Detailed analysis/generation records and uploaded source binaries are separate local artifacts; copying a project alone does not bundle them.
- Stale analysis or changed library pins block generation. Concurrent revisions preserve completed evidence without replacing the newer workspace state. Failed analyses preserve the previous successful result.
- One background AI operation runs at a time. Job progress is persisted under `output/ai-jobs/`; a service restart marks incomplete jobs interrupted and permits rerun. This is a local executor, not a durable distributed queue.

The original hydraulic schema remains distinct from Design. Claims preserve source kinds, unknowns, alternatives and engineer-review overlays. Reviewing a model name does not manufacture knowledge-base compatibility. The separate Knowledge Base has not been migrated or written by this feature.

## API map

Existing task/run/review/export endpoints remain under `/api/ai-design`. New endpoints expose settings, rendered source pages, library searches, generation preflight, job start/status and immutable generation retrieval. Consult `manifold/ai_design/api.py` for the exact route contract. `remote.py` owns the current transport; `semantic.py` owns semantic admission; `generation.py` compiles into the existing CAD pipeline. Other providers can implement the same analysis adapter without changing Design or embedding vendor response syntax in hydraulic entities.

## Provider diagnostics and controls

Operator-selected reasoning dialect/mode/effort can be overridden per operation. No endpoint/model-name detection is used. Automatic semantic-contract retry defaults to zero and can be explicitly enabled once; auth, HTTP, network, timeout and truncation never retry. Optional SSE streaming records usage when reported and discards reasoning text. All requests share a total provider deadline. Runs expose normalized token fields, per-request evidence, stage and actionable failure guidance. Latest attempt is separate from latest successful result, including legacy failed runs. See [Provider diagnostics](PROVIDER_DIAGNOSTICS.md).
