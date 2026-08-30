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
from takhrij.manifest import (
    APPROVED_KIND,
    FIXTURE_KIND,
    LOCAL_ONLY_STATUS,
    CorpusManifest,
    load_manifest,
    resolve_document_path,
)
from takhrij.normalization import normalize_token, tokenize_with_offsets

SCHEMA_VERSION = 5
LOGICAL_DATABASE_FORMAT_VERSION = 1
APPROVED_STATUS = "written_permission_granted"
FIXTURE_SCOPE = "fixture_only"
LOCAL_ONLY_SCOPE = "local_only"
APPROVED_SCOPE = "distribution_approved"

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


def _update_typed_value(digest: Any, value: Any) -> None:
    """Add one unambiguous SQLite value to a logical database digest."""
    if value is None:
        tag, payload = b"null", b""
    elif isinstance(value, int):
        tag, payload = b"integer", str(value).encode("ascii")
    elif isinstance(value, float):
        tag, payload = b"real", value.hex().encode("ascii")
    elif isinstance(value, str):
        tag, payload = b"text", value.encode("utf-8")
    elif isinstance(value, bytes):
        tag, payload = b"blob", value
    else:  # pragma: no cover - sqlite3 returns only the types above
        raise TypeError(f"unsupported SQLite value type: {type(value).__name__}")
    digest.update(len(tag).to_bytes(2, "big"))
    digest.update(tag)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _update_logical_rows(digest: Any, label: str, rows: list[tuple[Any, ...]]) -> None:
    _update_typed_value(digest, label)
    _update_typed_value(digest, len(rows))
    for row in rows:
        _update_typed_value(digest, len(row))
        for value in row:
            _update_typed_value(digest, value)


def logical_database_sha256(database_path: Path | str) -> str:
    """Hash TAKHRIJ schema and rows independently of SQLite file layout."""
    path = Path(database_path).resolve()
    digest = hashlib.sha256()
    digest.update(f"takhrij-logical-database-v{LOGICAL_DATABASE_FORMAT_VERSION}\n".encode("ascii"))
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only = ON")
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        _update_typed_value(digest, "user_version")
        _update_typed_value(digest, user_version)

        schema_rows = connection.execute(
            """
            SELECT type, name, tbl_name, sql
              FROM sqlite_schema
             WHERE name NOT LIKE 'sqlite_%'
             ORDER BY type, name, tbl_name
            """
        ).fetchall()
        _update_logical_rows(digest, "schema", schema_rows)

        logical_queries = (
            ("corpus_metadata", "SELECT key, value FROM corpus_metadata ORDER BY key"),
            ("documents", "SELECT * FROM documents ORDER BY doc_id"),
            (
                "postings",
                """SELECT normalized_form, doc_id, raw_start, raw_end, token_index
                     FROM postings
                 ORDER BY doc_id, raw_start, raw_end, normalized_form, token_index""",
            ),
        )
        for label, query in logical_queries:
            _update_logical_rows(digest, label, connection.execute(query).fetchall())
    return digest.hexdigest()


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
    allow_local_only_corpus: bool = False,
    allow_approved_corpus: bool = False,
) -> str:
    if allow_local_only_corpus and allow_approved_corpus:
        raise PermissionError("local-only and distribution-approved flags are mutually exclusive")
    if manifest.content_kind == FIXTURE_KIND:
        if allow_local_only_corpus or allow_approved_corpus:
            raise PermissionError("external-corpus flags may not be used with a fixture manifest")
        return FIXTURE_SCOPE
    if manifest.content_kind != APPROVED_KIND:
        raise PermissionError("unknown corpus content kind")

    status = manifest.approval.status
    if not allow_local_only_corpus and not allow_approved_corpus:
        raise PermissionError(
            "external corpus builds require an explicit --allow-local-only-corpus "
            "or --allow-approved-corpus flag"
        )
    if status == LOCAL_ONLY_STATUS and not allow_local_only_corpus:
        raise PermissionError(
            "local-only corpus builds require the explicit --allow-local-only-corpus flag"
        )
    if status == APPROVED_STATUS and not allow_approved_corpus:
        raise PermissionError(
            "distribution-approved corpus builds require the explicit "
            "--allow-approved-corpus flag"
        )
    if status not in {LOCAL_ONLY_STATUS, APPROVED_STATUS}:
        raise PermissionError(
            "external corpus build blocked: approval.status must be "
            f"{LOCAL_ONLY_STATUS} or {APPROVED_STATUS}"
        )
    if status == LOCAL_ONLY_STATUS and allow_approved_corpus:
        raise PermissionError("local-only corpus may not use the distribution-approved flag")
    if status == APPROVED_STATUS and allow_local_only_corpus:
        raise PermissionError("distribution-approved corpus may not use the local-only flag")

    repository_root = _repository_root(manifest_path)
    resolved_output = output_path.resolve()
    if resolved_output == repository_root or repository_root in resolved_output.parents:
        raise PermissionError("external derived databases must be built outside the repository")
    return LOCAL_ONLY_SCOPE if status == LOCAL_ONLY_STATUS else APPROVED_SCOPE


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
    allow_local_only_corpus: bool = False,
    allow_approved_corpus: bool = False,
) -> dict[str, Any]:
    """Build a deterministic database; real-data builds are explicit and external-only."""
    started = time.perf_counter()
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    output_path = output_path.resolve()
    delivery_scope = _enforce_approval_boundary(
        manifest,
        manifest_path,
        output_path,
        allow_local_only_corpus=allow_local_only_corpus,
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
                "delivery_scope": delivery_scope,
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
    logical_sha256 = logical_database_sha256(output_path)
    return {
        **metadata,
        "database_sha256": database_sha256,
        "logical_database_sha256": logical_sha256,
        "build_seconds": round(time.perf_counter() - started, 3),
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    corpus_mode = parser.add_mutually_exclusive_group()
    corpus_mode.add_argument(
        "--allow-local-only-corpus",
        action="store_true",
        help="permit a licence-reviewed corpus for a non-distributable local run",
    )
    corpus_mode.add_argument(
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
                allow_local_only_corpus=args.allow_local_only_corpus,
                allow_approved_corpus=args.allow_approved_corpus,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
