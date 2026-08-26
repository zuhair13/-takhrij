from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from takhrij.config import Settings
from takhrij.index_builder import build_index
from takhrij.jobs import InMemoryJobStore
from takhrij.publisher import RecordingPublisher
from takhrij.web import _run_inline_worker, _select_asset_root, create_app

ROOT = Path(__file__).resolve().parents[1]


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "fixture.db"
        build_index(ROOT / "config" / "corpus_manifest.fixture.json", db_path)
        self.settings = Settings(
            corpus_db_path=db_path,
            corpus_release="FIXTURE-ONLY",
            corpus_book_ids=("fixture-early", "fixture-late"),
            pubsub_audience="http://local/worker",
            pubsub_service_account="local@example.invalid",
        )
        self.store = InMemoryJobStore(lease_seconds=900, max_active=1, max_daily=20)
        self.publisher = RecordingPublisher()

    def tearDown(self):
        self.temp.cleanup()

    def _app(self, **kwargs):
        app = create_app(
            settings=self.settings,
            store=self.store,
            publisher=self.publisher,
            **kwargs,
        )
        app.testing = True
        return app

    @staticmethod
    def _claim():
        return {
            "form": "تخريج",
            "target_sense": "دليل يُستند إليه",
            "cutoff_year_ah": 500,
        }

    @staticmethod
    def _push(job_id: str, delivery_attempt: int = 1):
        data = base64.b64encode(json.dumps({"job_id": job_id}).encode()).decode()
        return {
            "message": {"data": data},
            "deliveryAttempt": delivery_attempt,
        }

    def test_installed_container_falls_back_to_runtime_asset_root(self):
        source_root = Path(self.temp.name) / "installed-python"
        runtime_root = Path(self.temp.name) / "app"
        (runtime_root / "templates").mkdir(parents=True)
        (runtime_root / "static").mkdir()

        self.assertEqual(_select_asset_root(source_root, runtime_root), runtime_root)

    def test_inline_failure_releases_demo_capacity(self):
        def failing_runner(*_args, **_kwargs):
            raise RuntimeError("synthetic failure")

        app = self._app(worker_runner=failing_runner)
        client = app.test_client()
        created = client.post("/claims", json=self._claim()).get_json()
        worker = app.extensions["takhrij_worker"]

        with self.assertLogs("takhrij.web", level="ERROR"):
            _run_inline_worker(worker, created["job_id"], self.settings.max_delivery_attempts)

        self.assertEqual(self.store.get(created["job_id"])["status"], "failed")
        self.assertEqual(client.post("/claims", json=self._claim()).status_code, 202)

    def test_public_form_is_bilingual_and_claim_returns_202(self):
        client = self._app().test_client()
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Intended sense", page.get_data(as_text=True))
        self.assertIn("المعنى المقصود", page.get_data(as_text=True))

        response = client.post("/claims", json=self._claim())
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(self.publisher.job_ids, [body["job_id"]])
        self.assertEqual(body["status_url"], f"/claims/{body['job_id']}")
        status = client.get(f"/claims/{body['job_id']}")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["status"], "queued")

    def test_worker_rejects_missing_identity(self):
        client = self._app().test_client()
        response = client.post("/worker", json=self._push("a" * 32))
        self.assertEqual(response.status_code, 401)

    def test_authenticated_worker_persists_progress_and_completion(self):
        def verifier(*_args, **_kwargs):
            return {"email": self.settings.pubsub_service_account}

        def runner(_index, _settings, _claim, progress):
            progress(
                "provisional",
                {
                    "label": "PROVISIONAL_NO_EARLIER_MATCH_IN_DECLARED_CORPUS",
                    "verdict": "NO_EARLIER_MATCH_IN_DECLARED_CORPUS",
                },
            )
            progress("devils_advocate", {"completed": True, "findings": 1})
            return {"gate_passed": True, "verdict": "EARLIER_MATCH_FOUND"}

        client = self._app(oidc_verifier=verifier, worker_runner=runner).test_client()
        created = client.post("/claims", json=self._claim()).get_json()
        response = client.post(
            "/worker",
            json=self._push(created["job_id"]),
            headers={"Authorization": "Bearer test"},
        )
        self.assertEqual(response.status_code, 204)
        job = client.get(f"/claims/{created['job_id']}").get_json()
        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["progress"]["stage"], "devils_advocate")
        self.assertEqual(job["dossier"]["verdict"], "EARLIER_MATCH_FOUND")


if __name__ == "__main__":
    unittest.main()
