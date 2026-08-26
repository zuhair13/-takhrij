"""Job state, quotas, leases, and compare-and-set finalization."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from takhrij.models import Claim, JobStatus


class CapacityExceeded(RuntimeError):
    pass


class ClaimOutcome(StrEnum):
    ACQUIRED = "acquired"
    BUSY = "busy"
    COMPLETE = "complete"
    FAILED = "failed"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    outcome: ClaimOutcome
    job: dict[str, Any] | None = None
    attempt_id: str | None = None


class JobStore(Protocol):
    def create(self, claim: Claim) -> dict[str, Any]: ...

    def get(self, job_id: str) -> dict[str, Any] | None: ...

    def claim(self, job_id: str) -> ClaimedJob: ...

    def renew(self, job_id: str, attempt_id: str) -> bool: ...

    def progress(
        self, job_id: str, attempt_id: str, stage: str, details: dict[str, Any]
    ) -> bool: ...

    def complete(self, job_id: str, attempt_id: str, dossier: dict[str, Any]) -> bool: ...

    def retry(self, job_id: str, attempt_id: str, error: str) -> bool: ...

    def fail(self, job_id: str, attempt_id: str, error: str) -> bool: ...

    def cancel_unpublished(self, job_id: str, error: str) -> None: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def day_key(now: datetime | None = None) -> str:
    return (now or utc_now()).date().isoformat()


class InMemoryJobStore:
    """Thread-safe development adapter with production-equivalent semantics."""

    def __init__(self, *, lease_seconds: int, max_active: int, max_daily: int):
        self.lease_seconds = lease_seconds
        self.max_active = max_active
        self.max_daily = max_daily
        self._jobs: dict[str, dict[str, Any]] = {}
        self._quotas: dict[str, dict[str, int]] = {}
        self._lock = threading.RLock()

    def create(self, claim: Claim) -> dict[str, Any]:
        with self._lock:
            today = day_key()
            quota = self._quotas.setdefault(today, {"active": 0, "created": 0})
            if quota["active"] >= self.max_active or quota["created"] >= self.max_daily:
                raise CapacityExceeded("Public demo capacity reached; try again later.")
            now = utc_now()
            job_id = uuid.uuid4().hex
            job = {
                "job_id": job_id,
                "status": JobStatus.QUEUED.value,
                "claim": asdict(claim),
                "created_at": now,
                "updated_at": now,
                "quota_day": today,
                "attempt_id": None,
                "lease_expires_at": None,
                "attempts": [],
                "dossier": None,
                "progress": {"stage": "queued"},
            }
            self._jobs[job_id] = job
            quota["active"] += 1
            quota["created"] += 1
            return copy.deepcopy(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job) if job else None

    def claim(self, job_id: str) -> ClaimedJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return ClaimedJob(ClaimOutcome.MISSING)
            if job["status"] == JobStatus.COMPLETE.value:
                return ClaimedJob(ClaimOutcome.COMPLETE, copy.deepcopy(job))
            if job["status"] == JobStatus.FAILED.value:
                return ClaimedJob(ClaimOutcome.FAILED, copy.deepcopy(job))
            now = utc_now()
            lease = job.get("lease_expires_at")
            if job["status"] == JobStatus.RUNNING.value and lease and lease > now:
                return ClaimedJob(ClaimOutcome.BUSY, copy.deepcopy(job))
            attempt_id = uuid.uuid4().hex
            job.update(
                status=JobStatus.RUNNING.value,
                attempt_id=attempt_id,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                updated_at=now,
            )
            job["attempts"] = [
                *job.get("attempts", [])[-19:],
                {"attempt_id": attempt_id, "started_at": now},
            ]
            return ClaimedJob(ClaimOutcome.ACQUIRED, copy.deepcopy(job), attempt_id)

    def renew(self, job_id: str, attempt_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                not job
                or job.get("status") != JobStatus.RUNNING.value
                or job.get("attempt_id") != attempt_id
            ):
                return False
            now = utc_now()
            job["lease_expires_at"] = now + timedelta(seconds=self.lease_seconds)
            job["updated_at"] = now
            return True

    def progress(self, job_id: str, attempt_id: str, stage: str, details: dict[str, Any]) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                not job
                or job.get("status") != JobStatus.RUNNING.value
                or job.get("attempt_id") != attempt_id
            ):
                return False
            job["progress"] = {"stage": stage, **copy.deepcopy(details), "updated_at": utc_now()}
            job["updated_at"] = utc_now()
            return True

    def complete(self, job_id: str, attempt_id: str, dossier: dict[str, Any]) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                not job
                or job.get("status") != JobStatus.RUNNING.value
                or job.get("attempt_id") != attempt_id
            ):
                return False
            now = utc_now()
            job.update(
                status=JobStatus.COMPLETE.value,
                dossier=dossier,
                lease_expires_at=None,
                updated_at=now,
                completed_at=now,
            )
            self._decrement_active(job)
            return True

    def retry(self, job_id: str, attempt_id: str, error: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                not job
                or job.get("status") != JobStatus.RUNNING.value
                or job.get("attempt_id") != attempt_id
            ):
                return False
            job.update(
                status=JobStatus.QUEUED.value,
                lease_expires_at=None,
                last_error=error[:1000],
                updated_at=utc_now(),
            )
            return True

    def fail(self, job_id: str, attempt_id: str, error: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                not job
                or job.get("status") != JobStatus.RUNNING.value
                or job.get("attempt_id") != attempt_id
            ):
                return False
            job.update(
                status=JobStatus.FAILED.value,
                lease_expires_at=None,
                last_error=error[:1000],
                updated_at=utc_now(),
            )
            self._decrement_active(job)
            return True

    def cancel_unpublished(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] != JobStatus.QUEUED.value:
                return
            job.update(status=JobStatus.FAILED.value, last_error=error[:1000], updated_at=utc_now())
            self._decrement_active(job)

    def _decrement_active(self, job: dict[str, Any]) -> None:
        quota = self._quotas.get(job["quota_day"])
        if quota:
            quota["active"] = max(0, quota["active"] - 1)


class FirestoreJobStore:
    """Firestore adapter. Every state transition is a transaction."""

    def __init__(
        self,
        *,
        project_id: str,
        collection: str,
        lease_seconds: int,
        max_active: int,
        max_daily: int,
    ):
        from google.cloud import firestore

        self.firestore = firestore
        self.client = firestore.Client(project=project_id)
        self.collection = self.client.collection(collection)
        self.meta = self.client.collection(f"{collection}__meta")
        self.lease_seconds = lease_seconds
        self.max_active = max_active
        self.max_daily = max_daily

    def create(self, claim: Claim) -> dict[str, Any]:
        now = utc_now()
        today = day_key(now)
        job_id = uuid.uuid4().hex
        job_ref = self.collection.document(job_id)
        quota_ref = self.meta.document(f"quota-{today}")
        job = {
            "job_id": job_id,
            "status": JobStatus.QUEUED.value,
            "claim": asdict(claim),
            "created_at": now,
            "updated_at": now,
            "quota_day": today,
            "attempt_id": None,
            "lease_expires_at": None,
            "attempts": [],
            "dossier": None,
            "progress": {"stage": "queued"},
        }

        @self.firestore.transactional
        def create_tx(transaction):
            snapshot = quota_ref.get(transaction=transaction)
            quota = snapshot.to_dict() if snapshot.exists else {"active": 0, "created": 0}
            if (
                quota.get("active", 0) >= self.max_active
                or quota.get("created", 0) >= self.max_daily
            ):
                raise CapacityExceeded("Public demo capacity reached; try again later.")
            transaction.set(
                quota_ref,
                {"active": quota.get("active", 0) + 1, "created": quota.get("created", 0) + 1},
            )
            transaction.create(job_ref, job)

        create_tx(self.client.transaction())
        return job

    def get(self, job_id: str) -> dict[str, Any] | None:
        snapshot = self.collection.document(job_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def claim(self, job_id: str) -> ClaimedJob:
        ref = self.collection.document(job_id)

        @self.firestore.transactional
        def claim_tx(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return ClaimedJob(ClaimOutcome.MISSING)
            job = snapshot.to_dict()
            if job["status"] == JobStatus.COMPLETE.value:
                return ClaimedJob(ClaimOutcome.COMPLETE, job)
            if job["status"] == JobStatus.FAILED.value:
                return ClaimedJob(ClaimOutcome.FAILED, job)
            now = utc_now()
            lease = job.get("lease_expires_at")
            if job["status"] == JobStatus.RUNNING.value and lease and lease > now:
                return ClaimedJob(ClaimOutcome.BUSY, job)
            attempt_id = uuid.uuid4().hex
            attempts = [
                *job.get("attempts", [])[-19:],
                {"attempt_id": attempt_id, "started_at": now},
            ]
            updates = {
                "status": JobStatus.RUNNING.value,
                "attempt_id": attempt_id,
                "lease_expires_at": now + timedelta(seconds=self.lease_seconds),
                "updated_at": now,
                "attempts": attempts,
            }
            transaction.update(ref, updates)
            job.update(updates)
            return ClaimedJob(ClaimOutcome.ACQUIRED, job, attempt_id)

        return claim_tx(self.client.transaction())

    def renew(self, job_id: str, attempt_id: str) -> bool:
        ref = self.collection.document(job_id)

        @self.firestore.transactional
        def renew_tx(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            job = snapshot.to_dict()
            if job.get("status") != JobStatus.RUNNING.value or job.get("attempt_id") != attempt_id:
                return False
            now = utc_now()
            transaction.update(
                ref,
                {
                    "lease_expires_at": now + timedelta(seconds=self.lease_seconds),
                    "updated_at": now,
                },
            )
            return True

        return renew_tx(self.client.transaction())

    def progress(self, job_id: str, attempt_id: str, stage: str, details: dict[str, Any]) -> bool:
        ref = self.collection.document(job_id)

        @self.firestore.transactional
        def progress_tx(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            job = snapshot.to_dict()
            if job.get("status") != JobStatus.RUNNING.value or job.get("attempt_id") != attempt_id:
                return False
            now = utc_now()
            transaction.update(
                ref,
                {"progress": {"stage": stage, **details, "updated_at": now}, "updated_at": now},
            )
            return True

        return progress_tx(self.client.transaction())

    def complete(self, job_id: str, attempt_id: str, dossier: dict[str, Any]) -> bool:
        return self._finish(job_id, attempt_id, JobStatus.COMPLETE, {"dossier": dossier})

    def retry(self, job_id: str, attempt_id: str, error: str) -> bool:
        ref = self.collection.document(job_id)

        @self.firestore.transactional
        def retry_tx(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            job = snapshot.to_dict()
            if job.get("status") != JobStatus.RUNNING.value or job.get("attempt_id") != attempt_id:
                return False
            transaction.update(
                ref,
                {
                    "status": JobStatus.QUEUED.value,
                    "lease_expires_at": None,
                    "last_error": error[:1000],
                    "updated_at": utc_now(),
                },
            )
            return True

        return retry_tx(self.client.transaction())

    def fail(self, job_id: str, attempt_id: str, error: str) -> bool:
        return self._finish(
            job_id,
            attempt_id,
            JobStatus.FAILED,
            {"last_error": error[:1000]},
        )

    def cancel_unpublished(self, job_id: str, error: str) -> None:
        ref = self.collection.document(job_id)

        @self.firestore.transactional
        def cancel_tx(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return
            job = snapshot.to_dict()
            if job.get("status") != JobStatus.QUEUED.value:
                return
            quota_ref = self.meta.document(f"quota-{job['quota_day']}")
            quota_snapshot = quota_ref.get(transaction=transaction)
            quota = (
                quota_snapshot.to_dict() if quota_snapshot.exists else {"active": 0, "created": 0}
            )
            transaction.update(
                ref,
                {
                    "status": JobStatus.FAILED.value,
                    "last_error": error[:1000],
                    "updated_at": utc_now(),
                },
            )
            transaction.set(quota_ref, {**quota, "active": max(0, quota.get("active", 0) - 1)})

        cancel_tx(self.client.transaction())

    def _finish(
        self,
        job_id: str,
        attempt_id: str,
        status: JobStatus,
        extra: dict[str, Any],
    ) -> bool:
        ref = self.collection.document(job_id)

        @self.firestore.transactional
        def finish_tx(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            job = snapshot.to_dict()
            if job.get("status") != JobStatus.RUNNING.value or job.get("attempt_id") != attempt_id:
                return False
            quota_ref = self.meta.document(f"quota-{job['quota_day']}")
            quota_snapshot = quota_ref.get(transaction=transaction)
            quota = (
                quota_snapshot.to_dict() if quota_snapshot.exists else {"active": 0, "created": 0}
            )
            now = utc_now()
            transaction.update(
                ref,
                {
                    "status": status.value,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "completed_at": now,
                    **extra,
                },
            )
            transaction.set(quota_ref, {**quota, "active": max(0, quota.get("active", 0) - 1)})
            return True

        return finish_tx(self.client.transaction())
