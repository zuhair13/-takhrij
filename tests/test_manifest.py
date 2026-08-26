from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from takhrij.index_builder import _enforce_approval_boundary, build_index
from takhrij.manifest import (
    ManifestError,
    load_manifest,
    resolve_document_path,
    resolve_source_root,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MANIFEST = ROOT / "config" / "corpus_manifest.fixture.json"
APPROVED_EXAMPLE = ROOT / "config" / "corpus_manifest.approved.example.json"
SCHEMA_PATH = ROOT / "config" / "corpus_manifest.schema.json"


class ManifestTests(unittest.TestCase):
    def test_fixture_manifest_has_complete_provenance(self):
        manifest = load_manifest(FIXTURE_MANIFEST)
        self.assertEqual(manifest.content_kind, "synthetic_fixture")
        self.assertEqual(manifest.release, "FIXTURE-ONLY")
        self.assertEqual(manifest.approval.status, "not_required")
        self.assertEqual(len(manifest.documents), 3)
        for document in manifest.documents:
            self.assertEqual(document.language, "ara")
            self.assertEqual(document.calendar, "AH")
            self.assertTrue(document.provenance.metadata_source_uri)
            self.assertTrue(document.provenance.quality_notes)
            self.assertTrue(resolve_document_path(manifest, FIXTURE_MANIFEST, document).is_file())

    def test_manifest_digest_is_independent_of_json_formatting(self):
        original = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            rewritten = Path(directory) / "manifest.json"
            rewritten.write_text(
                json.dumps(original, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            self.assertEqual(
                load_manifest(FIXTURE_MANIFEST).canonical_sha256,
                load_manifest(rewritten).canonical_sha256,
            )

    def test_date_requires_an_explicit_metadata_source(self):
        data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        data["documents"][0]["provenance"]["author_date_source_uri"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "required with an author date"):
                load_manifest(path)

    def test_unknown_manifest_fields_are_rejected(self):
        data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        data["documents"][0]["unreviewed_guess"] = "must not be silently accepted"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "unknown fields"):
                load_manifest(path)

    def test_invalid_manifest_contracts_fail_closed(self):
        cases = (
            ("schema_version", 2, "schema_version"),
            ("content_kind", "unknown", "content_kind"),
            ("documents", [], "non-empty list"),
            ("release", "NOT-A-FIXTURE", "must use release"),
            ("source_root_env", "CORPUS_ROOT", "may not set source_root_env"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (field, value, message) in enumerate(cases):
                with self.subTest(field=field):
                    data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
                    data[field] = value
                    path = Path(directory) / f"invalid-{index}.json"
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(ManifestError, message):
                        load_manifest(path)

    def test_invalid_document_contracts_fail_closed(self):
        cases = (
            ("source_sha256", "bad", "64 lowercase"),
            ("source_format", "guess", "source_format"),
            ("calendar", "CE", "explicitly AH"),
            ("language", "eng", "must be ara"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (field, value, message) in enumerate(cases):
                with self.subTest(field=field):
                    data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
                    data["documents"][0][field] = value
                    path = Path(directory) / f"invalid-document-{index}.json"
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(ManifestError, message):
                        load_manifest(path)

    def test_approved_source_root_is_external_and_paths_cannot_escape(self):
        manifest = load_manifest(APPROVED_EXAMPLE)
        assert manifest.source_root_env is not None
        with (
            patch.dict(os.environ, {manifest.source_root_env: ""}),
            self.assertRaisesRegex(ManifestError, "must name"),
        ):
            resolve_source_root(manifest, APPROVED_EXAMPLE)
        with (
            patch.dict(os.environ, {manifest.source_root_env: str(ROOT)}),
            self.assertRaisesRegex(ManifestError, "outside the repository"),
        ):
            resolve_source_root(manifest, APPROVED_EXAMPLE)
        with tempfile.TemporaryDirectory() as directory:
            external_root = Path(directory)
            with patch.dict(os.environ, {manifest.source_root_env: str(external_root)}):
                self.assertEqual(
                    resolve_source_root(manifest, APPROVED_EXAMPLE), external_root.resolve()
                )
                escaped = replace(manifest.documents[0], path="../escape")
                with self.assertRaisesRegex(ManifestError, "path escapes"):
                    resolve_document_path(manifest, APPROVED_EXAMPLE, escaped)

    def test_invalid_json_and_duplicate_document_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_bytes(b"{not-json")
            with self.assertRaisesRegex(ManifestError, "invalid UTF-8 JSON"):
                load_manifest(invalid)

            data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
            data["documents"].append(data["documents"][0])
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "unique doc_id"):
                load_manifest(duplicate)

    def test_edition_metadata_requires_a_source(self):
        data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        data["documents"][0]["provenance"]["edition_source_uri"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "required with edition metadata"):
                load_manifest(path)

    def test_witness_metadata_requires_a_source(self):
        data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        data["documents"][0]["provenance"]["witness_description"] = "synthetic witness"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "required with witness metadata"):
                load_manifest(path)

    def test_fixture_path_cannot_escape_tests_fixtures(self):
        manifest = load_manifest(FIXTURE_MANIFEST)
        escaped = replace(manifest.documents[0], path="../README.md")
        with self.assertRaisesRegex(ManifestError, "under tests/fixtures"):
            resolve_document_path(manifest, FIXTURE_MANIFEST, escaped)

    def test_approved_build_requires_flag_and_written_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "approved.db"
            with self.assertRaisesRegex(PermissionError, "explicit"):
                build_index(APPROVED_EXAMPLE, output)
            with self.assertRaisesRegex(PermissionError, "written_permission_granted"):
                build_index(APPROVED_EXAMPLE, output, allow_approved_corpus=True)

    def test_approved_database_cannot_be_written_inside_repository(self):
        manifest = load_manifest(APPROVED_EXAMPLE)
        approved = replace(
            manifest,
            approval=replace(
                manifest.approval,
                status="written_permission_granted",
                reference="fixture://written-permission-test",
            ),
        )
        with self.assertRaisesRegex(PermissionError, "outside the repository"):
            _enforce_approval_boundary(
                approved,
                APPROVED_EXAMPLE,
                ROOT / "data" / "forbidden.db",
                allow_approved_corpus=True,
            )

    def test_json_schema_required_fields_match_fixture_shape(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        fixture = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), set(fixture))
        document_required = set(schema["$defs"]["document"]["required"])
        provenance_required = set(schema["$defs"]["provenance"]["required"])
        for document in fixture["documents"]:
            self.assertEqual(document_required, set(document))
            self.assertEqual(provenance_required, set(document["provenance"]))


if __name__ == "__main__":
    unittest.main()
