"""Mechanical dossier issuance gate; it verifies facts, never interpretations."""

from __future__ import annotations

import hashlib

from takhrij.index import CorpusIndex
from takhrij.models import Dossier, Verdict
from takhrij.verdict import derive_verdict, is_qualifying_attestation


class IssuanceRejected(RuntimeError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class IssuanceGate:
    def __init__(self, index: CorpusIndex):
        self.index = index

    def inspect(self, dossier: Dossier) -> list[str]:
        errors: list[str] = []
        if not dossier.audit.completed:
            errors.append("devils_advocate_not_completed")
        if not self.index.declared_books_exist(dossier.claim.book_ids):
            errors.append("declared_book_missing")
        metadata = self.index.metadata()
        if metadata.get("release") != dossier.claim.corpus_release:
            errors.append("corpus_release_mismatch")
        if dossier.claim_statement != dossier.claim.proposition():
            errors.append("claim_statement_not_deterministic")
        if dossier.boundary_statement != dossier.claim.boundary_statement(dossier.verdict):
            errors.append("boundary_statement_not_deterministic")

        searched = {
            variant.surface_form
            for search_pass in dossier.search_passes
            for variant in search_pass.variants
        }
        declared = {variant.surface_form for variant in dossier.variants}
        if searched != declared:
            errors.append("variant_trace_incomplete")
        if dossier.coverage_complete and any(
            search_pass.truncated for search_pass in dossier.search_passes
        ):
            errors.append("truncated_trace_marked_complete")
        if dossier.coverage_complete and any(
            finding.kind in {"thin_time_slice", "metadata_conflict"}
            for finding in dossier.audit.findings
        ):
            errors.append("blocking_audit_marked_complete")
        pending = set(dossier.audit.proposed_variants) - declared
        if pending:
            errors.append("audit_variant_not_retrieved")

        for item in dossier.matches:
            hit = item.hit
            document = self.index.get_document(hit.doc_id)
            if document is None:
                errors.append(f"missing_source:{hit.key}")
                continue
            if hashlib.sha256(document.raw_text.encode("utf-8")).hexdigest() != (
                document.raw_text_sha256
            ):
                errors.append(f"document_hash_mismatch:{hit.key}")
            if not self.index.verify_raw_span(hit.doc_id, hit.raw_start, hit.raw_end, hit.raw_form):
                errors.append(f"quote_mismatch:{hit.key}")
            if hit.match != hit.raw_form:
                errors.append(f"highlight_mismatch:{hit.key}")
            expected_context = document.raw_text[hit.context_start : hit.context_end]
            if hit.prefix + hit.match + hit.suffix != expected_context:
                errors.append(f"context_mismatch:{hit.key}")
            if hit.context_start + len(hit.prefix) != hit.raw_start:
                errors.append(f"prefix_offset_mismatch:{hit.key}")
            if hit.raw_end + len(hit.suffix) != hit.context_end:
                errors.append(f"suffix_offset_mismatch:{hit.key}")
            if (
                hit.source_uri != document.source_uri
                or hit.corpus_release != document.corpus_release
                or hit.work_id != document.work_id
                or hit.language != document.language
                or hit.source_format != document.source_format
                or hit.parser_version != document.parser_version
                or hit.source_sha256 != document.source_sha256
                or hit.raw_text_sha256 != document.raw_text_sha256
                or hit.license_id != document.license_id
                or hit.license_uri != document.license_uri
                or hit.selection_reason != document.selection_reason
            ):
                errors.append(f"source_metadata_mismatch:{hit.key}")
            if hit.provenance != document.provenance:
                errors.append(f"date_metadata_mismatch:{hit.key}")

        expected = derive_verdict(
            dossier.matches,
            cutoff_year_ah=dossier.claim.cutoff_year_ah,
            coverage_complete=dossier.coverage_complete,
        )
        if expected is not dossier.verdict:
            errors.append("verdict_not_derived_from_evidence")
        if dossier.verdict is Verdict.EARLIER_MATCH_FOUND:
            has_evidence = any(
                is_qualifying_attestation(item)
                and item.hit.provenance.comparison_year_ah is not None
                and item.hit.provenance.comparison_year_ah < dossier.claim.cutoff_year_ah
                for item in dossier.matches
            )
            if not has_evidence:
                errors.append("positive_verdict_without_attestation")
        return errors

    def issue(self, dossier: Dossier) -> Dossier:
        errors = self.inspect(dossier)
        dossier.gate_errors = errors
        dossier.gate_passed = not errors
        if errors:
            raise IssuanceRejected(errors)
        return dossier
