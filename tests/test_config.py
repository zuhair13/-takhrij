from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from takhrij.config import Settings, load_settings


class ConfigTests(unittest.TestCase):
    def test_production_validation_fails_closed(self):
        settings = Settings(
            app_env="production",
            model_id="unapproved-model",
            lease_seconds=599,
            max_matches=0,
            max_variants=0,
            corpus_db_path=Path("missing.db"),
        )
        with self.assertRaises(ValueError) as raised:
            settings.validate()
        message = str(raised.exception)
        self.assertIn("GEMINI_MODEL_ID", message)
        self.assertIn("LEASE_SECONDS", message)
        self.assertIn("GOOGLE_CLOUD_PROJECT", message)
        self.assertIn("CORPUS_RELEASE", message)
        self.assertIn("CORPUS_BOOK_IDS", message)
        self.assertIn("corpus database does not exist", message)

    def test_valid_production_settings_and_derived_topic(self):
        with tempfile.NamedTemporaryFile() as database:
            settings = Settings(
                app_env="production",
                project_id="takhrij-project",
                pubsub_audience="https://takhrij.example/worker",
                pubsub_service_account="push@example.invalid",
                corpus_db_path=Path(database.name),
                corpus_release="2025.1.9",
                corpus_book_ids=("book-a",),
            )
            settings.validate()
            self.assertTrue(settings.production)
            self.assertEqual(
                settings.topic_path,
                "projects/takhrij-project/topics/takhrij-claims",
            )

    def test_environment_loader_parses_books_numbers_and_boolean(self):
        environment = {
            "APP_ENV": "development",
            "GOOGLE_CLOUD_PROJECT": "project",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GEMINI_MODEL_ID": "gemini-3.5-flash",
            "FIRESTORE_COLLECTION": "jobs",
            "PUBSUB_TOPIC": "topic",
            "PUBSUB_AUDIENCE": "audience",
            "PUBSUB_SERVICE_ACCOUNT": "push@example.invalid",
            "CORPUS_DB_PATH": "fixture.db",
            "CORPUS_RELEASE": "release",
            "CORPUS_BOOK_IDS": "book-a, book-b,",
            "LEASE_SECONDS": "1200",
            "MAX_MATCHES": "50",
            "MAX_VARIANTS": "10",
            "MAX_ACTIVE_JOBS": "2",
            "MAX_JOBS_PER_DAY": "7",
            "MAX_DELIVERY_ATTEMPTS": "4",
            "LOCAL_INLINE_WORKER": "yes",
        }
        with patch.dict("os.environ", environment, clear=True):
            settings = load_settings()
        self.assertEqual(settings.corpus_book_ids, ("book-a", "book-b"))
        self.assertEqual(settings.lease_seconds, 1200)
        self.assertEqual(settings.max_matches, 50)
        self.assertEqual(settings.max_variants, 10)
        self.assertEqual(settings.max_active_jobs, 2)
        self.assertEqual(settings.max_jobs_per_day, 7)
        self.assertEqual(settings.max_delivery_attempts, 4)
        self.assertTrue(settings.local_inline_worker)


if __name__ == "__main__":
    unittest.main()
