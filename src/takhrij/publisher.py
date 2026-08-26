"""Queue publisher adapters."""

from __future__ import annotations

import json
from typing import Protocol


class Publisher(Protocol):
    def publish(self, job_id: str) -> None: ...


class PubSubPublisher:
    def __init__(self, topic_path: str):
        from google.cloud import pubsub_v1

        self.topic_path = topic_path
        self.client = pubsub_v1.PublisherClient()

    def publish(self, job_id: str) -> None:
        payload = json.dumps({"job_id": job_id}, separators=(",", ":")).encode()
        self.client.publish(self.topic_path, payload, job_id=job_id).result(timeout=30)


class RecordingPublisher:
    """Development/test publisher that records messages without hidden work."""

    def __init__(self):
        self.job_ids: list[str] = []

    def publish(self, job_id: str) -> None:
        self.job_ids.append(job_id)
