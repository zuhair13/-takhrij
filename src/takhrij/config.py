"""Runtime configuration with fail-closed production validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = "development"
    project_id: str = ""
    location: str = "global"
    model_id: str = "gemini-3.5-flash"
    firestore_collection: str = "claims"
    pubsub_topic: str = "takhrij-claims"
    pubsub_audience: str = ""
    pubsub_service_account: str = ""
    corpus_db_path: Path = Path("data/takhrij.db")
    corpus_release: str = "UNCONFIGURED"
    corpus_book_ids: tuple[str, ...] = ()
    lease_seconds: int = 900
    max_matches: int = 200
    max_variants: int = 64
    max_active_jobs: int = 1
    max_jobs_per_day: int = 20
    max_delivery_attempts: int = 5
    local_inline_worker: bool = False

    @property
    def production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def topic_path(self) -> str:
        return f"projects/{self.project_id}/topics/{self.pubsub_topic}"

    def validate(self) -> None:
        errors: list[str] = []
        if self.model_id != "gemini-3.5-flash":
            errors.append("GEMINI_MODEL_ID must remain pinned to gemini-3.5-flash")
        if self.lease_seconds < 600:
            errors.append("LEASE_SECONDS must be at least the 600-second Pub/Sub ack deadline")
        if self.max_matches < 1 or self.max_variants < 1:
            errors.append("MAX_MATCHES and MAX_VARIANTS must be positive")
        if self.production:
            required = {
                "GOOGLE_CLOUD_PROJECT": self.project_id,
                "PUBSUB_AUDIENCE": self.pubsub_audience,
                "PUBSUB_SERVICE_ACCOUNT": self.pubsub_service_account,
            }
            errors.extend(
                f"{name} is required in production" for name, value in required.items() if not value
            )
            if self.corpus_release in {"", "UNCONFIGURED", "FIXTURE-ONLY"}:
                errors.append("CORPUS_RELEASE must name the verified pinned release in production")
            if not self.corpus_book_ids:
                errors.append("CORPUS_BOOK_IDS must declare the production book list")
        if not self.corpus_db_path.is_file():
            errors.append(f"corpus database does not exist: {self.corpus_db_path}")
        if errors:
            raise ValueError("; ".join(errors))


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    books = tuple(
        filter(None, (part.strip() for part in os.getenv("CORPUS_BOOK_IDS", "").split(",")))
    )
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        model_id=os.getenv("GEMINI_MODEL_ID", "gemini-3.5-flash"),
        firestore_collection=os.getenv("FIRESTORE_COLLECTION", "claims"),
        pubsub_topic=os.getenv("PUBSUB_TOPIC", "takhrij-claims"),
        pubsub_audience=os.getenv("PUBSUB_AUDIENCE", ""),
        pubsub_service_account=os.getenv("PUBSUB_SERVICE_ACCOUNT", ""),
        corpus_db_path=Path(os.getenv("CORPUS_DB_PATH", "data/takhrij.db")),
        corpus_release=os.getenv("CORPUS_RELEASE", "UNCONFIGURED"),
        corpus_book_ids=books,
        lease_seconds=int(os.getenv("LEASE_SECONDS", "900")),
        max_matches=int(os.getenv("MAX_MATCHES", "200")),
        max_variants=int(os.getenv("MAX_VARIANTS", "64")),
        max_active_jobs=int(os.getenv("MAX_ACTIVE_JOBS", "1")),
        max_jobs_per_day=int(os.getenv("MAX_JOBS_PER_DAY", "20")),
        max_delivery_attempts=int(os.getenv("MAX_DELIVERY_ATTEMPTS", "5")),
        local_inline_worker=_as_bool(os.getenv("LOCAL_INLINE_WORKER", "false")),
    )
