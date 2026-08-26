"""Strict corpus-manifest loading and licence-boundary validation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
FIXTURE_KIND = "synthetic_fixture"
APPROVED_KIND = "approved_corpus"
SOURCE_FORMATS = frozenset(("plain_text", "openiti_mARkdown"))
APPROVAL_STATUSES = frozenset(("written_permission_required", "written_permission_granted"))
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ROOT_FIELDS = frozenset(
    (
        "schema_version",
        "release",
        "release_date",
        "release_uri",
        "release_doi",
        "content_kind",
        "license",
        "attribution",
        "approval",
        "source_root_env",
        "documents",
    )
)
DOCUMENT_FIELDS = frozenset(
    (
        "doc_id",
        "work_id",
        "title",
        "author",
        "path",
        "source_uri",
        "source_sha256",
        "source_format",
        "language",
        "calendar",
        "selection_reason",
        "provenance",
    )
)
PROVENANCE_FIELDS = frozenset(
    (
        "metadata_source_uri",
        "author_death_year_ah",
        "author_date_source_uri",
        "composition_date_ah",
        "composition_date_source_uri",
        "edition_citation",
        "edition_date",
        "edition_source_uri",
        "witness_description",
        "witness_date",
        "witness_source_uri",
        "quality_status",
        "quality_notes",
    )
)


class ManifestError(ValueError):
    """Raised when a corpus manifest violates the deterministic contract."""


@dataclass(frozen=True, slots=True)
class LicenceSpec:
    identifier: str
    uri: str


@dataclass(frozen=True, slots=True)
class ApprovalSpec:
    status: str
    reference: str


@dataclass(frozen=True, slots=True)
class ProvenanceSpec:
    metadata_source_uri: str
    author_death_year_ah: int | None
    author_date_source_uri: str | None
    composition_date_ah: int | None
    composition_date_source_uri: str | None
    edition_citation: str | None
    edition_date: str | None
    edition_source_uri: str | None
    witness_description: str | None
    witness_date: str | None
    witness_source_uri: str | None
    quality_status: str
    quality_notes: str


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    doc_id: str
    work_id: str
    title: str
    author: str
    path: str
    source_uri: str
    source_sha256: str
    source_format: str
    language: str
    calendar: str
    selection_reason: str
    provenance: ProvenanceSpec


@dataclass(frozen=True, slots=True)
class CorpusManifest:
    schema_version: int
    release: str
    release_date: str | None
    release_uri: str
    release_doi: str | None
    content_kind: str
    licence: LicenceSpec
    attribution: str
    approval: ApprovalSpec
    source_root_env: str | None
    documents: tuple[DocumentSpec, ...]
    canonical_sha256: str


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be an object")
    return value


def _reject_unknown(data: dict[str, Any], allowed: frozenset[str], field: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ManifestError(f"{field} contains unknown fields: {unknown}")


def _require_fields(data: dict[str, Any], required: frozenset[str], field: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise ManifestError(f"{field} is missing required fields: {missing}")


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field)


def _ah_year(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1600:
        raise ManifestError(f"{field} must be null or an AH integer from 1 through 1600")
    return value


def _provenance(raw: Any, prefix: str) -> ProvenanceSpec:
    data = _mapping(raw, prefix)
    _reject_unknown(data, PROVENANCE_FIELDS, prefix)
    _require_fields(data, PROVENANCE_FIELDS, prefix)
    author_year = _ah_year(data.get("author_death_year_ah"), f"{prefix}.author_death_year_ah")
    composition_year = _ah_year(
        data.get("composition_date_ah"), f"{prefix}.composition_date_ah"
    )
    author_source = _optional_string(
        data.get("author_date_source_uri"), f"{prefix}.author_date_source_uri"
    )
    composition_source = _optional_string(
        data.get("composition_date_source_uri"), f"{prefix}.composition_date_source_uri"
    )
    if author_year is not None and author_source is None:
        raise ManifestError(f"{prefix}.author_date_source_uri is required with an author date")
    if composition_year is not None and composition_source is None:
        raise ManifestError(
            f"{prefix}.composition_date_source_uri is required with a composition date"
        )
    edition_citation = _optional_string(
        data.get("edition_citation"), f"{prefix}.edition_citation"
    )
    edition_date = _optional_string(data.get("edition_date"), f"{prefix}.edition_date")
    edition_source = _optional_string(
        data.get("edition_source_uri"), f"{prefix}.edition_source_uri"
    )
    if (edition_citation is not None or edition_date is not None) and edition_source is None:
        raise ManifestError(f"{prefix}.edition_source_uri is required with edition metadata")
    witness_description = _optional_string(
        data.get("witness_description"), f"{prefix}.witness_description"
    )
    witness_date = _optional_string(data.get("witness_date"), f"{prefix}.witness_date")
    witness_source = _optional_string(
        data.get("witness_source_uri"), f"{prefix}.witness_source_uri"
    )
    if (witness_description is not None or witness_date is not None) and witness_source is None:
        raise ManifestError(f"{prefix}.witness_source_uri is required with witness metadata")
    return ProvenanceSpec(
        metadata_source_uri=_nonempty(
            data.get("metadata_source_uri"), f"{prefix}.metadata_source_uri"
        ),
        author_death_year_ah=author_year,
        author_date_source_uri=author_source,
        composition_date_ah=composition_year,
        composition_date_source_uri=composition_source,
        edition_citation=edition_citation,
        edition_date=edition_date,
        edition_source_uri=edition_source,
        witness_description=witness_description,
        witness_date=witness_date,
        witness_source_uri=witness_source,
        quality_status=_nonempty(data.get("quality_status"), f"{prefix}.quality_status"),
        quality_notes=_nonempty(data.get("quality_notes"), f"{prefix}.quality_notes"),
    )


def _document(raw: Any, index: int) -> DocumentSpec:
    prefix = f"documents[{index}]"
    data = _mapping(raw, prefix)
    _reject_unknown(data, DOCUMENT_FIELDS, prefix)
    _require_fields(data, DOCUMENT_FIELDS, prefix)
    source_sha256 = _nonempty(data.get("source_sha256"), f"{prefix}.source_sha256").lower()
    if SHA256_RE.fullmatch(source_sha256) is None:
        raise ManifestError(f"{prefix}.source_sha256 must be 64 lowercase hexadecimal digits")
    source_format = _nonempty(data.get("source_format"), f"{prefix}.source_format")
    if source_format not in SOURCE_FORMATS:
        raise ManifestError(
            f"{prefix}.source_format must be one of {sorted(SOURCE_FORMATS)}"
        )
    calendar = data.get("calendar")
    if calendar != "AH":
        raise ManifestError(f"{prefix}.calendar must be explicitly AH")
    language = _nonempty(data.get("language"), f"{prefix}.language")
    if language != "ara":
        raise ManifestError(f"{prefix}.language must be ara for the Revision 4.1 corpus")
    return DocumentSpec(
        doc_id=_nonempty(data.get("doc_id"), f"{prefix}.doc_id"),
        work_id=_nonempty(data.get("work_id"), f"{prefix}.work_id"),
        title=_nonempty(data.get("title"), f"{prefix}.title"),
        author=_nonempty(data.get("author"), f"{prefix}.author"),
        path=_nonempty(data.get("path"), f"{prefix}.path"),
        source_uri=_nonempty(data.get("source_uri"), f"{prefix}.source_uri"),
        source_sha256=source_sha256,
        source_format=source_format,
        language=language,
        calendar=calendar,
        selection_reason=_nonempty(
            data.get("selection_reason"), f"{prefix}.selection_reason"
        ),
        provenance=_provenance(data.get("provenance"), f"{prefix}.provenance"),
    )


def load_manifest(path: Path) -> CorpusManifest:
    """Load a manifest without resolving or reading any corpus source file."""
    raw_bytes = path.read_bytes()
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid UTF-8 JSON manifest: {path}") from exc
    root = _mapping(data, "manifest")
    _reject_unknown(root, ROOT_FIELDS, "manifest")
    _require_fields(root, ROOT_FIELDS, "manifest")
    if root.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {MANIFEST_SCHEMA_VERSION}")
    content_kind = _nonempty(root.get("content_kind"), "content_kind")
    if content_kind not in {FIXTURE_KIND, APPROVED_KIND}:
        raise ManifestError("content_kind must be synthetic_fixture or approved_corpus")
    licence_data = _mapping(root.get("license"), "license")
    _reject_unknown(licence_data, frozenset(("id", "uri")), "license")
    _require_fields(licence_data, frozenset(("id", "uri")), "license")
    approval_data = _mapping(root.get("approval"), "approval")
    _reject_unknown(approval_data, frozenset(("status", "reference")), "approval")
    _require_fields(approval_data, frozenset(("status", "reference")), "approval")
    raw_documents = root.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise ManifestError("documents must be a non-empty list")
    documents = tuple(_document(item, index) for index, item in enumerate(raw_documents))
    ids = [document.doc_id for document in documents]
    if len(ids) != len(set(ids)):
        raise ManifestError("documents must have unique doc_id values")

    release = _nonempty(root.get("release"), "release")
    approval = ApprovalSpec(
        status=_nonempty(approval_data.get("status"), "approval.status"),
        reference=_nonempty(approval_data.get("reference"), "approval.reference"),
    )
    source_root_env = _optional_string(root.get("source_root_env"), "source_root_env")
    if content_kind == FIXTURE_KIND:
        if release != "FIXTURE-ONLY":
            raise ManifestError("synthetic_fixture manifests must use release FIXTURE-ONLY")
        if approval.status != "not_required":
            raise ManifestError("synthetic_fixture approval.status must be not_required")
        if source_root_env is not None:
            raise ManifestError("synthetic_fixture manifests may not set source_root_env")
    else:
        if release == "FIXTURE-ONLY":
            raise ManifestError("approved_corpus manifests may not use FIXTURE-ONLY")
        if approval.status not in APPROVAL_STATUSES:
            raise ManifestError(
                f"approved_corpus approval.status must be one of {sorted(APPROVAL_STATUSES)}"
            )
        if (
            approval.status == "written_permission_granted"
            and "REPLACE_WITH" in approval.reference.upper()
        ):
            raise ManifestError(
                "written_permission_granted requires a real approval.reference"
            )
        if source_root_env is None:
            raise ManifestError("approved_corpus manifests require source_root_env")

    import hashlib

    canonical = json.dumps(root, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return CorpusManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        release=release,
        release_date=_optional_string(root.get("release_date"), "release_date"),
        release_uri=_nonempty(root.get("release_uri"), "release_uri"),
        release_doi=_optional_string(root.get("release_doi"), "release_doi"),
        content_kind=content_kind,
        licence=LicenceSpec(
            identifier=_nonempty(licence_data.get("id"), "license.id"),
            uri=_nonempty(licence_data.get("uri"), "license.uri"),
        ),
        attribution=_nonempty(root.get("attribution"), "attribution"),
        approval=approval,
        source_root_env=source_root_env,
        documents=documents,
        canonical_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def resolve_source_root(manifest: CorpusManifest, manifest_path: Path) -> Path:
    """Resolve a source root while keeping approved material outside the repository."""
    if manifest.content_kind == FIXTURE_KIND:
        return manifest_path.resolve().parent
    assert manifest.source_root_env is not None
    configured = os.getenv(manifest.source_root_env, "").strip()
    if not configured:
        raise ManifestError(
            f"{manifest.source_root_env} must name the approved external source root"
        )
    root = Path(configured).resolve()
    repository_root = manifest_path.resolve().parents[1]
    if root == repository_root or repository_root in root.parents:
        raise ManifestError("approved corpus source root must be outside the repository")
    if not root.is_dir():
        raise ManifestError(f"approved corpus source root does not exist: {root}")
    return root


def resolve_document_path(
    manifest: CorpusManifest, manifest_path: Path, document: DocumentSpec
) -> Path:
    if manifest.content_kind == FIXTURE_KIND:
        path = (manifest_path.resolve().parent / document.path).resolve()
        fixture_root = manifest_path.resolve().parents[1] / "tests" / "fixtures"
        if path != fixture_root and fixture_root not in path.parents:
            raise ManifestError(f"{document.doc_id}: fixture source must be under tests/fixtures")
        if not document.source_uri.startswith("fixture://"):
            raise ManifestError(f"{document.doc_id}: fixture source_uri must use fixture://")
        return path
    root = resolve_source_root(manifest, manifest_path)
    path = (root / document.path).resolve()
    if path != root and root not in path.parents:
        raise ManifestError(f"{document.doc_id}: path escapes the configured source root")
    return path
