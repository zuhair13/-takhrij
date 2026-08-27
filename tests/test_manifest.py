from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from takhrij.index_builder import _enforce_approval_boundary, build_index
from takhrij.manifest import (
    LOCAL_ONLY_STATUS,
    ManifestError,
    load_manifest,
    resolve_document_path,
    resolve_source_root,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MANIFEST = ROOT / "config" / "corpus_manifest.fixture.json"
APPROVED_EXAMPLE = ROOT / "config" / "corpus_manifest.approved.example.json"
SCHEMA_PATH = ROOT / "config" / "corpus_manifest.schema.json"
LOCAL_OPENITI = ROOT / "config" / "corpus_manifest.local-openiti-2025.1.9.json"
DIZA_CLAIM = ROOT / "config" / "claims" / "TAKHRIJ-DIZA-01.json"


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

    def test_written_permission_status_rejects_placeholder_reference(self):
        data = json.loads(APPROVED_EXAMPLE.read_text(encoding="utf-8"))
        data["approval"]["status"] = "written_permission_granted"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "real approval.reference"):
                load_manifest(path)

    def test_local_only_status_rejects_placeholder_reference(self):
        data = json.loads(APPROVED_EXAMPLE.read_text(encoding="utf-8"))
        data["approval"]["status"] = LOCAL_ONLY_STATUS
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "real approval.reference"):
                load_manifest(path)

    def test_local_openiti_manifest_is_pinned_and_straddles_cutoff(self):
        manifest = load_manifest(LOCAL_OPENITI)
        self.assertEqual(manifest.approval.status, LOCAL_ONLY_STATUS)
        self.assertIn("cfc4157a3cf2054c0888f133970a4eaa3e22e58c", manifest.release_uri)
        self.assertEqual(manifest.release_doi, "10.5281/zenodo.17767721")
        self.assertEqual(len(manifest.documents), 5)
        self.assertEqual(
            [item.provenance.author_death_year_ah for item in manifest.documents],
            [276, 414, 456, 505, 598],
        )
        ids = [item.doc_id for item in manifest.documents]
        self.assertTrue(any(".Shamela" in item for item in ids))
        self.assertTrue(any(".JK" in item for item in ids))
        self.assertTrue(any(".Shia" in item for item in ids))
        self.assertIn("0505Ghazali.Munqidh.JK009330-ara1", ids)
        self.assertFalse(any("Munqidh.Shamela" in item for item in ids))

    def test_diza_claim_contract_hash_and_corpus_binding_are_reproducible(self):
        envelope = json.loads(DIZA_CLAIM.read_text(encoding="utf-8"))
        canonical = json.dumps(
            envelope["contract"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            envelope["contract_sha256"],
        )
        manifest = load_manifest(LOCAL_OPENITI)
        self.assertEqual(envelope["contract"]["manifest_sha256"], manifest.canonical_sha256)
        self.assertEqual(
            envelope["contract"]["book_ids"],
            [document.doc_id for document in manifest.documents],
        )

    def test_local_only_build_requires_its_flag_and_external_output(self):
        manifest = load_manifest(LOCAL_OPENITI)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "local.db"
            with self.assertRaisesRegex(PermissionError, "allow-local-only-corpus"):
                _enforce_approval_boundary(manifest, LOCAL_OPENITI, output)
            self.assertEqual(
                _enforce_approval_boundary(
                    manifest,
                    LOCAL_OPENITI,
                    output,
                    allow_local_only_corpus=True,
                ),
                "local_only",
            )
        with self.assertRaisesRegex(PermissionError, "outside the repository"):
            _enforce_approval_boundary(
                manifest,
                LOCAL_OPENITI,
                ROOT / "data" / "forbidden-local.db",
                allow_local_only_corpus=True,
            )

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
