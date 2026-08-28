# Revision 4.1 traceability

| Requirement | Implementation | Verification |
|---|---|---|
| Three verdicts | `verdict.py` | `test_verdict_gate.py` |
| Semantic classes + evidence roles | `models.py`, Assessor schema | quote, attribution, mention, allusion, homograph, uncertainty tests |
| Exact SQLite postings | `index_builder.py`, `index.py` | exact retrieval and byte-reproducible build tests |
| Source-agnostic ingestion | `manifest.py`, `ingestion.py` | plain-text, markup, hash, malformed-input tests |
| Raw offsets | `normalization.py`, `ingestion.py`, `index.py` | raw recovery and markup-ingestion offset tests |
| Provenance and approval manifest | schema + `manifest.py` | schema shape, date source, path, approval tests |
| Corpus packaging boundary | ignore rules, baked-image builder, Dockerfile, boundary scan | reproducible fixture, explicit opt-in, isolated-context, and leakage tests |
| Three model roles | `agent.py` | ADK runner test with deterministic model doubles; live Gemini pending credentials |
| ADK orchestration | dynamic `takhrij_orchestrator` | actual `Runner.run_async` end-to-end test |
| Deterministic tools | `adk_tools.py` registry + `ctx.run_node(FunctionTool)` | workflow test records all six tool executions |
| Mandatory adversarial pass | `agent.py` | ADK two-axis adjudication test + synthetic script |
| Evidence-derived verdict | `verdict.py`, `gate.py` | only independent authorial target use qualifies; corruption and uncertainty tests |
| Async 202 path | `web.py`, `publisher.py`, `worker.py` | Flask route tests |
| OIDC worker | `security.py` | fail-closed signature/claim tests; live token pending cloud |
| Lease and stale-write safety | `jobs.py` | in-memory and Firestore transaction tests |
| Dead-letter terminal state | `worker.py`, Pub/Sub script | terminal worker failure releases quota test |
| Bilingual labels | template and UI script | HTTP/template test; final browser visual check pending deploy |
| Immutable release/book list | startup checks, manifest hashes and metadata | index and production-startup tests |
| Local-only corpus boundary | manifest status, delivery scope, redaction | local build, image rejection, API redaction, and Vertex-run tests |
| No phrase/vector/account features | omitted by design | source and README review |
