"""Pub/Sub push worker with OIDC verification, leases, and stale-attempt protection."""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from takhrij.agent import run_claim_sync
from takhrij.config import Settings
from takhrij.index import CorpusIndex
from takhrij.jobs import ClaimOutcome, JobStore

LOGGER = logging.getLogger(__name__)


class BusyJob(RuntimeError):
    pass


class TerminalJob(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerResult:
    action: str
    job_id: str
    attempt_id: str | None = None


@dataclass(frozen=True, slots=True)
class PushEnvelope:
    job_id: str
    delivery_attempt: int


def parse_push_envelope(payload: dict[str, Any]) -> PushEnvelope:
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("data"), str):
        raise ValueError("invalid Pub/Sub push envelope")
    try:
        decoded = base64.b64decode(message["data"], validate=True)
        data = json.loads(decoded)
    except Exception as exc:
        raise ValueError("invalid Pub/Sub message data") from exc
    job_id = data.get("job_id") if isinstance(data, dict) else None
    if (
        not isinstance(job_id, str)
        or len(job_id) != 32
        or not all(c in "0123456789abcdef" for c in job_id)
    ):
        raise ValueError("invalid job_id")
    raw_attempt = payload.get("deliveryAttempt", 1)
    try:
        delivery_attempt = max(1, int(raw_attempt))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid deliveryAttempt") from exc
    return PushEnvelope(job_id, delivery_attempt)


class LeaseKeeper:
    def __init__(self, store: JobStore, job_id: str, attempt_id: str, lease_seconds: int):
        self.store = store
        self.job_id = job_id
        self.attempt_id = attempt_id
        self.interval = max(30, lease_seconds // 3)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval):
            if not self.store.renew(self.job_id, self.attempt_id):
                LOGGER.warning(
                    "lease renewal rejected",
                    extra={"job_id": self.job_id, "attempt_id": self.attempt_id},
                )
                return


class ClaimWorker:
    def __init__(
        self,
        *,
        store: JobStore,
        index: CorpusIndex,
        settings: Settings,
        runner: Callable[
            [CorpusIndex, Settings, dict[str, Any], Callable[[str, dict[str, Any]], None]],
            dict[str, Any],
        ] = run_claim_sync,
    ):
        self.store = store
        self.index = index
        self.settings = settings
        self.runner = runner

    def process(self, job_id: str, delivery_attempt: int = 1) -> WorkerResult:
        claimed = self.store.claim(job_id)
        if claimed.outcome is ClaimOutcome.MISSING:
            return WorkerResult("ack_missing", job_id)
        if claimed.outcome is ClaimOutcome.COMPLETE:
            return WorkerResult("ack_complete", job_id)
        if claimed.outcome is ClaimOutcome.FAILED:
            raise TerminalJob(job_id)
        if claimed.outcome is ClaimOutcome.BUSY:
            raise BusyJob(job_id)
        assert claimed.job is not None and claimed.attempt_id is not None
        attempt_id = claimed.attempt_id
        LOGGER.info("attempt started", extra={"job_id": job_id, "attempt_id": attempt_id})
        try:

            def report_progress(stage: str, details: dict[str, Any]) -> None:
                self.store.progress(job_id, attempt_id, stage, details)

            with LeaseKeeper(self.store, job_id, attempt_id, self.settings.lease_seconds):
                dossier = self.runner(
                    self.index,
                    self.settings,
                    claimed.job["claim"],
                    report_progress,
                )
            if not self.store.complete(job_id, attempt_id, dossier):
                LOGGER.warning(
                    "stale attempt completion rejected",
                    extra={"job_id": job_id, "attempt_id": attempt_id},
                )
                return WorkerResult("ack_stale", job_id, attempt_id)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if delivery_attempt >= self.settings.max_delivery_attempts:
                self.store.fail(job_id, attempt_id, error)
            else:
                self.store.retry(job_id, attempt_id, error)
            LOGGER.exception(
                "attempt failed",
                extra={
                    "job_id": job_id,
                    "attempt_id": attempt_id,
                    "delivery_attempt": delivery_attempt,
                    "terminal": delivery_attempt >= self.settings.max_delivery_attempts,
                },
            )
            raise
        LOGGER.info("attempt completed", extra={"job_id": job_id, "attempt_id": attempt_id})
        return WorkerResult("ack_completed", job_id, attempt_id)
