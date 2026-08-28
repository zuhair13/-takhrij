from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from takhrij.gate import IssuanceGate, IssuanceRejected
from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index
from takhrij.models import (
    AuditFinding,
    AuditReport,
    Claim,
    EvidenceRole,
    MatchClass,
    Verdict,
)
from takhrij.pipeline import apply_classifications, assemble_dossier, expand_forms, retrieve_pass
from takhrij.verdict import derive_verdict

ROOT = Path(__file__).resolve().parents[1]


class VerdictAndGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "fixture.db"
        build_index(ROOT / "config" / "corpus_manifest.fixture.json", path)
        self.index = CorpusIndex(path)
        self.claim = Claim(
            "تخريج",
            "دليل يُستند إليه",
            500,
            "FIXTURE-ONLY",
            ("fixture-early", "fixture-late"),
        )

    def tearDown(self):
        self.temp.cleanup()

    def _classified(
        self,
        form: str,
        classification: MatchClass,
        evidence_role: EvidenceRole = EvidenceRole.INDEPENDENT_AUTHORIAL_USE,
    ):
        variants = expand_forms(form, [], 64)
        hits, search_pass = retrieve_pass(
            self.index, self.claim, variants, pass_name="initial", max_hits=200
        )
        decisions = [
            {
                "hit_key": hit.key,
                "classification": classification.value,
                "evidence_role": evidence_role.value,
                "reason": "test",
                "confidence": 1,
            }
            for hit in hits
        ]
        return variants, hits, search_pass, apply_classifications(hits, decisions)

    def test_only_independent_target_use_can_break_claim(self):
        _, _, _, matches = self._classified("بالتخريج", MatchClass.TARGET_USE)
        self.assertEqual(
            derive_verdict(matches, cutoff_year_ah=500, coverage_complete=True),
            Verdict.EARLIER_MATCH_FOUND,
        )
        excluded_roles = (
            EvidenceRole.DIRECT_QUOTATION,
            EvidenceRole.ATTRIBUTED_QUOTATION,
            EvidenceRole.METALINGUISTIC_MENTION,
            EvidenceRole.FORMULAIC_ALLUSION,
        )
        for role in excluded_roles:
            with self.subTest(role=role):
                _, _, _, excluded = self._classified(
                    "بالتخريج", MatchClass.TARGET_USE, role
                )
                self.assertEqual(
                    derive_verdict(excluded, cutoff_year_ah=500, coverage_complete=True),
                    Verdict.NO_EARLIER_MATCH_IN_DECLARED_CORPUS,
                )

    def test_uncertain_evidence_role_blocks_negative_verdict(self):
        _, _, _, matches = self._classified(
            "بالتخريج",
            MatchClass.TARGET_USE,
            EvidenceRole.UNCERTAIN,
        )
        self.assertEqual(
            derive_verdict(matches, cutoff_year_ah=500, coverage_complete=True),
            Verdict.INCONCLUSIVE,
        )

    def test_homograph_cannot_break_claim_even_with_independent_role(self):
        _, _, _, matches = self._classified("بالتخريج", MatchClass.HOMOGRAPH)
        self.assertEqual(
            derive_verdict(matches, cutoff_year_ah=500, coverage_complete=True),
            Verdict.NO_EARLIER_MATCH_IN_DECLARED_CORPUS,
        )

    def test_uncertain_early_context_is_inconclusive(self):
        _, _, _, matches = self._classified("بالتخريج", MatchClass.UNCERTAIN)
        self.assertEqual(
            derive_verdict(matches, cutoff_year_ah=500, coverage_complete=True),
            Verdict.INCONCLUSIVE,
        )

    def test_gate_accepts_verified_dossier(self):
        variants, _, search_pass, matches = self._classified("بالتخريج", MatchClass.TARGET_USE)
        dossier = assemble_dossier(
            claim=self.claim,
            variants=variants,
            matches=matches,
            passes=[search_pass],
            audit=AuditReport(completed=True),
        )
        self.assertTrue(IssuanceGate(self.index).issue(dossier).gate_passed)

    def test_gate_rejects_changed_quote(self):
        variants, _, search_pass, matches = self._classified("بالتخريج", MatchClass.TARGET_USE)
        corrupted_hit = replace(matches[0].hit, raw_form="نص مختلق", match="نص مختلق")
        corrupted = [replace(matches[0], hit=corrupted_hit)]
        dossier = assemble_dossier(
            claim=self.claim,
            variants=variants,
            matches=corrupted,
            passes=[search_pass],
            audit=AuditReport(completed=True),
        )
        with self.assertRaises(IssuanceRejected) as raised:
            IssuanceGate(self.index).issue(dossier)
        self.assertTrue(
            any(error.startswith("quote_mismatch") for error in raised.exception.errors)
        )

    def test_gate_rejects_changed_context(self):
        variants, _, search_pass, matches = self._classified("بالتخريج", MatchClass.TARGET_USE)
        corrupted_hit = replace(matches[0].hit, prefix="نص مختلق")
        dossier = assemble_dossier(
            claim=self.claim,
            variants=variants,
            matches=[replace(matches[0], hit=corrupted_hit)],
            passes=[search_pass],
            audit=AuditReport(completed=True),
        )
        with self.assertRaises(IssuanceRejected) as raised:
            IssuanceGate(self.index).issue(dossier)
        self.assertTrue(
            any(error.startswith("context_mismatch") for error in raised.exception.errors)
        )

    def test_gate_requires_audited_variant_to_be_searched(self):
        variants, _, search_pass, matches = self._classified("تخريج", MatchClass.TARGET_USE)
        dossier = assemble_dossier(
            claim=self.claim,
            variants=variants,
            matches=matches,
            passes=[search_pass],
            audit=AuditReport(
                completed=True,
                findings=(AuditFinding("missing_variant", "attached clitic", "بالتخريج"),),
            ),
        )
        with self.assertRaises(IssuanceRejected) as raised:
            IssuanceGate(self.index).issue(dossier)
        self.assertIn("audit_variant_not_retrieved", raised.exception.errors)

    def test_truncated_search_issues_an_inconclusive_dossier(self):
        variants = expand_forms("هذا", [], 64)
        hits, search_pass = retrieve_pass(
            self.index, self.claim, variants, pass_name="initial", max_hits=1
        )
        matches = apply_classifications(
            hits,
            [
                {
                    "hit_key": hit.key,
                    "classification": MatchClass.HOMOGRAPH.value,
                    "evidence_role": EvidenceRole.INDEPENDENT_AUTHORIAL_USE.value,
                    "reason": "test",
                    "confidence": 1,
                }
                for hit in hits
            ],
        )
        dossier = assemble_dossier(
            claim=self.claim,
            variants=variants,
            matches=matches,
            passes=[search_pass],
            audit=AuditReport(completed=True),
        )
        self.assertEqual(dossier.verdict, Verdict.INCONCLUSIVE)
        self.assertTrue(IssuanceGate(self.index).issue(dossier).gate_passed)

    def test_blocking_audit_finding_forces_inconclusive(self):
        variants, _, search_pass, matches = self._classified("تخريج", MatchClass.HOMOGRAPH)
        dossier = assemble_dossier(
            claim=self.claim,
            variants=variants,
            matches=matches,
            passes=[search_pass],
            audit=AuditReport(
                completed=True,
                findings=(AuditFinding("thin_time_slice", "coverage is sparse"),),
            ),
        )
        self.assertFalse(dossier.coverage_complete)
        self.assertEqual(dossier.verdict, Verdict.INCONCLUSIVE)
        self.assertTrue(IssuanceGate(self.index).issue(dossier).gate_passed)

    def test_low_confidence_label_becomes_uncertain(self):
        variants = expand_forms("بالتخريج", [], 64)
        hits, _ = retrieve_pass(self.index, self.claim, variants, pass_name="initial", max_hits=200)
        matches = apply_classifications(
            hits,
            [
                {
                    "hit_key": hit.key,
                    "classification": MatchClass.TARGET_USE.value,
                    "evidence_role": EvidenceRole.INDEPENDENT_AUTHORIAL_USE.value,
                    "reason": "weak",
                    "confidence": 0.4,
                }
                for hit in hits
            ],
        )
        self.assertEqual(matches[0].classification, MatchClass.UNCERTAIN)
        self.assertEqual(matches[0].evidence_role, EvidenceRole.UNCERTAIN)
        self.assertEqual(
            derive_verdict(matches, cutoff_year_ah=500, coverage_complete=True),
            Verdict.INCONCLUSIVE,
        )

    def test_missing_evidence_role_fails_closed(self):
        variants = expand_forms("بالتخريج", [], 64)
        hits, _ = retrieve_pass(
            self.index,
            self.claim,
            variants,
            pass_name="initial",
            max_hits=200,
        )
        matches = apply_classifications(
            hits,
            [
                {
                    "hit_key": hit.key,
                    "classification": MatchClass.TARGET_USE.value,
                    "reason": "role omitted",
                    "confidence": 1.0,
                }
                for hit in hits
            ],
        )
        self.assertEqual(matches[0].classification, MatchClass.UNCERTAIN)
        self.assertEqual(matches[0].evidence_role, EvidenceRole.UNCERTAIN)
        self.assertEqual(
            derive_verdict(matches, cutoff_year_ah=500, coverage_complete=True),
            Verdict.INCONCLUSIVE,
        )


if __name__ == "__main__":
    unittest.main()
