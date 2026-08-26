"""Read-only deterministic retrieval over the immutable SQLite corpus image."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from takhrij.models import Document, Provenance, RetrievalHit, Variant
from takhrij.normalization import normalize_token


class CorpusIndex:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        connection = sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def metadata(self) -> dict[str, str]:
        with closing(self._connect()) as connection:
            return dict(connection.execute("SELECT key, value FROM corpus_metadata").fetchall())

    def document_exists(self, doc_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        return row is not None

    def get_document(self, doc_id: str) -> Document | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        return _row_to_document(row) if row else None

    def declared_books_exist(self, book_ids: Iterable[str]) -> bool:
        expected = set(book_ids)
        if not expected:
            return False
        placeholders = ",".join("?" for _ in expected)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT doc_id FROM documents WHERE doc_id IN ({placeholders})", tuple(expected)
            ).fetchall()
        return {row["doc_id"] for row in rows} == expected

    def verify_raw_span(self, doc_id: str, start: int, end: int, expected: str) -> bool:
        document = self.get_document(doc_id)
        return bool(document and document.raw_text[start:end] == expected)

    def search(
        self,
        variants: Iterable[Variant],
        *,
        book_ids: tuple[str, ...],
        max_hits: int,
        context_chars: int = 110,
    ) -> tuple[list[RetrievalHit], int, bool]:
        normalized_forms = tuple(
            dict.fromkeys(normalize_token(variant.surface_form) for variant in variants)
        )
        if not normalized_forms or not book_ids:
            return [], 0, False
        form_slots = ",".join("?" for _ in normalized_forms)
        book_slots = ",".join("?" for _ in book_ids)
        where = f"p.normalized_form IN ({form_slots}) AND p.doc_id IN ({book_slots})"
        params = (*normalized_forms, *book_ids)
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM postings p WHERE {where}", params
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT p.normalized_form, p.doc_id, p.raw_start, p.raw_end, p.token_index,
                       d.work_id, d.title, d.author, d.raw_text, d.source_uri, d.corpus_release,
                       d.language, d.source_format, d.parser_version,
                       d.source_sha256, d.raw_text_sha256, d.license_id, d.license_uri,
                       d.selection_reason,
                       d.author_death_year_ah, d.composition_date_ah,
                       d.metadata_source_uri, d.author_date_source_uri,
                       d.composition_date_source_uri, d.edition_citation,
                       d.edition_date, d.edition_source_uri, d.witness_description,
                       d.witness_date, d.witness_source_uri,
                       d.quality_status, d.quality_notes
                  FROM postings p
                  JOIN documents d ON d.doc_id = p.doc_id
                 WHERE {where}
                 ORDER BY COALESCE(d.composition_date_ah, d.author_death_year_ah, 999999),
                          p.doc_id, p.raw_start
                 LIMIT ?
                """,
                (*params, max_hits),
            ).fetchall()

        hits: list[RetrievalHit] = []
        for row in rows:
            raw_text = row["raw_text"]
            raw_start = int(row["raw_start"])
            raw_end = int(row["raw_end"])
            context_start = max(0, raw_start - context_chars)
            context_end = min(len(raw_text), raw_end + context_chars)
            hits.append(
                RetrievalHit(
                    doc_id=row["doc_id"],
                    title=row["title"],
                    author=row["author"],
                    source_uri=row["source_uri"],
                    corpus_release=row["corpus_release"],
                    raw_start=raw_start,
                    raw_end=raw_end,
                    token_index=int(row["token_index"]),
                    raw_form=raw_text[raw_start:raw_end],
                    normalized_form=row["normalized_form"],
                    context_start=context_start,
                    context_end=context_end,
                    prefix=raw_text[context_start:raw_start],
                    match=raw_text[raw_start:raw_end],
                    suffix=raw_text[raw_end:context_end],
                    provenance=Provenance(
                        author_death_year_ah=row["author_death_year_ah"],
                        composition_date_ah=row["composition_date_ah"],
                        metadata_source_uri=row["metadata_source_uri"],
                        author_date_source_uri=row["author_date_source_uri"],
                        composition_date_source_uri=row["composition_date_source_uri"],
                        edition_citation=row["edition_citation"],
                        edition_date=row["edition_date"],
                        edition_source_uri=row["edition_source_uri"],
                        witness_description=row["witness_description"],
                        witness_date=row["witness_date"],
                        witness_source_uri=row["witness_source_uri"],
                        quality_status=row["quality_status"],
                        quality_notes=row["quality_notes"],
                    ),
                    work_id=row["work_id"],
                    language=row["language"],
                    source_format=row["source_format"],
                    parser_version=row["parser_version"],
                    source_sha256=row["source_sha256"],
                    raw_text_sha256=row["raw_text_sha256"],
                    license_id=row["license_id"],
                    license_uri=row["license_uri"],
                    selection_reason=row["selection_reason"],
                )
            )
        return hits, total, total > max_hits


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        doc_id=row["doc_id"],
        title=row["title"],
        author=row["author"],
        raw_text=row["raw_text"],
        source_uri=row["source_uri"],
        corpus_release=row["corpus_release"],
        provenance=Provenance(
            author_death_year_ah=row["author_death_year_ah"],
            composition_date_ah=row["composition_date_ah"],
            metadata_source_uri=row["metadata_source_uri"],
            author_date_source_uri=row["author_date_source_uri"],
            composition_date_source_uri=row["composition_date_source_uri"],
            edition_citation=row["edition_citation"],
            edition_date=row["edition_date"],
            edition_source_uri=row["edition_source_uri"],
            witness_description=row["witness_description"],
            witness_date=row["witness_date"],
            witness_source_uri=row["witness_source_uri"],
            quality_status=row["quality_status"],
            quality_notes=row["quality_notes"],
        ),
        work_id=row["work_id"],
        language=row["language"],
        source_format=row["source_format"],
        parser_version=row["parser_version"],
        source_sha256=row["source_sha256"],
        raw_text_sha256=row["raw_text_sha256"],
        license_id=row["license_id"],
        license_uri=row["license_uri"],
        selection_reason=row["selection_reason"],
    )
