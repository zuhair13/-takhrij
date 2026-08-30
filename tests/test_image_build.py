from __future__ import annotations

import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from scripts.build_approved_image import _approved_manifest, build_approved_image
from takhrij.image_gate import verify_image_database
from takhrij.manifest import load_manifest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MANIFEST = ROOT / "config" / "corpus_manifest.fixture.json"
APPROVED_EXAMPLE = ROOT / "config" / "corpus_manifest.approved.example.json"


class ApprovedImageBuildTests(unittest.TestCase):
    def test_explicit_opt_in_and_approved_manifest_are_required(self):
        with self.assertRaisesRegex(PermissionError, "explicit"):
            _approved_manifest(APPROVED_EXAMPLE, allow_approved_corpus_image=False)
        with self.assertRaisesRegex(PermissionError, "approved_corpus"):
            _approved_manifest(FIXTURE_MANIFEST, allow_approved_corpus_image=True)
        with self.assertRaisesRegex(PermissionError, "written_permission_granted"):
            _approved_manifest(APPROVED_EXAMPLE, allow_approved_corpus_image=True)

    def test_approved_build_uses_isolated_context_and_bakes_database(self):
        manifest = load_manifest(APPROVED_EXAMPLE)
        manifest = replace(
            manifest,
            approval=replace(
                manifest.approval,
                status="written_permission_granted",
                reference="fixture://written-permission-test",
            ),
        )
        database_bytes = b"SQLite format 3\x00synthetic approved-image workflow test"

        def fake_build_index(_manifest_path, output_path, *, allow_approved_corpus):
            self.assertTrue(allow_approved_corpus)
            output_path.write_bytes(database_bytes)
            return {
                "database_sha256": "0" * 64,
                "build_seconds": 0.001,
                "document_count": "1",
                "token_count": "1",
            }

        def fake_docker(command, *, cwd, check):
            self.assertEqual(
                command,
                [
                    "docker",
                    "build",
                    "--build-arg",
                    "ALLOW_APPROVED_CORPUS_IMAGE=written_permission_granted",
                    "--tag",
                    "example:test",
                    ".",
                ],
            )
            self.assertTrue(check)
            self.assertNotIn(ROOT.resolve(), (cwd, *cwd.parents))
            self.assertEqual((cwd / "data" / "takhrij.db").read_bytes(), database_bytes)
            self.assertFalse((cwd / "tests").exists())
            self.assertFalse((cwd / "config").exists())
            return subprocess.CompletedProcess(command, 0)

        with (
            patch("scripts.build_approved_image.load_manifest", return_value=manifest),
            patch("scripts.build_approved_image.build_index", side_effect=fake_build_index),
            patch("scripts.build_approved_image.subprocess.run", side_effect=fake_docker),
        ):
            result = build_approved_image(
                APPROVED_EXAMPLE,
                "example:test",
                allow_approved_corpus_image=True,
            )
        self.assertEqual(result["delivery"], "baked_read_only_database")
        self.assertEqual(result["approval_status"], "written_permission_granted")

    def test_docker_image_gate_allows_fixture_and_requires_approved_opt_in(self):
        cloudbuild = (ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")
        self.assertIn("APP_ENV=${_APP_ENV}", cloudbuild)
        self.assertIn("LOCAL_INLINE_WORKER=${_LOCAL_INLINE_WORKER}", cloudbuild)
        self.assertIn("_APP_ENV: development", cloudbuild)
        self.assertIn('_LOCAL_INLINE_WORKER: "true"', cloudbuild)
        self.assertNotIn("APP_ENV=production", cloudbuild)

        fixture_database = ROOT / "data" / "takhrij.db"
        fixture_metadata = verify_image_database(fixture_database, "fixture_only")
        self.assertEqual(fixture_metadata["content_kind"], "synthetic_fixture")

        with tempfile.TemporaryDirectory() as directory:
            approved_database = Path(directory) / "approved-synthetic.db"
            approved_database.write_bytes(fixture_database.read_bytes())
            with closing(sqlite3.connect(approved_database)) as connection, connection:
                connection.executemany(
                    "UPDATE corpus_metadata SET value = ? WHERE key = ?",
                    (
                        ("approved_corpus", "content_kind"),
                        ("written_permission_granted", "approval_status"),
                        ("fixture://written-permission-test", "approval_reference"),
                        ("distribution_approved", "delivery_scope"),
                    ),
                )
            with self.assertRaisesRegex(PermissionError, "explicit Docker build opt-in"):
                verify_image_database(approved_database, "fixture_only")
            approved_metadata = verify_image_database(
                approved_database, "written_permission_granted"
            )
            self.assertEqual(approved_metadata["content_kind"], "approved_corpus")

            with closing(sqlite3.connect(approved_database)) as connection, connection:
                connection.executemany(
                    "UPDATE corpus_metadata SET value = ? WHERE key = ?",
                    (
                        ("local_only_licence_reviewed", "approval_status"),
                        ("local_only", "delivery_scope"),
                    ),
                )
            with self.assertRaisesRegex(PermissionError, "approval_status"):
                verify_image_database(approved_database, "written_permission_granted")


if __name__ == "__main__":
    unittest.main()
