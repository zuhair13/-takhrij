from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index
from takhrij.ingestion import IngestionError, ingest_source, strip_openiti_markup
from takhrij.manifest import load_manifest, resolve_document_path
from takhrij.models import Variant
from takhrij.normalization import is_arabic_letter, is_arabic_mark

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "corpus_manifest.fixture.json"


def _arabic_codepoints(text: str) -> str:
    return "".join(char for char in text if is_arabic_letter(char) or is_arabic_mark(char))


class IngestionTests(unittest.TestCase):
    def test_plain_text_adapter_is_byte_faithful(self):
        manifest = load_manifest(MANIFEST_PATH)
        document = manifest.documents[0]
        path = resolve_document_path(manifest, MANIFEST_PATH, document)
        ingested = ingest_source(path, document.source_format, document.source_sha256)
        self.assertEqual(ingested.raw_text, path.read_bytes().decode("utf-8"))
        self.assertEqual(ingested.parser_version, "plain_text:v1")

    def test_openiti_adapter_strips_controls_but_preserves_arabic(self):
        manifest = load_manifest(MANIFEST_PATH)
        document = next(item for item in manifest.documents if item.doc_id == "fixture-markup")
        path = resolve_document_path(manifest, MANIFEST_PATH, document)
        source = path.read_bytes().decode("utf-8")
        content = source.split("#META#Header#End#", 1)[1]
        ingested = ingest_source(path, document.source_format, document.source_sha256)

        self.assertNotIn("######OpenITI#", ingested.raw_text)
        self.assertNotIn("#META#", ingested.raw_text)
        self.assertNotIn("PageV01P001", ingested.raw_text)
        self.assertNotIn("%~%", ingested.raw_text)
        self.assertNotIn("msA1", ingested.raw_text)
        self.assertIn("بالتَّخْرِيجِ", ingested.raw_text)
        self.assertEqual(_arabic_codepoints(ingested.raw_text), _arabic_codepoints(content))

    def test_openiti_adapter_fails_closed_on_missing_header_end(self):
        with self.assertRaisesRegex(IngestionError, "Header#End"):
            strip_openiti_markup("######OpenITI#\n#META# no terminator\n# نص")

    def test_source_hash_mismatch_is_rejected(self):
        manifest = load_manifest(MANIFEST_PATH)
        document = manifest.documents[0]
        path = resolve_document_path(manifest, MANIFEST_PATH, document)
        with self.assertRaisesRegex(IngestionError, "SHA-256 mismatch"):
            ingest_source(path, document.source_format, "0" * 64)

    def test_invalid_encoding_format_and_empty_input_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_utf8 = root / "invalid.txt"
            invalid_utf8.write_bytes(b"\xff")
            with self.assertRaisesRegex(IngestionError, "valid UTF-8"):
                ingest_source(
                    invalid_utf8,
                    "plain_text",
                    hashlib.sha256(invalid_utf8.read_bytes()).hexdigest(),
                )

            empty = root / "empty.txt"
            empty.write_text(" \n", encoding="utf-8")
            empty_hash = hashlib.sha256(empty.read_bytes()).hexdigest()
            with self.assertRaisesRegex(IngestionError, "empty document"):
                ingest_source(empty, "plain_text", empty_hash)
            with self.assertRaisesRegex(IngestionError, "unsupported source format"):
                ingest_source(empty, "unsupported", empty_hash)

    def test_openiti_adapter_requires_magic_header(self):
        with self.assertRaisesRegex(IngestionError, "magic header"):
            strip_openiti_markup("#META#Header#End#\n# synthetic")

    def test_markup_ingestion_offsets_recover_exact_stored_arabic(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fixture.db"
            build_index(MANIFEST_PATH, database)
            index = CorpusIndex(database)
            hits, total, truncated = index.search(
                [Variant("بالتخريج", "input")],
                book_ids=("fixture-markup",),
                max_hits=20,
            )
            self.assertEqual(total, 1)
            self.assertFalse(truncated)
            hit = hits[0]
            document = index.get_document(hit.doc_id)
            assert document is not None
            self.assertEqual(hit.raw_form, "بالتَّخْرِيجِ")
            self.assertEqual(document.raw_text[hit.raw_start : hit.raw_end], hit.raw_form)
            self.assertTrue(
                index.verify_raw_span(hit.doc_id, hit.raw_start, hit.raw_end, hit.raw_form)
            )


if __name__ == "__main__":
    unittest.main()
