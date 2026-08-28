"""Domain types. Model judgements and deterministic facts remain visibly separate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    EARLIER_MATCH_FOUND = "EARLIER_MATCH_FOUND"
    NO_EARLIER_MATCH_IN_DECLARED_CORPUS = "NO_EARLIER_MATCH_IN_DECLARED_CORPUS"
    INCONCLUSIVE = "INCONCLUSIVE"


class MatchClass(StrEnum):
    TARGET_USE = "target_use"
    HOMOGRAPH = "homograph"
    UNCERTAIN = "uncertain"


class EvidenceRole(StrEnum):
    """How a matching string functions in its containing source."""

    INDEPENDENT_AUTHORIAL_USE = "independent_authorial_use"
    FORMULAIC_ALLUSION = "formulaic_allusion"
    DIRECT_QUOTATION = "direct_quotation"
    ATTRIBUTED_QUOTATION = "attributed_quotation"
    METALINGUISTIC_MENTION = "metalinguistic_mention"
    UNCERTAIN = "uncertain"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Claim:
    form: str
    target_sense: str
    cutoff_year_ah: int
    corpus_release: str
    book_ids: tuple[str, ...]

    def proposition(self) -> str:
        return (
            f"No independent authorial target-use attestation of any enumerated variant "
            f"of {self.form!r} "
            f"in the stated sense occurs before {self.cutoff_year_ah} AH within "
            f"corpus release {self.corpus_release} and the declared book list."
        )

    def boundary_statement(self, verdict: Verdict) -> str:
        scope = f"corpus release {self.corpus_release} and its declared book list"
        if verdict is Verdict.EARLIER_MATCH_FOUND:
            return f"An earlier independent authorial target-use match was found within {scope}."
        if verdict is Verdict.NO_EARLIER_MATCH_IN_DECLARED_CORPUS:
            return f"No earlier independent authorial target-use match was found within {scope}."
        return f"The available coverage or classifications were insufficient within {scope}."


@dataclass(frozen=True, slots=True)
class Provenance:
    author_death_year_ah: int | None = None
    composition_date_ah: int | None = None
    metadata_source_uri: str | None = None
    author_date_source_uri: str | None = None
    composition_date_source_uri: str | None = None
    edition_citation: str | None = None
    edition_date: str | None = None
    edition_source_uri: str | None = None
    witness_description: str | None = None
    witness_date: str | None = None
    witness_source_uri: str | None = None
    quality_status: str | None = None
    quality_notes: str | None = None

    @property
    def comparison_year_ah(self) -> int | None:
        return self.composition_date_ah or self.author_death_year_ah

    @property
    def date_basis(self) -> str | None:
        if self.composition_date_ah is not None:
            return "composition_date_ah"
        if self.author_death_year_ah is not None:
            return "author_death_year_ah"
        return None


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    title: str
    author: str
    raw_text: str
    source_uri: str
    corpus_release: str
    provenance: Provenance
    work_id: str = ""
    language: str = "ara"
    source_format: str = ""
    parser_version: str = ""
    source_sha256: str = ""
    raw_text_sha256: str = ""
    license_id: str = ""
    license_uri: str = ""
    selection_reason: str = ""


@dataclass(frozen=True, slots=True)
class Variant:
    surface_form: str
    source: str
    parent: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    doc_id: str
    title: str
    author: str
    source_uri: str
    corpus_release: str
    raw_start: int
    raw_end: int
    token_index: int
    raw_form: str
    normalized_form: str
    context_start: int
    context_end: int
    prefix: str
    match: str
    suffix: str
    provenance: Provenance
    work_id: str = ""
    language: str = "ara"
    source_format: str = ""
    parser_version: str = ""
    source_sha256: str = ""
    raw_text_sha256: str = ""
    license_id: str = ""
    license_uri: str = ""
    selection_reason: str = ""

    @property
    def key(self) -> str:
        return f"{self.doc_id}:{self.raw_start}:{self.raw_end}"


@dataclass(frozen=True, slots=True)
class ClassifiedMatch:
    hit: RetrievalHit
    classification: MatchClass
    evidence_role: EvidenceRole
    reason: str
    confidence: float


@dataclass(frozen=True, slots=True)
class SearchPass:
    name: str
    variants: tuple[Variant, ...]
    hit_keys: tuple[str, ...]
    total_hits: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class AuditFinding:
    kind: str
    rationale: str
    missing_variant: str | None = None


@dataclass(frozen=True, slots=True)
class AuditReport:
    completed: bool
    findings: tuple[AuditFinding, ...] = ()

    @property
    def proposed_variants(self) -> tuple[str, ...]:
        return tuple(f.missing_variant for f in self.findings if f.missing_variant)


@dataclass(slots=True)
class Dossier:
    claim: Claim
    claim_statement: str
    boundary_statement: str
    variants: list[Variant]
    matches: list[ClassifiedMatch]
    search_passes: list[SearchPass]
    audit: AuditReport
    provisional_verdict: Verdict
    verdict: Verdict
    coverage_complete: bool
    limitations: list[str]
    gate_passed: bool = False
    gate_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
