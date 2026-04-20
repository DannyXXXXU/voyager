"""Azure Service Bus producer/consumer helpers for the ingest queue.

The cloud-worker consumes IngestJob messages from the `ingest` queue and runs
the data subgraph (search → metadata → audio → transcribe → comments → persist).
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient
from pydantic import BaseModel, Field

__all__ = ["IngestJob", "IngestProducer", "IngestConsumer"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IngestJob(BaseModel):
    """A unit of work for the cloud-worker data pipeline."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    keywords: list[str] = Field(default_factory=list)
    max_videos: int = 20
    region_code: str = "US"
    language: str = "en"
    created_at: datetime = Field(default_factory=_utcnow)

    def to_message_body(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_message_body(cls, body: str | bytes) -> "IngestJob":
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        return cls.model_validate_json(body)


class IngestProducer:
    """Send IngestJob messages to the Service Bus ingest queue."""

    def __init__(self, connection_string: str, queue_name: str = "ingest") -> None:
        self._conn_str = connection_string
        self._queue_name = queue_name

    def _client(self) -> ServiceBusClient:
        return ServiceBusClient.from_connection_string(self._conn_str)

    async def send(self, job: IngestJob) -> None:
        async with self._client() as client:
            sender = client.get_queue_sender(queue_name=self._queue_name)
            async with sender as s:
                msg = ServiceBusMessage(
                    job.to_message_body(),
                    content_type="application/json",
                    message_id=job.job_id,
                )
                await s.send_messages(msg)


def _body_to_str(msg: Any) -> str:
    body = msg.body if hasattr(msg, "body") else msg
    # SB receive typically returns a generator of bytes; concat if iterable
    if isinstance(body, (bytes, bytearray)):
        return body.decode("utf-8")
    if isinstance(body, str):
        return body
    try:
        chunks = b"".join(
            c if isinstance(c, (bytes, bytearray)) else str(c).encode("utf-8")
            for c in body
        )
        return chunks.decode("utf-8")
    except TypeError:
        return str(body)


class IngestConsumer:
    """Consume IngestJob messages from the Service Bus ingest queue.

    Usage:
        consumer = IngestConsumer(conn_str)
        async for job, complete in consumer.iter_jobs():
            try:
                await handle(job)
                await complete()
            except Exception:
                # message will be abandoned/dead-lettered by the broker lock timeout
                raise
    """

    def __init__(
        self,
        connection_string: str,
        queue_name: str = "ingest",
        max_wait_seconds: int = 30,
    ) -> None:
        self._conn_str = connection_string
        self._queue_name = queue_name
        self._max_wait = max_wait_seconds

    def _client(self) -> ServiceBusClient:
        return ServiceBusClient.from_connection_string(self._conn_str)

    async def iter_jobs(
        self, max_wait_seconds: int | None = None
    ) -> AsyncIterator[tuple[IngestJob, Callable[[], Awaitable[None]]]]:
        wait = max_wait_seconds if max_wait_seconds is not None else self._max_wait
        async with self._client() as client:
            receiver = client.get_queue_receiver(queue_name=self._queue_name)
            async with receiver as rx:
                async for msg in rx:
                    body = _body_to_str(msg)
                    job = IngestJob.from_message_body(body)

                    async def _complete(_msg: Any = msg, _rx: Any = rx) -> None:
                        await _rx.complete_message(_msg)

                    yield job, _complete
                _ = wait  # kept for API parity
