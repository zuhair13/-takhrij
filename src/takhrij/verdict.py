"""Exactly three verdicts, derived from trace facts and model classifications."""

from __future__ import annotations

from collections.abc import Iterable

from takhrij.models import ClassifiedMatch, MatchClass, Verdict


def derive_verdict(
    matches: Iterable[ClassifiedMatch],
    *,
    cutoff_year_ah: int,
    coverage_complete: bool,
) -> Verdict:
    items = list(matches)
    for item in items:
        year = item.hit.provenance.comparison_year_ah
        if (
            item.classification is MatchClass.TARGET_USE
            and year is not None
            and year < cutoff_year_ah
        ):
            return Verdict.EARLIER_MATCH_FOUND

    if not coverage_complete:
        return Verdict.INCONCLUSIVE

    for item in items:
        year = item.hit.provenance.comparison_year_ah
        could_precede_cutoff = year is None or year < cutoff_year_ah
        if could_precede_cutoff and item.classification is MatchClass.UNCERTAIN:
            return Verdict.INCONCLUSIVE
        if year is None and item.classification is MatchClass.TARGET_USE:
            return Verdict.INCONCLUSIVE

    return Verdict.NO_EARLIER_MATCH_IN_DECLARED_CORPUS
