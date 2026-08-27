"""Four-route Flask application for the public UI and authenticated worker."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, url_for

from takhrij.config import Settings, load_settings
from takhrij.index import CorpusIndex
from takhrij.jobs import CapacityExceeded, FirestoreJobStore, InMemoryJobStore, JobStore
from takhrij.models import Claim
from takhrij.normalization import validate_variants
from takhrij.publisher import Publisher, PubSubPublisher, RecordingPublisher
from takhrij.security import AuthenticationError, verify_pubsub_oidc
from takhrij.serde import redact_dossier_for_display
from takhrij.worker import BusyJob, ClaimWorker, TerminalJob, parse_push_envelope

LOGGER = logging.getLogger(__name__)
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _select_asset_root(source_root: Path, runtime_root: Path) -> Path:
    """Locate UI assets in both source checkouts and installed containers."""
    for candidate in (source_root, runtime_root):
        if (candidate / "templates").is_dir() and (candidate / "static").is_dir():
            return candidate
    return source_root


def _run_inline_worker(worker: ClaimWorker, job_id: str, delivery_attempt: int) -> None:
    """Run the fixture worker without leaving demo capacity stuck after failures."""
    try:
        worker.process(job_id, delivery_attempt)
    except Exception:
        LOGGER.exception("inline demo worker failed", extra={"job_id": job_id})


def _validate_claim(payload: Any, settings: Settings) -> Claim:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    allowed = {"form", "target_sense", "cutoff_year_ah"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    form = str(payload.get("form", "")).strip()
    validate_variants([form], max_variants=settings.max_variants)
    target_sense = str(payload.get("target_sense", "")).strip()
    if not 3 <= len(target_sense) <= 300:
        raise ValueError("target_sense must be 3 to 300 characters")
    try:
        cutoff = int(payload["cutoff_year_ah"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("cutoff_year_ah must be an integer") from exc
    if not 1 <= cutoff <= 1600:
        raise ValueError("cutoff_year_ah must be between 1 and 1600 AH")
    return Claim(
        form=form,
        target_sense=target_sense,
        cutoff_year_ah=cutoff,
        corpus_release=settings.corpus_release,
        book_ids=settings.corpus_book_ids,
    )


def create_app(
    *,
    settings: Settings | None = None,
    store: JobStore | None = None,
    publisher: Publisher | None = None,
    worker_runner: Callable | None = None,
    oidc_verifier: Callable[..., dict[str, object]] = verify_pubsub_oidc,
) -> Flask:
    settings = settings or load_settings()
    settings.validate()
    index = CorpusIndex(settings.corpus_db_path)
    metadata = index.metadata()
    if metadata.get("release") != settings.corpus_release:
        raise ValueError("CORPUS_RELEASE does not match the baked SQLite index")
    content_kind = metadata.get("content_kind")
    approval_status = metadata.get("approval_status")
    delivery_scope = metadata.get("delivery_scope")
    if content_kind == "synthetic_fixture":
        expected_scope = "fixture_only"
    elif content_kind == "approved_corpus" and approval_status == "local_only_licence_reviewed":
        expected_scope = "local_only"
    elif content_kind == "approved_corpus" and approval_status == "written_permission_granted":
        expected_scope = "distribution_approved"
    else:
        raise ValueError("SQLite index has an unsupported content or approval state")
    if delivery_scope != expected_scope:
        raise ValueError("SQLite index delivery_scope is inconsistent with its approval state")
    local_only_mode = approval_status == "local_only_licence_reviewed"
    if local_only_mode and not settings.redact_corpus_text:
        raise ValueError("local-only corpus mode requires REDACT_CORPUS_TEXT=true")
    if settings.production and content_kind != "approved_corpus":
        raise ValueError("production requires an approved_corpus SQLite index")
    if settings.production and approval_status != "written_permission_granted":
        raise ValueError("production corpus is missing a written-permission approval record")
    if settings.production and delivery_scope != "distribution_approved":
        raise ValueError("production corpus requires distribution_approved delivery scope")
    if not index.declared_books_exist(settings.corpus_book_ids):
        raise ValueError("CORPUS_BOOK_IDS does not match the baked SQLite index")

    if store is None:
        store = (
            FirestoreJobStore(
                project_id=settings.project_id,
                collection=settings.firestore_collection,
                lease_seconds=settings.lease_seconds,
                max_active=settings.max_active_jobs,
                max_daily=settings.max_jobs_per_day,
            )
            if settings.production
            else InMemoryJobStore(
                lease_seconds=settings.lease_seconds,
                max_active=settings.max_active_jobs,
                max_daily=settings.max_jobs_per_day,
            )
        )
    if publisher is None:
        publisher = (
            PubSubPublisher(settings.topic_path) if settings.production else RecordingPublisher()
        )
    worker_kwargs = {"store": store, "index": index, "settings": settings}
    if worker_runner is not None:
        worker_kwargs["runner"] = worker_runner
    worker = ClaimWorker(**worker_kwargs)

    asset_root = _select_asset_root(SOURCE_ROOT, Path.cwd())
    app = Flask(
        __name__,
        template_folder=str(asset_root / "templates"),
        static_folder=str(asset_root / "static"),
    )
    app.config.update(JSON_AS_ASCII=False, MAX_CONTENT_LENGTH=32 * 1024)
    app.extensions["takhrij_worker"] = worker

    @app.get("/")
    def home():
        return render_template(
            "index.html",
            release=settings.corpus_release,
            books=len(settings.corpus_book_ids),
            max_matches=settings.max_matches,
            redacted=local_only_mode,
        )

    @app.post("/claims")
    def create_claim():
        try:
            claim = _validate_claim(request.get_json(silent=False), settings)
            job = store.create(claim)
        except CapacityExceeded as exc:
            return jsonify(error="capacity_exceeded", message=str(exc)), 429
        except (ValueError, TypeError) as exc:
            return jsonify(error="invalid_claim", message=str(exc)), 400
        try:
            publisher.publish(job["job_id"])
        except Exception as exc:
            store.cancel_unpublished(job["job_id"], f"publish failed: {type(exc).__name__}")
            LOGGER.exception("job publish failed", extra={"job_id": job["job_id"]})
            return jsonify(error="queue_unavailable"), 503

        if settings.local_inline_worker:
            threading.Thread(
                target=_run_inline_worker,
                args=(worker, job["job_id"], settings.max_delivery_attempts),
                daemon=True,
            ).start()
        response = jsonify(
            job_id=job["job_id"],
            status=job["status"],
            claim=asdict(claim),
            status_url=url_for("get_claim", claim_id=job["job_id"]),
        )
        response.status_code = 202
        response.headers["Location"] = url_for("get_claim", claim_id=job["job_id"])
        return response

    @app.get("/claims/<claim_id>")
    def get_claim(claim_id: str):
        if len(claim_id) != 32 or not all(char in "0123456789abcdef" for char in claim_id):
            return jsonify(error="not_found"), 404
        job = store.get(claim_id)
        if job is None:
            return jsonify(error="not_found"), 404
        visible = {
            key: value
            for key, value in job.items()
            if key
            in {
                "job_id",
                "status",
                "claim",
                "created_at",
                "updated_at",
                "completed_at",
                "dossier",
                "progress",
            }
        }
        if local_only_mode and isinstance(visible.get("dossier"), dict):
            visible["dossier"] = redact_dossier_for_display(visible["dossier"])
        return jsonify(visible)

    @app.post("/worker")
    def pubsub_worker():
        try:
            oidc_verifier(
                request.headers.get("Authorization"),
                audience=settings.pubsub_audience,
                expected_service_account=settings.pubsub_service_account,
            )
        except AuthenticationError as exc:
            return jsonify(error="unauthorized", message=str(exc)), 401
        try:
            envelope = parse_push_envelope(request.get_json(silent=False))
        except (ValueError, TypeError) as exc:
            return jsonify(error="invalid_push", message=str(exc)), 400
        try:
            worker.process(envelope.job_id, envelope.delivery_attempt)
        except BusyJob:
            return jsonify(status="lease_active"), 409
        except TerminalJob:
            return jsonify(status="terminal_failure", action="dead_letter"), 500
        except Exception:
            return jsonify(status="retry"), 500
        return "", 204

    return app
