# Local OpenITI recording run

This path is for one non-commercial local research run. It does not create a distributable
database or public corpus service.

## Frozen inputs

- manifest: `config/corpus_manifest.local-openiti-2025.1.9.json`;
- release commit: `cfc4157a3cf2054c0888f133970a4eaa3e22e58c`;
- release DOI: `10.5281/zenodo.17767721`;
- five source SHA-256 values: recorded per document in the manifest;
- claim: `config/claims/TAKHRIJ-DIZA-01.json`;
- current contract SHA-256:
  `4f4f3e538feac219a15d2217d665a05e2945b733480c1d324f1115c68befce13`.

The contract tests independent authorial use of `ضيزى` before 500 AH. Direct quotation,
attributed quotation, metalinguistic mention, and formulaic allusion do not qualify even when the
word has the target sense. Version 3 corrects the three pinned Shamela source paths to their
actual `.mARkdown` filenames without changing the claim predicate. The version 2 contract hash
and the earlier conceptual hash remain in the claim envelope for lineage.

## Preflight

1. Keep the pinned OpenITI checkout outside the TAKHRIJ repository.
2. Set `TAKHRIJ_LOCAL_CORPUS_ROOT` to the directory that contains its `data/` tree.
3. Authenticate Application Default Credentials for the intended Google Cloud project.
4. Install the pinned project runtime and run all local checks.
5. Confirm the five source files match the manifest hashes. The index builder repeats this check
   before tokenization and aborts on the first mismatch.

```bash
export TAKHRIJ_LOCAL_CORPUS_ROOT=/absolute/external/OpenITI-RELEASE
export GOOGLE_CLOUD_PROJECT=PROJECT_ID

PYTHONPATH=src python -m unittest tests.test_manifest tests.test_local_demo -v
PYTHONPATH=src python scripts/run_fixture_demo.py
```

## One live run

```bash
PYTHONPATH=src python scripts/run_local_corpus_demo.py \
  config/corpus_manifest.local-openiti-2025.1.9.json \
  --claim-contract config/claims/TAKHRIJ-DIZA-01.json \
  --project-id "$GOOGLE_CLOUD_PROJECT" \
  --acknowledge-local-only-licence \
  > /absolute/external/takhrij-diza-redacted.json
```

The script:

- builds the SQLite index in a temporary directory outside the repository;
- writes `delivery_scope=local_only`;
- derives the exact book list from the built database;
- forces the Google Cloud Vertex/enterprise runtime path;
- suppresses raw diagnostic output that might contain source context;
- requires an Issuance Gate pass; and
- removes corpus quotations and free-form rationales before emitting JSON.

The temporary database is deleted when the process exits. Keep the redacted JSON outside the
repository; it is a run artifact, not application source.

## Local result page

After a successful run, display the post-Gate redacted JSON through the existing bilingual UI:

```bash
PYTHONPATH=src .venv/bin/python scripts/serve_redacted_result.py \
  /absolute/external/takhrij-diza-redacted.json --port 8080
```

Open port 8080 through Cloud Shell Web Preview. The viewer is read-only, adds no model call, sends
no corpus text to the browser, and refuses any result that lacks a clean Gate pass, local-only
scope, both redaction declarations, or that still contains a raw quotation/rationale field.

## What may be shown

Safe display fields include release/manifest/database hashes, book IDs, document/version IDs,
normalized token, offsets, source and parsed-text hashes, dates/provenance, semantic class,
evidence role, confidence, verdict, and Gate status.

Do not show raw corpus text, prefix/match/suffix, free-form assessment reasons, raw model
diagnostics, the derived database, or the external checkout.

## Fail-closed interpretation

- A source hash mismatch: stop; do not substitute a mutable file.
- Missing ADC or model capacity: report that the live run did not complete; do not use fixture
  output as a real result.
- Any pre-cutoff hit with unresolved semantic relevance or unresolved independent authorship:
  `INCONCLUSIVE`.
- A completed negative verdict: only “no qualifying earlier attestation in this exact corpus.”
- No real count or verdict goes into the video script until it appears in the post-Gate redacted
  output.
