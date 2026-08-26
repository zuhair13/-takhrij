# Working agreement

- Revision 4.1 is the feature boundary. A new capability requires removing another one.
- The shipped runtime uses only Google ADK, Google Gen AI on Google Cloud Agent Platform
  (the current name for the Vertex AI path), and Google Cloud.
- Keep `GEMINI_MODEL_ID=gemini-3.5-flash` pinned. It was verified against Google's official
  global-endpoint model list on 26 Aug 2026 after the newer model repeatedly exhausted
  shared capacity; do not substitute a family name or preview alias.
- Deterministic facts stay in deterministic functions. Models may propose or classify; they never assert that a string exists in a source.
- Deterministic functions must remain represented in the ADK tool registry, and the orchestrator
  must execute those `FunctionTool` objects through `ctx.run_node`; a decorative registry is not
  sufficient.
- Never collapse `ة` with `ه`.
- Never issue a dossier that did not pass `IssuanceGate`.
- Keep the public `/worker` endpoint fail-closed on signed Pub/Sub OIDC verification.
- Run `PYTHONPATH=src python -m unittest discover -s tests -v` before every merge.
- Run the runtime-provider scan documented in `README.md` before every merge.
- Do not commit a production corpus until its exact release, book list, attribution, and licence use are approved.
