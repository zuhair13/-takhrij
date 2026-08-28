# TAKHRIJ · تخريج

> **A word found in a book is not necessarily a word used by its author.**

TAKHRIJ is an attestation-intelligence layer for corpus search. Search engines retrieve matching
strings; TAKHRIJ determines which matches count as historical evidence by separating two questions:

1. Does the string carry the target sense?
2. Is it independent authorial use, or only quotation, attribution, allusion, or mention?

Its frozen, falsifiable claim is:

> No **independent authorial target-use** attestation of any enumerated variant of form X,
> in intended sense S, occurs before cutoff Y AH within release R and book list B.

Only `target_use ∧ independent_authorial_use ∧ year < cutoff` can falsify that claim. An earlier
Quranic quotation, cited speech, metalinguistic discussion, formulaic allusion, or homograph is a
real string match but not independent lexical evidence. Unresolved semantics or evidence role
forces `INCONCLUSIVE`; it can never be silently counted as absence.

The system searches exact normalized tokens, classifies both axes with Gemini, requires a Devil's
Advocate to audit the search trace, optionally searches missed variants, and releases a dossier
only after a deterministic Issuance Gate verifies every quote, source, offset, date field, and the
evidence-to-verdict derivation.

This repository implements Revision 4.1. It intentionally contains no OpenITI corpus. The tracked
`data/takhrij.db` is a byte-reproducible database built only from repository-authored synthetic
texts under `tests/fixtures`; it preserves the frozen fixture-image deployment and is never
historical evidence. Tests also rebuild databases in temporary paths.

## Judge quick path

1. Run `PYTHONPATH=src python scripts/run_fixture_demo.py`.
2. Inspect `adjudication`: the synthetic control returns three raw matches, two before the cutoff,
   and zero qualifying earlier independent uses.
3. Run `PYTHONPATH=src python -m unittest tests.test_verdict_gate -v` to see direct quotation,
   attributed quotation, metalinguistic mention, formulaic allusion, homograph, and uncertainty
   tested against the same deterministic predicate.
4. Open the web UI: each hit shows **meaning**, **evidence role**, and whether the claim contract
   counts or excludes it.

The fixture is intentionally synthetic. A real OpenITI run is local-only, redacted, and described
in [`docs/local-openiti-runbook.md`](docs/local-openiti-runbook.md); the public image remains on
the fixture until distribution permission covers the derived index.

## Current status

| Layer | Status |
|---|---|
| SQLite index, offsets, two-axis adjudication, verdicts, Gate | Implemented and locally tested |
| Leases, duplicate delivery, stale-attempt CAS, terminal failure | Implemented and locally tested |
| ADK 2.x dynamic workflow, three model roles, deterministic tool registry | Implemented and verified live with Gemini 3.5 Flash through Vertex AI |
| Bilingual web UI and four routes | Implemented, HTTP-tested, and publicly deployed on Cloud Run |
| Container, Cloud Build and IAM setup | Executed successfully in Google Cloud project `integral-loop-411822` |
| Source-agnostic manifest, ingestion, deterministic index build | Implemented with fixture, local-only, and distribution-approved scopes |
| Local OpenITI five-book manifest | Pinned to release 2025.1.9; local non-commercial run path implemented |
| Public OpenITI image | Blocked until distribution permission covers the derived index and service |
| Live Gemini integration | Verified end-to-end on Cloud Run against the synthetic fixture; Firestore/Pub/Sub production activation remains licence-gated |

Verification snapshot (29 Aug 2026): 94 tests pass with 86% branch coverage, including an actual
ADK `Runner` execution with all six registered `FunctionTool` objects observed in the run.
Ruff, Python compilation, Node JavaScript syntax, Bash syntax, Cloud Build YAML parsing, the
corpus-boundary scan, and the runtime-provider scan are clean.
Cloud Build successfully built the container, and Cloud Run served a complete live Gemini/ADK
adjudication at https://takhrij-39896183136.us-central1.run.app. The hosted service contains only
repository-authored synthetic fixture content and is not historical evidence.

The three-document synthetic build is byte-reproducible. Its size and build time validate the
workflow only; they are not production-corpus estimates.

## Architecture

```mermaid
flowchart TD
    UI["Bilingual UI"] --> API["POST /claims"]
    API --> FS["Firestore jobs + leases"]
    API --> PS["Pub/Sub"]
    PS --> W["OIDC-protected /worker"]
    W --> ADK["ADK dynamic workflow"]
    ADK --> DB["Read-only SQLite corpus"]
    ADK --> G["Gemini 3.5 Flash"]
    ADK --> Gate["Issuance Gate"]
    Gate --> FS
```

ADK is load-bearing. `takhrij_orchestrator` owns the ordered nodes, the second retrieval pass,
and progress events. The Morphologist, Assessor, and Devil's Advocate are `LlmAgent` nodes.
Normalization, validation, retrieval, quote extraction, and span verification are exposed as
`FunctionTool` objects. The orchestrator executes those exact tool objects through
`ctx.run_node`; the registry is therefore load-bearing, while a model never gets discretion over
whether a string exists.

| Gemini judges | Code establishes |
|---|---|
| Same-lexeme morphological forms | Non-destructive normalization |
| Semantic axis: `target_use` / `homograph` / `uncertain` | Exact postings lookup |
| Evidence-role axis: independent use / quotation / attribution / mention / allusion / uncertain | The one predicate that can affect the verdict |
| Weak trace or missing variant | Raw quote extraction and offset verification |
| Contextual reasons | Verdict derivation and dossier assembly |

The two axes are deliberately orthogonal. A quoted word may still have the target sense, but it
does not become evidence that the containing book's author independently used it.

## Claim input correction

Revision 4.1 names `target_use` as “the sense under investigation” but lists only form and year
as inputs. A classifier cannot distinguish a homograph without knowing the intended sense.
The implementation therefore requires `target_sense`. This closes the contract; it does not
add a claim type or product feature.

```json
{
  "form": "تخريج",
  "target_sense": "دليل يُستند إليه في الاستدلال",
  "cutoff_year_ah": 500
}
```

The server—not the caller—adds the immutable `corpus_release` and `book_ids`.

## Date rule

The comparison year is deterministic:

1. `composition_date_ah`, when documented.
2. Otherwise `author_death_year_ah`, explicitly labelled as a proxy.
3. `edition_date` and `witness_date` are displayed but never silently compared with an AH cutoff.
4. A potentially relevant match without a usable AH comparison year makes the verdict
   `INCONCLUSIVE`.

The date belongs to the containing work, not automatically to quoted speech. A target-sense hit
with an unresolved evidence role therefore blocks a negative verdict. The dossier also states
that attribution to an author/date does not prove when a spelling entered Arabic or whether a
later transmission normalized it.

## Retrieval and offsets

`documents` holds the exact post-markup raw text, source and raw-text hashes, parser version,
licence, and provenance. `postings` holds normalized single-token forms and Unicode code-point
offsets into that stored raw text. OpenITI-shaped ingestion removes only declared structural
controls and never normalizes Arabic glyphs. The browser receives already separated `prefix`,
`match`, and `suffix` strings; it never reinterprets Python offsets as JavaScript UTF-16 offsets.
The Gate compares the selected span as exact UTF-8 bytes, re-hashes the raw document, and resolves
all source and provenance fields again from SQLite.

Normalization removes optional Arabic combining marks and tatweel. Orthographic alternatives are
enumerated visibly: final `ى`/`ي`, plus the first lexical alef seat when present. The alef of the
definite article is never mutated, so a form such as `بالتخريج` cannot produce the false spelling
`بألتخريج`. Suffix alefs in `اً`, `ات`, `نا`, and `ان` never receive hamza seats; final
pronominal `ي` never becomes `ى`; and `ة` and `ه` are never merged.

No vector index is used. Attestation is an existence-of-a-token question, not semantic
similarity. Similarity search would add silent false positives without answering the contract.

## Safety and failure semantics

- Pub/Sub push tokens are signature-verified; `aud` and service-account `email` must exactly
  match deployment configuration.
- Ack deadline: 600 seconds. Worker lease: 900 seconds, renewed every 300 seconds.
- A valid lease returns a non-2xx response so Pub/Sub retries later.
- Expired leases are reclaimable with a new `attempt_id`.
- Final writes are compare-and-set on the current `attempt_id`; stale workers cannot overwrite.
- The fifth failed delivery marks the job failed and releases the public-demo quota while the
  message proceeds to the dead-letter topic.
- One active job and 20 created jobs per UTC day are the default public budget guard.
- More than 200 matches is not sampled into a confident answer; coverage becomes incomplete and
  the verdict becomes `INCONCLUSIVE`.
- A non-`uncertain` semantic or evidence-role decision below the deterministic 0.80 confidence
  floor converts both axes to `uncertain`; low-confidence judgement can never break the claim.
- Approved source roots and derived databases stay outside the repository. The only tracked
  database is the byte-reproducible synthetic fixture. Git, Python-package, Docker-context, and
  workspace scans reject other corpus artifacts; production startup rejects fixture databases.
- The default Docker build bakes the fixture database at `/app/data/takhrij.db`. A real database
  can enter an isolated image context only through the written-permission and explicit-opt-in
  approved-image builder. The database is mode `0444` in the image; no runtime mount is used.
- A licence-reviewed OpenITI database can be built only with `--allow-local-only-corpus`, outside
  the repository. Its metadata says `delivery_scope=local_only`; startup requires server-side
  redaction, and the image gate rejects it.

## Local deterministic verification

Python 3.12 is required. Install the pinned runtime before running the complete suite.

```bash
python -m pip install -e .
PYTHONPATH=src python -m takhrij.index_builder \
  config/corpus_manifest.fixture.json data/takhrij.db
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/check_corpus_boundary.py
PYTHONPATH=src python scripts/run_fixture_demo.py
```

Expected fixture adjudication:

```text
3 raw matches
2 raw matches before cutoff
0 qualifying independent uses before cutoff
NO_EARLIER_MATCH_IN_DECLARED_CORPUS
```

The early hits are an explicit quotation and a metalinguistic mention. The one independent
authorial use is after the cutoff. The output also says
`SYNTHETIC FIXTURE — NOT HISTORICAL EVIDENCE`.

## Full local application

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:APP_ENV = "development"
$env:CORPUS_DB_PATH = "data/takhrij.db"
$env:CORPUS_RELEASE = "FIXTURE-ONLY"
$env:CORPUS_BOOK_IDS = "fixture-early,fixture-late,fixture-markup"
$env:PUBSUB_AUDIENCE = "http://localhost:8080/worker"
$env:PUBSUB_SERVICE_ACCOUNT = "local-test@example.invalid"
python -m flask --app "takhrij.web:create_app()" run --port 8080
```

The fixture web app queues jobs but does not call the cloud model unless a worker is invoked with a
valid configured identity. The synthetic adjudication script builds its own temporary database and
is the offline smoke test. `docker build -t takhrij:fixture .` preserves the existing fixture image;
run it only with development settings because production startup rejects fixture content.

## Local OpenITI demo without distribution

The pinned manifest selects five primary texts at 276, 414, 456, 505, and 598 AH across Shamela,
JK, and Shia source families. It correctly uses
`0505Ghazali.Munqidh.JK009330-ara1`; the former Shamela candidate was secondary.

Set `TAKHRIJ_LOCAL_CORPUS_ROOT` to the external pinned release checkout, authenticate with Google
Cloud ADC, and run:

```bash
PYTHONPATH=src python scripts/run_local_corpus_demo.py \
  --claim-contract config/claims/TAKHRIJ-DIZA-01.json \
  --project-id PROJECT_ID \
  --acknowledge-local-only-licence
```

The script builds a temporary database outside the repository, forces the Google Cloud
Vertex/enterprise path, derives the exact book IDs from that database, runs the ADK workflow once,
and emits only a post-Gate redacted dossier. Do not announce a corpus result until that live run
has actually completed; the manifest is a reproducible experiment definition, not a result.
See [`docs/local-openiti-runbook.md`](docs/local-openiti-runbook.md).

## Distribution-approved corpus image (currently blocked)

Local non-commercial research use and public distribution are separate delivery scopes. The local
workflow above does not authorize baking the index into a public image. First satisfy
[`docs/licensing-checklist.md`](docs/licensing-checklist.md) and obtain permission covering the
exact release, files, derived database, image, service access, and distribution plan. Then:

1. Copy `config/corpus_manifest.approved.example.json` to the ignored
   `config/corpus_manifest.approved.json` and replace every placeholder with verified values.
2. Set `approval.status` to `written_permission_granted` and reference the written permission
   record stored outside Git.
3. Put the approved, hash-pinned inputs in an external directory and set
   `TAKHRIJ_APPROVED_CORPUS_ROOT` to that directory.
4. Build the approved image with the dedicated explicit opt-in workflow:

```bash
PYTHONPATH=src python scripts/build_approved_image.py \
  config/corpus_manifest.approved.json \
  REGION-docker.pkg.dev/PROJECT/REPOSITORY/takhrij:TAG \
  --allow-approved-corpus-image
```

The workflow refuses approved content without the explicit image flag, exact
`written_permission_granted` status, and an external source root. It creates a temporary build
context outside the repository, builds `takhrij.db` there, bakes it into the image at
`/app/data/takhrij.db`, makes it read-only, runs Docker without a shell, and deletes the context.
The Dockerfile independently rejects `approved_corpus` content unless the helper supplies its
dedicated build opt-in, so an ordinary `docker build` remains fixture-only.
Neither corpus sources nor the derived real database enter Git or Python source archives. The
manifest release and book IDs must exactly match the production environment or the service
refuses to start. Production additionally refuses a database labelled `synthetic_fixture`.

## Cloud deployment order

1. Run `deploy/bootstrap.sh PROJECT_ID REGION` from Cloud Shell. It enables APIs, creates
   dedicated runtime, push, and build service accounts, creates Firestore if needed, deploys the
   hello container, and refuses to finish until the URL returns `hello`.
2. Resolve permission and use the approved-image workflow to bake the read-only database into the
   image. Push only that explicitly authorized image to the existing Artifact Registry.
3. Set the non-placeholder deployment variables. The audience is the stable Cloud Run URL
   plus `/worker`.
4. Deploy the already-built approved image with the dedicated build/deploy identity. The checked-in
   `cloudbuild.yaml` continues to build the synthetic fixture image for engineering rehearsal; it
   is not an authorization path for a real corpus image. Do not assume the legacy
   `${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com` identity exists on a new project.
5. Run `deploy/configure_pubsub.sh PROJECT_ID REGION` after the real service is live.
6. Replay one Pub/Sub message deliberately and confirm a single final dossier plus multiple
   `attempt_id` log entries.

Do not run this sequence until the licence gate and baked-image authorization are resolved.
`cloudbuild.yaml` pins `gemini-3.5-flash`, sets the 60-minute Cloud Run request timeout, and uses
one Gunicorn process with threaded request handling. Cloud Run concurrency is four, while the
Firestore quota transaction permits only one active public research job.

The deployment variable is `GOOGLE_GENAI_USE_ENTERPRISE=True`. In ADK 2.7.1 this is the current
name of the Google Cloud/Vertex path; Google documents it as equivalent to the earlier
`GOOGLE_GENAI_USE_VERTEXAI` name. The runtime service account supplies ADC, so no API key or
service-account key file is shipped.

## Required pre-merge checks

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
ruff check .
python scripts/check_corpus_boundary.py
python scripts/check_runtime_providers.py
```

A clean provider scan prints no matches. The checker constructs its forbidden terms from fragments
so it does not match its own source.

## Known limits

- Single Arabic tokens only; no phrase matching.
- Corpus-bounded absence only; never historical absence.
- Semantic class and evidence role are model judgements and can be wrong.
- The Gate guarantees exact quote/source/metadata linkage, not interpretive correctness.
- The Devil's Advocate audits the trace, not unseen corpus contents.
- No geographic inference, borrowing analysis, accounts, or cross-session learning.

## Licensing boundary

The application code is Apache-2.0. Corpus files and derived data are separate inputs and are not
relicensed by this repository. OpenITI's documentation states that releases use CC BY-NC-SA 4.0,
so the repository implements two different boundaries:

- **Local non-commercial research:** the pinned source and derived index stay outside Git and
  containers; the displayed dossier is redacted server-side.
- **Public distribution/service:** still blocked until permission resolves the cash-prize context,
  hackathon submission licence, upstream digitization rights, derived-database treatment, image
  redistribution, and service access.

See the [`licensing gate`](docs/licensing-checklist.md), local
[`runbook`](docs/local-openiti-runbook.md), and pinned manifest. This is an engineering policy,
not legal advice.

## Current authoritative references (verified 26 Aug 2026)

- [ADK 2.x dynamic workflows](https://adk.dev/graphs/dynamic/)
- [ADK function tools](https://adk.dev/tools-custom/function-tools/)
- [ADK Google Cloud authentication and environment naming](https://adk.dev/get-started/google-cloud/)
- [Gemini 3.5 Flash global endpoint support](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations)
- [Cloud Build default service-account change](https://docs.cloud.google.com/build/docs/cloud-build-service-account-updates)
- [Pub/Sub authenticated push validation](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Cloud Run service identity](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [OpenITI documentation and licence](https://openiti.org/documentation/)
- [OpenITI release 2025.1.9](https://zenodo.org/records/17767721)
- [OpenITI primary-only release 2025.1.9](https://zenodo.org/records/18613982)
- [CC BY-NC-SA 4.0 legal code](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en)

All application code in this repository is new for this build. The synthetic fixture corpus is
new test material and is explicitly non-evidentiary.
