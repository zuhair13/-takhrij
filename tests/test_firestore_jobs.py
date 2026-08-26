from __future__ import annotations

import copy
import unittest
from datetime import timedelta

from takhrij.jobs import CapacityExceeded, ClaimOutcome, FirestoreJobStore, utc_now
from takhrij.models import Claim, JobStatus


class FakeSnapshot:
    def __init__(self, value):
        self._value = value
        self.exists = value is not None

    def to_dict(self):
        return copy.deepcopy(self._value)


class FakeDocument:
    def __init__(self, records, key):
        self.records = records
        self.key = key

    def get(self, transaction=None):
        del transaction
        return FakeSnapshot(self.records.get(self.key))


class FakeCollection:
    def __init__(self, records, name):
        self.records = records
        self.name = name

    def document(self, document_id):
        return FakeDocument(self.records, (self.name, document_id))


class FakeTransaction:
    @staticmethod
    def create(ref, value):
        if ref.key in ref.records:
            raise RuntimeError("document already exists")
        ref.records[ref.key] = copy.deepcopy(value)

    @staticmethod
    def set(ref, value):
        ref.records[ref.key] = copy.deepcopy(value)

    @staticmethod
    def update(ref, value):
        ref.records[ref.key].update(copy.deepcopy(value))


class FakeClient:
    def __init__(self, records):
        self.records = records

    def collection(self, name):
        return FakeCollection(self.records, name)

    @staticmethod
    def transaction():
        return FakeTransaction()


class FakeFirestore:
    @staticmethod
    def transactional(function):
        return function


def make_store(*, max_active=1, max_daily=3):
    records = {}
    store = object.__new__(FirestoreJobStore)
    store.firestore = FakeFirestore()
    store.client = FakeClient(records)
    store.collection = store.client.collection("claims")
    store.meta = store.client.collection("claims__meta")
    store.lease_seconds = 900
    store.max_active = max_active
    store.max_daily = max_daily
    return store, records


class FirestoreJobStoreTests(unittest.TestCase):
    def setUp(self):
        self.store, self.records = make_store()
        self.claim = Claim("تخريج", "دليل", 500, "FIXTURE-ONLY", ("fixture-early",))

    def quota(self, job):
        return self.records[("claims__meta", f"quota-{job['quota_day']}")]

    def test_create_get_and_capacity_are_transactional(self):
        job = self.store.create(self.claim)
        self.assertEqual(self.store.get(job["job_id"]), job)
        self.assertEqual(self.quota(job), {"active": 1, "created": 1})
        with self.assertRaises(CapacityExceeded):
            self.store.create(self.claim)
        self.assertIsNone(self.store.get("missing"))

    def test_claim_covers_terminal_busy_and_expired_states(self):
        self.assertEqual(self.store.claim("missing").outcome, ClaimOutcome.MISSING)
        job = self.store.create(self.claim)
        acquired = self.store.claim(job["job_id"])
        self.assertEqual(acquired.outcome, ClaimOutcome.ACQUIRED)
        self.assertEqual(self.store.claim(job["job_id"]).outcome, ClaimOutcome.BUSY)

        stored = self.records[("claims", job["job_id"])]
        stored["lease_expires_at"] = utc_now() - timedelta(seconds=1)
        reclaimed = self.store.claim(job["job_id"])
        self.assertEqual(reclaimed.outcome, ClaimOutcome.ACQUIRED)
        self.assertNotEqual(reclaimed.attempt_id, acquired.attempt_id)

        stored["status"] = JobStatus.COMPLETE.value
        self.assertEqual(self.store.claim(job["job_id"]).outcome, ClaimOutcome.COMPLETE)
        stored["status"] = JobStatus.FAILED.value
        self.assertEqual(self.store.claim(job["job_id"]).outcome, ClaimOutcome.FAILED)

    def test_renew_and_progress_are_compare_and_set(self):
        job = self.store.create(self.claim)
        claimed = self.store.claim(job["job_id"])
        self.assertFalse(self.store.renew("missing", "attempt"))
        self.assertFalse(self.store.renew(job["job_id"], "stale"))
        self.assertTrue(self.store.renew(job["job_id"], claimed.attempt_id))

        self.assertFalse(self.store.progress("missing", "attempt", "stage", {}))
        self.assertFalse(self.store.progress(job["job_id"], "stale", "stage", {}))
        self.assertTrue(
            self.store.progress(job["job_id"], claimed.attempt_id, "audit", {"findings": 1})
        )
        progress = self.store.get(job["job_id"])["progress"]
        self.assertEqual(progress["stage"], "audit")
        self.assertEqual(progress["findings"], 1)

    def test_retry_is_compare_and_set_and_retains_quota(self):
        job = self.store.create(self.claim)
        claimed = self.store.claim(job["job_id"])
        self.assertFalse(self.store.retry("missing", "attempt", "error"))
        self.assertFalse(self.store.retry(job["job_id"], "stale", "error"))
        self.assertTrue(self.store.retry(job["job_id"], claimed.attempt_id, "x" * 1100))
        retried = self.store.get(job["job_id"])
        self.assertEqual(retried["status"], JobStatus.QUEUED.value)
        self.assertEqual(len(retried["last_error"]), 1000)
        self.assertEqual(self.quota(job)["active"], 1)

    def test_complete_and_fail_release_quota_once(self):
        job = self.store.create(self.claim)
        claimed = self.store.claim(job["job_id"])
        self.assertFalse(self.store.complete("missing", "attempt", {}))
        self.assertFalse(self.store.complete(job["job_id"], "stale", {}))
        self.assertTrue(self.store.complete(job["job_id"], claimed.attempt_id, {"ok": True}))
        completed = self.store.get(job["job_id"])
        self.assertEqual(completed["status"], JobStatus.COMPLETE.value)
        self.assertEqual(completed["dossier"], {"ok": True})
        self.assertEqual(self.quota(job)["active"], 0)
        self.assertFalse(self.store.complete(job["job_id"], claimed.attempt_id, {}))

        second = self.store.create(self.claim)
        second_claim = self.store.claim(second["job_id"])
        self.assertTrue(self.store.fail(second["job_id"], second_claim.attempt_id, "poison"))
        failed = self.store.get(second["job_id"])
        self.assertEqual(failed["status"], JobStatus.FAILED.value)
        self.assertEqual(failed["last_error"], "poison")
        self.assertEqual(self.quota(second)["active"], 0)

    def test_cancel_unpublished_only_cancels_queued_job(self):
        self.store.cancel_unpublished("missing", "publish failed")
        job = self.store.create(self.claim)
        self.store.cancel_unpublished(job["job_id"], "publish failed")
        cancelled = self.store.get(job["job_id"])
        self.assertEqual(cancelled["status"], JobStatus.FAILED.value)
        self.assertEqual(self.quota(job)["active"], 0)

        second = self.store.create(self.claim)
        claimed = self.store.claim(second["job_id"])
        self.store.cancel_unpublished(second["job_id"], "too late")
        self.assertEqual(self.store.get(second["job_id"])["status"], JobStatus.RUNNING.value)
        self.store.fail(second["job_id"], claimed.attempt_id, "cleanup")


if __name__ == "__main__":
    unittest.main()
