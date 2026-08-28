#!/usr/bin/env python3
"""Run one live, redacted Vertex/ADK claim against a local-only corpus."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

from takhrij.agent import run_claim_sync
from takhrij.config import Settings
from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index
from takhrij.manifest import LOCAL_ONLY_STATUS, load_manifest
from takhrij.serde import redact_dossier_for_display


def _set_vertex_environment(project_id: str, location: str) -> dict[str, str | None]:
    updates = {
        "GOOGLE_CLOUD_PROJECT": project_id,
        "GOOGLE_CLOUD_LOCATION": location,
        "GOOGLE_GENAI_USE_ENTERPRISE": "true",
    }
    previous = {name: os.environ.get(name) for name in updates}
    os.environ.update(updates)
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _load_claim_contract(path: Path, manifest: Any) -> tuple[dict[str, Any], dict[str, str]]:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    contract = envelope["contract"]
    canonical = json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if digest != envelope.get("contract_sha256"):
        raise ValueError("claim contract SHA-256 mismatch")
    if contract.get("manifest_sha256") != manifest.canonical_sha256:
        raise ValueError("claim contract manifest SHA-256 mismatch")
    if contract.get("corpus_release") != manifest.release:
        raise ValueError("claim contract release mismatch")
    manifest_books = [document.doc_id for document in manifest.documents]
    if contract.get("book_ids") != manifest_books:
        raise ValueError("claim contract book list mismatch")
    return contract, {
        "claim_id": str(envelope["claim_id"]),
        "contract_version": str(envelope["contract_version"]),
        "contract_sha256": digest,
    }


def run_local_demo(
    manifest_path: Path,
    *,
    form: str | None = None,
    target_sense: str | None = None,
    cutoff_year_ah: int | None = None,
    claim_contract_path: Path | None = None,
    project_id: str,
    location: str = "global",
    acknowledge_local_only_licence: bool = False,
) -> dict[str, Any]:
    """Build outside the repo, run once, and return only a redacted issued dossier."""
    if not acknowledge_local_only_licence:
        raise PermissionError("local corpus run requires the explicit licence acknowledgement")
    if not project_id.strip():
        raise ValueError("GOOGLE_CLOUD_PROJECT or --project-id is required")
    manifest = load_manifest(manifest_path)
    if manifest.approval.status != LOCAL_ONLY_STATUS:
        raise PermissionError(
            f"local demo requires approval.status={LOCAL_ONLY_STATUS}"
        )
    claim_identity: dict[str, str] = {}
    if claim_contract_path is not None:
        if form is not None or target_sense is not None or cutoff_year_ah is not None:
            raise ValueError("claim contract may not be combined with inline claim fields")
        contract, claim_identity = _load_claim_contract(claim_contract_path, manifest)
        form = str(contract["form"])
        target_sense = str(contract["target_sense"])
        cutoff_year_ah = int(contract["cutoff_year_ah"])
    if form is None or target_sense is None or cutoff_year_ah is None:
        raise ValueError("provide --claim-contract or all three inline claim fields")

    progress_events: list[dict[str, Any]] = []

    def progress(stage: str, details: dict[str, Any]) -> None:
        progress_events.append(
            {
                "stage": stage,
                "label": details.get("label", stage),
                "matches": details.get("matches"),
                "findings": details.get("findings"),
            }
        )

    with tempfile.TemporaryDirectory(prefix="takhrij-local-corpus-") as directory:
        database_path = Path(directory) / "takhrij-local.db"
        build = build_index(
            manifest_path,
            database_path,
            allow_local_only_corpus=True,
        )
        index = CorpusIndex(database_path)
        book_ids = index.document_ids()
        settings = Settings(
            app_env="development",
            project_id=project_id,
            location=location,
            corpus_db_path=database_path,
            corpus_release=manifest.release,
            corpus_book_ids=book_ids,
            redact_corpus_text=True,
        )
        settings.validate()
        claim = {
            "form": form,
            "target_sense": target_sense,
            "cutoff_year_ah": cutoff_year_ah,
            "corpus_release": manifest.release,
            "book_ids": list(book_ids),
        }
        previous_environment = _set_vertex_environment(project_id, location)
        previous_logging_disable = logging.root.manager.disable
        try:
            logging.disable(logging.CRITICAL)
            with redirect_stderr(io.StringIO()):
                dossier = run_claim_sync(index, settings, claim, progress)
        finally:
            logging.disable(previous_logging_disable)
            _restore_environment(previous_environment)

        return {
            "run_policy": {
                "delivery_scope": build["delivery_scope"],
                "corpus_text": "redacted",
                "runtime": "Google ADK + Google Gen AI on Google Cloud",
                **claim_identity,
            },
            "corpus": {
                "release": build["release"],
                "release_doi": build["release_doi"],
                "manifest_sha256": build["manifest_sha256"],
                "database_sha256": build["database_sha256"],
                "document_count": build["document_count"],
                "token_count": build["token_count"],
                "book_ids": list(book_ids),
            },
            "progress": progress_events,
            "dossier": redact_dossier_for_display(dossier),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        type=Path,
        default=Path("config/corpus_manifest.local-openiti-2025.1.9.json"),
        nargs="?",
    )
    parser.add_argument("--claim-contract", type=Path)
    parser.add_argument("--form")
    parser.add_argument("--target-sense")
    parser.add_argument("--cutoff-year-ah", type=int)
    parser.add_argument("--project-id", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--location", default=os.getenv("GOOGLE_CLOUD_LOCATION", "global"))
    parser.add_argument("--acknowledge-local-only-licence", action="store_true")
    args = parser.parse_args()
    try:
        result = run_local_demo(
            args.manifest,
            form=args.form,
            target_sense=args.target_sense,
            cutoff_year_ah=args.cutoff_year_ah,
            claim_contract_path=args.claim_contract,
            project_id=args.project_id,
            location=args.location,
            acknowledge_local_only_licence=args.acknowledge_local_only_licence,
        )
    except Exception as exc:
        print(
            json.dumps({"error": type(exc).__name__}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
