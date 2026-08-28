from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.serve_redacted_result import create_result_app, load_redacted_result


def _safe_result() -> dict:
    return {
        "run_policy": {
            "delivery_scope": "local_only",
            "corpus_text": "redacted",
            "runtime": "Google ADK + Google Gen AI on Google Cloud",
            "claim_id": "TAKHRIJ-DIZA-01",
            "contract_version": "3",
            "contract_sha256": "a" * 64,
        },
        "corpus": {
            "release": "OpenITI-test",
            "manifest_sha256": "b" * 64,
            "document_count": 1,
            "token_count": 10,
        },
        "dossier": {
            "claim": {"cutoff_year_ah": 500},
            "claim_statement": "Frozen claim",
            "boundary_statement": "Corpus-bounded only",
            "provisional_verdict": "NO_EARLIER_MATCH_IN_DECLARED_CORPUS",
            "verdict": "NO_EARLIER_MATCH_IN_DECLARED_CORPUS",
            "variants": [{"surface_form": "ضيزى", "source": "submitted"}],
            "matches": [
                {
                    "classification": "target_use",
                    "evidence_role": "direct_quotation",
                    "hit": {
                        "doc_id": "book-a",
                        "normalized_form": "ضيزى",
                        "raw_start": 10,
                        "raw_end": 14,
                        "source_sha256": "c" * 64,
                        "raw_text_sha256": "d" * 64,
                        "title": "Book A",
                        "author": "Author A",
                        "source_uri": "https://example.invalid/book-a",
                        "provenance": {
                            "author_death_year_ah": 400,
                            "composition_date_ah": None,
                            "edition_date": None,
                            "witness_date": None,
                        },
                    },
                }
            ],
            "audit": {"findings": []},
            "limitations": ["Corpus-bounded only"],
            "gate_passed": True,
            "gate_errors": [],
            "display_policy": {
                "corpus_text": "redacted",
                "assessment_rationales": "redacted",
                "delivery_scope": "local_only",
            },
        },
    }


class ResultViewerTests(unittest.TestCase):
    def _write(self, directory: str, result: dict) -> Path:
        path = Path(directory) / "result.json"
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return path

    def test_viewer_renders_only_gate_issued_redacted_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _safe_result())
            app = create_result_app(path)
            app.testing = True
            response = app.test_client().get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertIn("LIVE GOOGLE CLOUD RUN", page)
        self.assertIn("NO_EARLIER_MATCH_IN_DECLARED_CORPUS", page)
        self.assertIn("book-a", page)
        self.assertNotIn("licensed secret", page)

    def test_viewer_rejects_failed_gate_or_exposed_text(self):
        cases = []
        failed = deepcopy(_safe_result())
        failed["dossier"]["gate_passed"] = False
        cases.append((failed, "Gate-issued"))
        exposed = deepcopy(_safe_result())
        exposed["dossier"]["matches"][0]["hit"]["prefix"] = "licensed secret"
        cases.append((exposed, "unredacted fields"))
        with tempfile.TemporaryDirectory() as directory:
            for index, (result, message) in enumerate(cases):
                with self.subTest(index=index):
                    path = self._write(directory, result)
                    with self.assertRaisesRegex(ValueError, message):
                        load_redacted_result(path)


if __name__ == "__main__":
    unittest.main()
