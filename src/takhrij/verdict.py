"""Exactly three verdicts, derived from trace facts and model classifications."""

from __future__ import annotations

from collections.abc import Iterable

from takhrij.models import ClassifiedMatch, EvidenceRole, MatchClass, Verdict


def is_qualifying_attestation(item: ClassifiedMatch) -> bool:
    """Return whether a match satisfies the frozen evidentiary predicate."""
    return (
        item.classification is MatchClass.TARGET_USE
        and item.evidence_role is EvidenceRole.INDEPENDENT_AUTHORIAL_USE
    )


def could_be_qualifying_attestation(item: ClassifiedMatch) -> bool:
    """Return whether unresolved judgement could still satisfy the predicate."""
    semantic_possible = item.classification in {MatchClass.TARGET_USE, MatchClass.UNCERTAIN}
    role_possible = item.evidence_role in {
        EvidenceRole.INDEPENDENT_AUTHORIAL_USE,
        EvidenceRole.UNCERTAIN,
    }
    return semantic_possible and role_possible


def derive_verdict(
    matches: Iterable[ClassifiedMatch],
    *,
    cutoff_year_ah: int,
    coverage_complete: bool,
) -> Verdict:
    items = list(matches)
    for item in items:
        year = item.hit.provenance.comparison_year_ah
        if is_qualifying_attestation(item) and year is not None and year < cutoff_year_ah:
            return Verdict.EARLIER_MATCH_FOUND

    if not coverage_complete:
        return Verdict.INCONCLUSIVE

    for item in items:
        year = item.hit.provenance.comparison_year_ah
        could_precede_cutoff = year is None or year < cutoff_year_ah
        if could_precede_cutoff and could_be_qualifying_attestation(item):
            return Verdict.INCONCLUSIVE

    return Verdict.NO_EARLIER_MATCH_IN_DECLARED_CORPUS
