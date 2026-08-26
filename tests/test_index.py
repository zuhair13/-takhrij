from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index
from takhrij.models import Variant

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "corpus_manifest.fixture.json"


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "fixture.db"
        build_index(MANIFEST, path)
        self.index = CorpusIndex(path)

    def tearDown(self):
        self.temp.cleanup()

    def test_release_and_books_are_pinned(self):
        metadata = self.index.metadata()
        self.assertEqual(metadata["release"], "FIXTURE-ONLY")
        self.assertEqual(metadata["content_kind"], "synthetic_fixture")
        self.assertEqual(metadata["document_count"], "3")
        self.assertEqual(metadata["offset_unit"], "unicode_code_points")
        self.assertTrue(self.index.declared_books_exist(("fixture-early", "fixture-late")))
        self.assertFalse(self.index.declared_books_exist(("missing",)))

    def test_document_provenance_and_hashes_are_exact(self):
        document = self.index.get_document("fixture-early")
        assert document is not None
        self.assertEqual(document.work_id, "fixture-early")
        self.assertEqual(document.source_format, "plain_text")
        self.assertEqual(document.parser_version, "plain_text:v1")
        self.assertEqual(document.license_id, "CC0-1.0")
        self.assertEqual(document.provenance.author_death_year_ah, 370)
        self.assertEqual(document.provenance.composition_date_ah, 350)
        self.assertEqual(
            document.provenance.author_date_source_uri,
            "fixture://early/metadata#author-death",
        )
        self.assertEqual(len(document.source_sha256), 64)
        self.assertEqual(len(document.raw_text_sha256), 64)

    def test_database_build_is_byte_reproducible(self):
        first = Path(self.temp.name) / "first.db"
        second = Path(self.temp.name) / "second.db"
        first_result = build_index(MANIFEST, first)
        second_result = build_index(MANIFEST, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_result["database_sha256"], second_result["database_sha256"])
        self.assertEqual(first_result["corpus_sha256"], second_result["corpus_sha256"])

    def test_tracked_fixture_database_matches_a_fresh_build(self):
        rebuilt = Path(self.temp.name) / "tracked-comparison.db"
        build_index(MANIFEST, rebuilt)
        self.assertEqual((ROOT / "data" / "takhrij.db").read_bytes(), rebuilt.read_bytes())

    def test_exact_search_does_not_silently_strip_clitics(self):
        hits, total, truncated = self.index.search(
            [Variant("تخريج", "input")],
            book_ids=("fixture-early", "fixture-late"),
            max_hits=20,
        )
        self.assertEqual(total, 1)
        self.assertEqual(hits[0].doc_id, "fixture-late")
        self.assertFalse(truncated)

    def test_offsets_recover_raw_diacritized_form(self):
        hits, total, _ = self.index.search(
            [Variant("بالتخريج", "audit")],
            book_ids=("fixture-early", "fixture-late"),
            max_hits=20,
        )
        self.assertEqual(total, 1)
        hit = hits[0]
        self.assertEqual(hit.raw_form, "بالتَّخْرِيجِ")
        self.assertTrue(
            self.index.verify_raw_span(hit.doc_id, hit.raw_start, hit.raw_end, hit.raw_form)
        )

    def test_truncation_is_explicit(self):
        hits, total, truncated = self.index.search(
            [Variant("هذا", "input")],
            book_ids=("fixture-early", "fixture-late"),
            max_hits=1,
        )
        self.assertEqual(len(hits), 1)
        self.assertGreater(total, len(hits))
        self.assertTrue(truncated)

    def test_manifest_calendar_must_be_explicit(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["documents"][0].pop("calendar")
        path = Path(self.temp.name) / "missing-calendar.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            build_index(path, Path(self.temp.name) / "invalid.db")


if __name__ == "__main__":
    unittest.main()
