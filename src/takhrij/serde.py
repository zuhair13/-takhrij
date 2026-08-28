"""Explicit serialization at the boundary between ADK events and domain objects."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from takhrij.models import (
    Claim,
    ClassifiedMatch,
    EvidenceRole,
    MatchClass,
    Provenance,
    RetrievalHit,
    SearchPass,
    Variant,
)


def plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def claim_from_dict(data: dict[str, Any]) -> Claim:
    return Claim(
        form=str(data["form"]),
        target_sense=str(data["target_sense"]),
        cutoff_year_ah=int(data["cutoff_year_ah"]),
        corpus_release=str(data["corpus_release"]),
        book_ids=tuple(str(item) for item in data["book_ids"]),
    )


def variant_from_dict(data: dict[str, Any]) -> Variant:
    return Variant(
        surface_form=str(data["surface_form"]),
        source=str(data["source"]),
        parent=str(data["parent"]) if data.get("parent") is not None else None,
    )


def provenance_from_dict(data: dict[str, Any]) -> Provenance:
    return Provenance(
        author_death_year_ah=data.get("author_death_year_ah"),
        composition_date_ah=data.get("composition_date_ah"),
        metadata_source_uri=data.get("metadata_source_uri"),
        author_date_source_uri=data.get("author_date_source_uri"),
        composition_date_source_uri=data.get("composition_date_source_uri"),
        edition_citation=data.get("edition_citation"),
        edition_date=data.get("edition_date"),
        edition_source_uri=data.get("edition_source_uri"),
        witness_description=data.get("witness_description"),
        witness_date=data.get("witness_date"),
        witness_source_uri=data.get("witness_source_uri"),
        quality_status=data.get("quality_status"),
        quality_notes=data.get("quality_notes"),
    )


def hit_from_dict(data: dict[str, Any]) -> RetrievalHit:
    return RetrievalHit(
        doc_id=str(data["doc_id"]),
        title=str(data["title"]),
        author=str(data["author"]),
        source_uri=str(data["source_uri"]),
        corpus_release=str(data["corpus_release"]),
        raw_start=int(data["raw_start"]),
        raw_end=int(data["raw_end"]),
        token_index=int(data["token_index"]),
        raw_form=str(data["raw_form"]),
        normalized_form=str(data["normalized_form"]),
        context_start=int(data["context_start"]),
        context_end=int(data["context_end"]),
        prefix=str(data["prefix"]),
        match=str(data["match"]),
        suffix=str(data["suffix"]),
        provenance=provenance_from_dict(data["provenance"]),
        work_id=str(data.get("work_id", "")),
        language=str(data.get("language", "ara")),
        source_format=str(data.get("source_format", "")),
        parser_version=str(data.get("parser_version", "")),
        source_sha256=str(data.get("source_sha256", "")),
        raw_text_sha256=str(data.get("raw_text_sha256", "")),
        license_id=str(data.get("license_id", "")),
        license_uri=str(data.get("license_uri", "")),
        selection_reason=str(data.get("selection_reason", "")),
    )


def search_pass_from_dict(data: dict[str, Any]) -> SearchPass:
    return SearchPass(
        name=str(data["name"]),
        variants=tuple(variant_from_dict(item) for item in data["variants"]),
        hit_keys=tuple(str(item) for item in data["hit_keys"]),
        total_hits=int(data["total_hits"]),
        truncated=bool(data["truncated"]),
    )


def classified_from_dict(data: dict[str, Any]) -> ClassifiedMatch:
    return ClassifiedMatch(
        hit=hit_from_dict(data["hit"]),
        classification=MatchClass(data["classification"]),
        evidence_role=EvidenceRole(data["evidence_role"]),
        reason=str(data["reason"]),
        confidence=float(data["confidence"]),
    )


def redact_dossier_for_display(dossier: dict[str, Any]) -> dict[str, Any]:
    """Remove licensed corpus text and free-form model excerpts after Gate issuance."""
    if dossier.get("gate_passed") is not True:
        raise ValueError("only a Gate-issued dossier may be redacted for display")
    visible = deepcopy(dossier)
    matches = visible.get("matches", [])
    if isinstance(matches, list):
        for item in matches:
            if not isinstance(item, dict):
                continue
            hit = item.get("hit")
            if isinstance(hit, dict):
                for field in ("raw_form", "prefix", "match", "suffix"):
                    hit.pop(field, None)
            item.pop("reason", None)
    audit = visible.get("audit")
    if isinstance(audit, dict):
        findings = audit.get("findings", [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    finding.pop("rationale", None)
    limitations = visible.setdefault("limitations", [])
    if isinstance(limitations, list):
        limitations.append(
            "Corpus text and free-form assessment rationales are redacted in local-only mode."
        )
    visible["display_policy"] = {
        "corpus_text": "redacted",
        "assessment_rationales": "redacted",
        "delivery_scope": "local_only",
    }
    return visible
