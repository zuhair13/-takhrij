"""Pure pipeline helpers used as deterministic ADK workflow nodes."""

from __future__ import annotations

from collections.abc import Iterable

from takhrij.index import CorpusIndex
from takhrij.models import (
    AuditFinding,
    AuditReport,
    Claim,
    ClassifiedMatch,
    Dossier,
    MatchClass,
    RetrievalHit,
    SearchPass,
    Variant,
)
from takhrij.normalization import build_variant_set
from takhrij.verdict import derive_verdict

MIN_CLASSIFICATION_CONFIDENCE = 0.80


def retrieve_pass(
    index: CorpusIndex,
    claim: Claim,
    variants: list[Variant],
    *,
    pass_name: str,
    max_hits: int,
) -> tuple[list[RetrievalHit], SearchPass]:
    hits, total, truncated = index.search(
        variants,
        book_ids=claim.book_ids,
        max_hits=max_hits,
    )
    return hits, SearchPass(
        name=pass_name,
        variants=tuple(variants),
        hit_keys=tuple(hit.key for hit in hits),
        total_hits=total,
        truncated=truncated,
    )


def merge_hits(*groups: Iterable[RetrievalHit]) -> list[RetrievalHit]:
    by_key: dict[str, RetrievalHit] = {}
    for group in groups:
        for hit in group:
            by_key[hit.key] = hit
    return sorted(
        by_key.values(),
        key=lambda hit: (hit.provenance.comparison_year_ah or 999999, hit.doc_id, hit.raw_start),
    )


def apply_classifications(
    hits: Iterable[RetrievalHit], decisions: Iterable[dict[str, object]]
) -> list[ClassifiedMatch]:
    decision_map = {str(item.get("hit_key")): item for item in decisions}
    classified: list[ClassifiedMatch] = []
    for hit in hits:
        decision = decision_map.get(hit.key)
        if decision is None:
            classified.append(
                ClassifiedMatch(hit, MatchClass.UNCERTAIN, "No model decision returned.", 0.0)
            )
            continue
        try:
            label = MatchClass(str(decision.get("classification")))
            confidence = float(decision.get("confidence", 0.0))
        except (TypeError, ValueError):
            label = MatchClass.UNCERTAIN
            confidence = 0.0
        if not 0.0 <= confidence <= 1.0:
            label = MatchClass.UNCERTAIN
            confidence = 0.0
        reason = str(decision.get("reason") or "No reason supplied.")
        if label is not MatchClass.UNCERTAIN and confidence < MIN_CLASSIFICATION_CONFIDENCE:
            label = MatchClass.UNCERTAIN
            reason = (
                f"Below deterministic confidence threshold "
                f"({confidence:.2f} < {MIN_CLASSIFICATION_CONFIDENCE:.2f}). {reason}"
            )
        classified.append(ClassifiedMatch(hit, label, reason, confidence))
    return classified


def parse_audit(payload: dict[str, object]) -> AuditReport:
    findings: list[AuditFinding] = []
    raw_findings = payload.get("findings", [])
    if isinstance(raw_findings, list):
        for raw in raw_findings:
            if not isinstance(raw, dict):
                continue
            findings.append(
                AuditFinding(
                    kind=str(raw.get("kind") or "other"),
                    rationale=str(raw.get("rationale") or "No rationale supplied."),
                    missing_variant=(
                        str(raw["missing_variant"]) if raw.get("missing_variant") else None
                    ),
                )
            )
    return AuditReport(completed=bool(payload.get("completed")), findings=tuple(findings))


def assemble_dossier(
    *,
    claim: Claim,
    variants: list[Variant],
    matches: list[ClassifiedMatch],
    passes: list[SearchPass],
    audit: AuditReport,
) -> Dossier:
    initial_keys = set(passes[0].hit_keys) if passes else set()
    initial_matches = [item for item in matches if item.hit.key in initial_keys]
    initial_complete = bool(passes) and not passes[0].truncated
    provisional = derive_verdict(
        initial_matches,
        cutoff_year_ah=claim.cutoff_year_ah,
        coverage_complete=initial_complete,
    )
    blocking_audit_kinds = {"thin_time_slice", "metadata_conflict"}
    unresolved_coverage_finding = any(
        finding.kind in blocking_audit_kinds for finding in audit.findings
    )
    coverage_complete = (
        audit.completed
        and all(not item.truncated for item in passes)
        and not unresolved_coverage_finding
    )
    verdict = derive_verdict(
        matches,
        cutoff_year_ah=claim.cutoff_year_ah,
        coverage_complete=coverage_complete,
    )
    limitations = [
        "Absence from this declared corpus is not absence from Arabic history.",
        "Author death year is a comparison proxy, not the date a form entered the language.",
        (
            "The Gate verifies quotations, offsets, source resolution, and metadata; "
            "semantic classifications remain model judgements."
        ),
        "Version 1 searches single tokens only.",
    ]
    if any(item.truncated for item in passes):
        limitations.append("The configured match limit was exceeded; the result is incomplete.")
    return Dossier(
        claim=claim,
        claim_statement=claim.proposition(),
        boundary_statement=claim.boundary_statement(verdict),
        variants=variants,
        matches=matches,
        search_passes=passes,
        audit=audit,
        provisional_verdict=provisional,
        verdict=verdict,
        coverage_complete=coverage_complete,
        limitations=limitations,
    )


def expand_forms(original: str, forms: list[str], max_variants: int) -> list[Variant]:
    return build_variant_set(original, forms, max_variants=max_variants)
