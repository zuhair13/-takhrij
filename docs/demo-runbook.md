# Four-minute demo runbook

Use a real, preflighted corpus case. The synthetic fixture is only for engineering rehearsal.

| Time | Screen | Line |
|---:|---|---|
| 0:00–0:25 | Form, sense, cutoff AH, release, book count | “This is a falsifiable claim about this corpus, not Arabic history.” |
| 0:25–0:45 | Network response and Firestore queued doc | “The API returns 202; the research continues after the tab closes.” |
| 0:45–1:20 | First retrieval and provisional label | “The first pass found no earlier target use. It is explicitly provisional.” |
| 1:20–2:05 | Audit progress and Cloud Run log | “The system is required to argue against its own search.” |
| 2:05–2:35 | Missing variant and second exact lookup | “It caught an omitted variant; code, not the model, checks whether it exists.” |
| 2:35–3:10 | Earlier highlighted raw span and provenance | “The exact bytes resolve to the named source and date field.” |
| 3:10–3:35 | Final verdict flip | “The claim is falsified by the system built to test it.” |
| 3:35–3:50 | Deliberate Gate rejection clip | “Interpretation can be wrong; quotation and source linkage cannot be fabricated past this gate.” |
| 3:50–4:00 | Limits panel | “No corpus match is never proof of historical absence.” |

Preflight the chosen claim ten times with temperature zero. Save each dossier hash and reject the
case if the same inputs do not produce the same classifications and audit proposal consistently.
Warm the Cloud Run service immediately before recording, but keep the research execution live and
unedited.

For the deliberate Gate rejection rehearsal, corrupt only a copied fixture quote and run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_verdict_gate.py' \
  -k gate_rejects_changed_quote -v
```

Never corrupt or edit the production corpus for the recording.
