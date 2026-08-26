#!/usr/bin/env python3
"""Exercise the intended verdict reversal against synthetic, non-evidentiary text."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from takhrij.gate import IssuanceGate
from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index
from takhrij.models import AuditFinding, AuditReport, Claim, MatchClass
from takhrij.pipeline import (
    apply_classifications,
    assemble_dossier,
    expand_forms,
    merge_hits,
    retrieve_pass,
)
from takhrij.serde import plain


def decisions(hits):
    return [
        {
            "hit_key": hit.key,
            "classification": MatchClass.TARGET_USE.value,
            "reason": "Synthetic fixture marks this as the intended evidentiary sense.",
            "confidence": 1.0,
        }
        for hit in hits
    ]


def run_demo(index: CorpusIndex) -> None:
    claim = Claim(
        form="تخريج",
        target_sense="دليل يُستند إليه في الاستدلال",
        cutoff_year_ah=500,
        corpus_release="FIXTURE-ONLY",
        book_ids=("fixture-early", "fixture-late"),
    )
    initial_variants = expand_forms(claim.form, [], 64)
    initial_hits, initial_pass = retrieve_pass(
        index, claim, initial_variants, pass_name="initial", max_hits=200
    )
    initial_matches = apply_classifications(initial_hits, decisions(initial_hits))
    provisional = assemble_dossier(
        claim=claim,
        variants=initial_variants,
        matches=initial_matches,
        passes=[initial_pass],
        audit=AuditReport(completed=False),
    ).provisional_verdict

    audit = AuditReport(
        completed=True,
        findings=(
            AuditFinding(
                kind="missing_variant",
                rationale="The prepositional clitic may be attached to the token.",
                missing_variant="بالتخريج",
            ),
        ),
    )
    all_variants = expand_forms(claim.form, ["بالتخريج"], 64)
    initial_names = {item.surface_form for item in initial_variants}
    followup_variants = [item for item in all_variants if item.surface_form not in initial_names]
    followup_hits, followup_pass = retrieve_pass(
        index, claim, followup_variants, pass_name="devils_advocate_followup", max_hits=200
    )
    all_hits = merge_hits(initial_hits, followup_hits)
    dossier = assemble_dossier(
        claim=claim,
        variants=all_variants,
        matches=apply_classifications(all_hits, decisions(all_hits)),
        passes=[initial_pass, followup_pass],
        audit=audit,
    )
    IssuanceGate(index).issue(dossier)
    print(
        json.dumps(
            {
                "warning": "SYNTHETIC FIXTURE — NOT HISTORICAL EVIDENCE",
                "provisional_verdict": provisional.value,
                "final_dossier": plain(dossier),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="takhrij-fixture-") as directory:
        database = Path(directory) / "fixture.db"
        build_index(root / "config" / "corpus_manifest.fixture.json", database)
        run_demo(CorpusIndex(database))


if __name__ == "__main__":
    main()
