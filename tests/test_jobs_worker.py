from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from takhrij.config import Settings
from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index
from takhrij.jobs import CapacityExceeded, ClaimOutcome, InMemoryJobStore, utc_now
from takhrij.models import Claim, JobStatus
from takhrij.worker import ClaimWorker, TerminalJob, parse_push_envelope

ROOT = Path(__file__).resolve().parents[1]


class JobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "fixture.db"
        build_index(ROOT / "config" / "corpus_manifest.fixture.json", db_path)
        self.store = InMemoryJobStore(lease_seconds=900, max_active=1, max_daily=2)
        self.claim = Claim("تخريج", "دليل", 500, "FIXTURE-ONLY", ("fixture-early",))
        self.settings = Settings(
            corpus_db_path=db_path,
            corpus_release="FIXTURE-ONLY",
            corpus_book_ids=("fixture-early",),
            pubsub_audience="http://local/worker",
            pubsub_service_account="local@example.invalid",
        )
        self.index = CorpusIndex(db_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_lease_blocks_duplicate_and_expired_lease_is_reclaimed(self):
        job = self.store.create(self.claim)
        first = self.store.claim(job["job_id"])
        self.assertEqual(first.outcome, ClaimOutcome.ACQUIRED)
        self.assertEqual(self.store.claim(job["job_id"]).outcome, ClaimOutcome.BUSY)
        self.store._jobs[job["job_id"]]["lease_expires_at"] = utc_now() - timedelta(seconds=1)
        second = self.store.claim(job["job_id"])
        self.assertEqual(second.outcome, ClaimOutcome.ACQUIRED)
        self.assertNotEqual(first.attempt_id, second.attempt_id)

    def test_stale_attempt_cannot_overwrite_final_result(self):
        job = self.store.create(self.claim)
        first = self.store.claim(job["job_id"])
        self.store._jobs[job["job_id"]]["lease_expires_at"] = utc_now() - timedelta(seconds=1)
        second = self.store.claim(job["job_id"])
        self.assertTrue(self.store.complete(job["job_id"], second.attempt_id, {"new": True}))
        self.assertFalse(self.store.complete(job["job_id"], first.attempt_id, {"old": True}))
        self.assertEqual(self.store.get(job["job_id"])["dossier"], {"new": True})

    def test_capacity_is_transactional_in_adapter(self):
        self.store.create(self.claim)
        with self.assertRaises(CapacityExceeded):
            self.store.create(self.claim)

    def test_push_envelope_decoding(self):
        job_id = "a" * 32
        data = base64.b64encode(json.dumps({"job_id": job_id}).encode()).decode()
        envelope = parse_push_envelope({"message": {"data": data}, "deliveryAttempt": 3})
        self.assertEqual(envelope.job_id, job_id)
        self.assertEqual(envelope.delivery_attempt, 3)
        with self.assertRaises(ValueError):
            parse_push_envelope({"message": {"data": "not-base64"}})

    def test_terminal_failure_releases_active_quota(self):
        job = self.store.create(self.claim)

        def poison(*_args):
            raise RuntimeError("poison")

        worker = ClaimWorker(
            store=self.store,
            index=self.index,
            settings=self.settings,
            runner=poison,
        )
        with self.assertRaises(RuntimeError):
            worker.process(job["job_id"], delivery_attempt=self.settings.max_delivery_attempts)
        failed = self.store.get(job["job_id"])
        self.assertEqual(failed["status"], JobStatus.FAILED.value)
        self.assertIsNone(failed["lease_expires_at"])
        with self.assertRaises(TerminalJob):
            worker.process(job["job_id"], delivery_attempt=self.settings.max_delivery_attempts + 1)
        self.store.create(self.claim)

    def test_retryable_failure_keeps_active_quota(self):
        job = self.store.create(self.claim)

        def retryable(*_args):
            raise RuntimeError("temporary")

        worker = ClaimWorker(
            store=self.store,
            index=self.index,
            settings=self.settings,
            runner=retryable,
        )
        with self.assertRaises(RuntimeError):
            worker.process(job["job_id"], delivery_attempt=1)
        self.assertEqual(self.store.get(job["job_id"])["status"], JobStatus.QUEUED.value)
        with self.assertRaises(CapacityExceeded):
            self.store.create(self.claim)


if __name__ == "__main__":
    unittest.main()
