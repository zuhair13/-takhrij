"""Build the immutable SQLite postings index from an explicit corpus manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from takhrij.normalization import normalize_token, tokenize_with_offsets

SCHEMA = """
PRAGMA journal_mode = DELETE;
PRAGMA foreign_keys = ON;

CREATE TABLE corpus_metadata (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE documents (
  doc_id                TEXT PRIMARY KEY,
  title                 TEXT NOT NULL,
  author                TEXT NOT NULL,
  raw_text              TEXT NOT NULL,
  source_uri            TEXT NOT NULL,
  corpus_release        TEXT NOT NULL,
  author_death_year_ah  INTEGER,
  composition_date_ah   INTEGER,
  edition_date          TEXT,
  witness_date          TEXT
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

REQUIRED_DOC_KEYS = {"doc_id", "title", "author", "path", "source_uri"}


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if not manifest.get("release"):
        raise ValueError("manifest.release is required")
    if not manifest.get("license"):
        raise ValueError("manifest.license is required")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("manifest.documents must be a non-empty list")
    ids: set[str] = set()
    for document in documents:
        missing = REQUIRED_DOC_KEYS - document.keys()
        if missing:
            raise ValueError(f"document is missing keys: {sorted(missing)}")
        if document["doc_id"] in ids:
            raise ValueError(f"duplicate doc_id: {document['doc_id']}")
        ids.add(document["doc_id"])
        if document.get("calendar") != "AH":
            raise ValueError(f"{document['doc_id']}: v1 date metadata must be explicitly AH")
        for field in ("author_death_year_ah", "composition_date_ah"):
            value = document.get(field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1600
            ):
                raise ValueError(f"{document['doc_id']}: {field} must be null or an AH integer")


def build_index(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".building")
    if temporary.exists():
        temporary.unlink()

    digest = hashlib.sha256()
    token_count = 0
    with sqlite3.connect(temporary) as connection:
        connection.executescript(SCHEMA)
        for document in manifest["documents"]:
            source_path = (manifest_path.parent / document["path"]).resolve()
            raw_text = source_path.read_text(encoding="utf-8")
            digest.update(document["doc_id"].encode())
            digest.update(raw_text.encode())
            connection.execute(
                """
                INSERT INTO documents (
                  doc_id, title, author, raw_text, source_uri, corpus_release,
                  author_death_year_ah, composition_date_ah, edition_date, witness_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document["doc_id"],
                    document["title"],
                    document["author"],
                    raw_text,
                    document["source_uri"],
                    manifest["release"],
                    document.get("author_death_year_ah"),
                    document.get("composition_date_ah"),
                    document.get("edition_date"),
                    document.get("witness_date"),
                ),
            )
            rows = [
                (normalize_token(token), document["doc_id"], start, end, index)
                for index, (token, start, end) in enumerate(tokenize_with_offsets(raw_text))
            ]
            connection.executemany(
                "INSERT INTO postings VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            token_count += len(rows)
        metadata = {
            "release": manifest["release"],
            "license": manifest["license"],
            "attribution": manifest.get("attribution", ""),
            "document_count": str(len(manifest["documents"])),
            "token_count": str(token_count),
            "corpus_sha256": digest.hexdigest(),
            "offset_unit": "unicode_code_points",
            "schema_version": "4",
        }
        connection.executemany("INSERT INTO corpus_metadata VALUES (?, ?)", metadata.items())
        connection.execute("PRAGMA user_version = 4")
        connection.execute("ANALYZE")
    os.replace(temporary, output_path)
    return {**metadata, "output": str(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_index(args.manifest, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
