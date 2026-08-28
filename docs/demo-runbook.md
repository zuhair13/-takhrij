# Four-minute judge demo

The first sentence is the product:

> A word found in a book is not necessarily a word used by its author.

The demo shows one complete research decision, not an agent waiting for days. Search retrieves
strings; TAKHRIJ adjudicates which matches count as historical evidence.

| Time | Screen | Line |
|---:|---|---|
| 0:00–0:20 | Input and frozen corpus boundary | “I am testing independent authorial use before this cutoff—not whether the string appears anywhere.” |
| 0:20–0:45 | Raw-hit counter | “Ordinary search stops here. These are string matches, not yet attestations.” |
| 0:45–1:25 | Three hit cards | “Gemini answers two separate questions: target meaning, then evidence role.” |
| 1:25–1:55 | Quotation and mention marked “context only” | “A target-sense quotation is real text, but it does not prove this book's author independently used the word.” |
| 1:55–2:25 | Independent-use card and dates | “Only target sense plus independent authorial use plus a secure pre-cutoff date can affect the verdict.” |
| 2:25–2:55 | Devil's Advocate progress and second lookup | “The agent attacks the search coverage; deterministic tools execute any missing-form lookup.” |
| 2:55–3:20 | Gate badge and source/hash fields | “The model interprets context. Code rechecks existence, quote bytes, offsets, source, date, and verdict derivation.” |
| 3:20–3:40 | One-glance architecture / Cloud Run service | “This is a reusable attestation layer for historical language search, built with ADK, Gemini on Google Cloud, and Cloud Run.” |
| 3:40–4:00 | Limits and licence line | “The result is corpus-bounded. The real corpus run is local and redacted; the public image remains synthetic.” |

## Recording choice

Use a completed local OpenITI run only after all of these are true:

- the five pinned source hashes match;
- ADC reaches the configured Google Cloud project;
- the same input has been preflighted for stable two-axis labels;
- the output is the server-side redacted, post-Gate dossier;
- the spoken result exactly matches the recorded dossier.

If any condition fails, record the synthetic fixture and label it on screen as non-evidentiary.
Never invent a real corpus count or verdict.

## Fast rehearsal

```bash
PYTHONPATH=src python scripts/run_fixture_demo.py
PYTHONPATH=src python -m unittest tests.test_verdict_gate -v
```

The fixture's intended one-glance result is:

```text
3 raw matches · 2 before cutoff · 0 qualifying earlier evidence
```

The earlier matches are a direct quotation and a metalinguistic mention. The independent authorial
use is later than the cutoff, so the negative corpus-bounded verdict is valid.

For the deliberate Gate rejection clip, corrupt only a copied fixture quote and run:

```bash
PYTHONPATH=src python -m unittest tests.test_verdict_gate \
  -k gate_rejects_changed_quote -v
```

## Submission disclosure

Use this sentence in Devpost:

> OpenITI is used only in a local non-commercial run under CC BY-NC-SA 4.0 with attribution; the
> public deployment remains on a synthetic fixture pending permission to distribute the derived
> index.
