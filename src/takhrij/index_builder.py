"""Build an immutable SQLite postings index from an explicit corpus manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from takhrij.ingestion import ingest_source
from takhrij.manifest import APPROVED_KIND, CorpusManifest, load_manifest, resolve_document_path
from takhrij.normalization import normalize_token, tokenize_with_offsets

SCHEMA_VERSION = 5
APPROVED_STATUS = "written_permission_granted"

SCHEMA = """
PRAGMA page_size = 4096;
PRAGMA journal_mode = DELETE;
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = NONE;

CREATE TABLE corpus_metadata (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE documents (
  doc_id                       TEXT PRIMARY KEY,
  work_id                      TEXT NOT NULL,
  title                        TEXT NOT NULL,
  author                       TEXT NOT NULL,
  raw_text                     TEXT NOT NULL,
  source_uri                   TEXT NOT NULL,
  corpus_release               TEXT NOT NULL,
  language                     TEXT NOT NULL,
  source_format                TEXT NOT NULL,
  parser_version               TEXT NOT NULL,
  source_sha256                TEXT NOT NULL,
  raw_text_sha256              TEXT NOT NULL,
  license_id                   TEXT NOT NULL,
  license_uri                  TEXT NOT NULL,
  selection_reason             TEXT NOT NULL,
  metadata_source_uri          TEXT NOT NULL,
  author_death_year_ah         INTEGER,
  author_date_source_uri       TEXT,
  composition_date_ah          INTEGER,
  composition_date_source_uri  TEXT,
  edition_citation             TEXT,
  edition_date                 TEXT,
  edition_source_uri           TEXT,
  witness_description          TEXT,
  witness_date                 TEXT,
  witness_source_uri           TEXT,
  quality_status               TEXT NOT NULL,
  quality_notes                TEXT NOT NULL
);

CREATE TABLE postings (
  normalized_form TEXT NOT NULL,
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  raw_start       INTEGER NOT NULL,
  raw_end         INTEGER NOT NULL,
  token_index     INTEGER NOT NULL,
  PRIMARY KEY (doc_id, raw_start, raw_end)
);

CREATE INDEX idx_normalized_form ON postings(normalized_form);
CREATE INDEX idx_posting_doc ON postings(doc_id);
"""


def _repository_root(manifest_path: Path) -> Path:
    for candidate in (manifest_path.resolve().parent, *manifest_path.resolve().parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ValueError("manifest must be located within the TAKHRIJ repository")


def _enforce_approval_boundary(
    manifest: CorpusManifest,
    manifest_path: Path,
    output_path: Path,
    *,
    allow_approved_corpus: bool,
) -> None:
    if manifest.content_kind != APPROVED_KIND:
        return
    if not allow_approved_corpus:
        raise PermissionError(
            "approved corpus builds require the explicit --allow-approved-corpus flag"
        )
    if manifest.approval.status != APPROVED_STATUS:
        raise PermissionError(
            f"approved corpus build blocked: approval.status must be {APPROVED_STATUS}"
        )
    repository_root = _repository_root(manifest_path)
    resolved_output = output_path.resolve()
    if resolved_output == repository_root or repository_root in resolved_output.parents:
        raise PermissionError("approved derived databases must be built outside the repository")


def _document_row(document: Any, ingested: Any, manifest: CorpusManifest) -> tuple[Any, ...]:
    provenance = document.provenance
    return (
        document.doc_id,
        document.work_id,
        document.title,
        document.author,
        ingested.raw_text,
        document.source_uri,
        manifest.release,
        document.language,
        document.source_format,
        ingested.parser_version,
        ingested.source_sha256,
        ingested.raw_text_sha256,
        manifest.licence.identifier,
        manifest.licence.uri,
        document.selection_reason,
        provenance.metadata_source_uri,
        provenance.author_death_year_ah,
        provenance.author_date_source_uri,
        provenance.composition_date_ah,
        provenance.composition_date_source_uri,
        provenance.edition_citation,
        provenance.edition_date,
        provenance.edition_source_uri,
        provenance.witness_description,
        provenance.witness_date,
        provenance.witness_source_uri,
        provenance.quality_status,
        provenance.quality_notes,
    )


def build_index(
    manifest_path: Path,
    output_path: Path,
    *,
    allow_approved_corpus: bool = False,
) -> dict[str, Any]:
    """Build a deterministic database; real-data builds are explicit and external-only."""
    started = time.perf_counter()
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    output_path = output_path.resolve()
    _enforce_approval_boundary(
        manifest,
        manifest_path,
        output_path,
        allow_approved_corpus=allow_approved_corpus,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".building")
    if temporary.exists():
        temporary.unlink()

    digest = hashlib.sha256(manifest.canonical_sha256.encode("ascii"))
    token_count = 0
    try:
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.executescript(SCHEMA)
            for document in manifest.documents:
                source_path = resolve_document_path(manifest, manifest_path, document)
                ingested = ingest_source(
                    source_path,
                    document.source_format,
                    document.source_sha256,
                )
                digest.update(document.doc_id.encode("utf-8"))
                digest.update(ingested.raw_text_sha256.encode("ascii"))
                connection.execute(
                    """
                    INSERT INTO documents (
                      doc_id, work_id, title, author, raw_text, source_uri, corpus_release,
                      language, source_format, parser_version, source_sha256, raw_text_sha256,
                      license_id, license_uri, selection_reason, metadata_source_uri,
                      author_death_year_ah, author_date_source_uri, composition_date_ah,
                      composition_date_source_uri, edition_citation, edition_date,
                      edition_source_uri, witness_description, witness_date,
                      witness_source_uri, quality_status, quality_notes
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?
                    )
                    """,
                    _document_row(document, ingested, manifest),
                )
                rows = [
                    (normalize_token(token), document.doc_id, start, end, index)
                    for index, (token, start, end) in enumerate(
                        tokenize_with_offsets(ingested.raw_text)
                    )
                ]
                connection.executemany("INSERT INTO postings VALUES (?, ?, ?, ?, ?)", rows)
                token_count += len(rows)
            metadata = {
                "release": manifest.release,
                "release_date": manifest.release_date or "",
                "release_uri": manifest.release_uri,
                "release_doi": manifest.release_doi or "",
                "content_kind": manifest.content_kind,
                "license": manifest.licence.identifier,
                "license_uri": manifest.licence.uri,
                "attribution": manifest.attribution,
                "approval_status": manifest.approval.status,
                "approval_reference": manifest.approval.reference,
                "manifest_sha256": manifest.canonical_sha256,
                "document_count": str(len(manifest.documents)),
                "token_count": str(token_count),
                "corpus_sha256": digest.hexdigest(),
                "offset_unit": "unicode_code_points",
                "schema_version": str(SCHEMA_VERSION),
            }
            connection.executemany(
                "INSERT INTO corpus_metadata VALUES (?, ?)", sorted(metadata.items())
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("ANALYZE")
        os.replace(temporary, output_path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise

    database_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        **metadata,
        "database_sha256": database_sha256,
        "build_seconds": round(time.perf_counter() - started, 3),
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--allow-approved-corpus",
        action="store_true",
        help="permit a written-permission manifest to read an external corpus root",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_index(
                args.manifest,
                args.output,
                allow_approved_corpus=args.allow_approved_corpus,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
