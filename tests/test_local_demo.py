from __future__ import annotations

import io
import logging
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.run_local_corpus_demo import run_local_demo


class LocalCorpusDemoTests(unittest.TestCase):
    def test_acknowledgement_is_required_before_manifest_access(self):
        with (
            patch("scripts.run_local_corpus_demo.load_manifest") as load_manifest,
            self.assertRaisesRegex(PermissionError, "acknowledgement"),
        ):
            run_local_demo(
                Path("manifest.json"),
                form="ضيزى",
                target_sense="صفة القسمة الجائرة",
                cutoff_year_ah=500,
                project_id="project",
            )
        load_manifest.assert_not_called()

    def test_live_run_forces_vertex_and_returns_post_gate_redaction(self):
        manifest = SimpleNamespace(
            approval=SimpleNamespace(status="local_only_licence_reviewed"),
            release="OpenITI-test",
        )

        def fake_build(_manifest, output, *, allow_local_only_corpus):
            self.assertTrue(allow_local_only_corpus)
            output.write_bytes(b"fixture")
            return {
                "delivery_scope": "local_only",
                "release": "OpenITI-test",
                "release_doi": "10.0000/test",
                "manifest_sha256": "a" * 64,
                "database_sha256": "b" * 64,
                "document_count": "2",
                "token_count": "10",
            }

        class FakeIndex:
            def __init__(self, _path):
                pass

            def document_ids(self):
                return ("book-a", "book-b")

        def fake_run(_index, settings, claim, progress):
            self.assertEqual(os.environ["GOOGLE_CLOUD_PROJECT"], "vertex-project")
            self.assertEqual(os.environ["GOOGLE_CLOUD_LOCATION"], "global")
            self.assertEqual(os.environ["GOOGLE_GENAI_USE_ENTERPRISE"], "true")
            self.assertTrue(settings.redact_corpus_text)
            self.assertEqual(claim["book_ids"], ["book-a", "book-b"])
            progress("provisional", {"label": "PROVISIONAL_TEST", "matches": 2})
            logging.getLogger("sensitive").error("licensed context")
            print("licensed context", file=sys.stderr)
            return {
                "gate_passed": True,
                "matches": [
                    {
                        "classification": "target_use",
                        "evidence_role": "direct_quotation",
                        "reason": "licensed rationale",
                        "hit": {
                            "raw_form": "ضيزى",
                            "prefix": "قبل",
                            "match": "ضيزى",
                            "suffix": "بعد",
                            "doc_id": "book-a",
                        },
                    }
                ],
                "audit": {"findings": [{"rationale": "licensed audit"}]},
                "limitations": [],
            }

        old_project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        stderr = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("scripts.run_local_corpus_demo.load_manifest", return_value=manifest),
            patch("scripts.run_local_corpus_demo.build_index", side_effect=fake_build),
            patch("scripts.run_local_corpus_demo.CorpusIndex", FakeIndex),
            patch("scripts.run_local_corpus_demo.run_claim_sync", side_effect=fake_run),
            redirect_stderr(stderr),
        ):
            result = run_local_demo(
                Path(directory) / "manifest.json",
                form="ضيزى",
                target_sense="صفة القسمة الجائرة",
                cutoff_year_ah=500,
                project_id="vertex-project",
                acknowledge_local_only_licence=True,
            )
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(os.environ.get("GOOGLE_CLOUD_PROJECT"), old_project)
        self.assertEqual(result["run_policy"]["delivery_scope"], "local_only")
        match = result["dossier"]["matches"][0]
        self.assertNotIn("reason", match)
        self.assertNotIn("raw_form", match["hit"])
        self.assertEqual(result["progress"][0]["matches"], 2)


if __name__ == "__main__":
    unittest.main()
