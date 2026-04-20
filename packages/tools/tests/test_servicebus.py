"""Tests for Service Bus producer/consumer helpers (fully mocked)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from voyager_tools.servicebus import IngestConsumer, IngestJob, IngestProducer


def test_ingest_job_roundtrip() -> None:
    job = IngestJob(topic="Yunnan travel", keywords=["yunnan", "china travel"])
    body = job.to_message_body()
    loaded = IngestJob.from_message_body(body)
    assert loaded.topic == "Yunnan travel"
    assert loaded.keywords == ["yunnan", "china travel"]
    assert loaded.max_videos == 20
    assert loaded.region_code == "US"
    assert loaded.language == "en"
    assert loaded.job_id == job.job_id


def test_ingest_job_default_job_id_is_uuid() -> None:
    j1 = IngestJob(topic="a")
    j2 = IngestJob(topic="a")
    assert j1.job_id != j2.job_id
    assert len(j1.job_id) >= 32


def _make_async_cm(inner: Any) -> Any:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_producer_send_serializes_and_calls_send_messages(mocker: Any) -> None:
    sender = MagicMock()
    sender.send_messages = AsyncMock()
    sender_cm = _make_async_cm(sender)

    client = MagicMock()
    client.get_queue_sender = MagicMock(return_value=sender_cm)
    client_cm = _make_async_cm(client)

    mocker.patch(
        "voyager_tools.servicebus.ServiceBusClient.from_connection_string",
        return_value=client_cm,
    )

    producer = IngestProducer("Endpoint=sb://fake/;SharedAccessKey=x", queue_name="ingest")
    job = IngestJob(topic="xinjiang", keywords=["xinjiang travel"], max_videos=5)
    await producer.send(job)

    client.get_queue_sender.assert_called_once_with(queue_name="ingest")
    sender.send_messages.assert_awaited_once()
    (msg,), _ = sender.send_messages.call_args
    # msg is a ServiceBusMessage; body is bytes-ish
    body_attr = msg.body
    if not isinstance(body_attr, (bytes, str)):
        body_attr = b"".join(body_attr)
    body_str = body_attr.decode("utf-8") if isinstance(body_attr, (bytes, bytearray)) else body_attr
    roundtrip = IngestJob.model_validate_json(body_str)
    assert roundtrip.topic == "xinjiang"
    assert roundtrip.max_videos == 5
    assert msg.message_id == job.job_id


class _AsyncIter:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)

    def __aiter__(self) -> "_AsyncIter":
        return self

    async def __anext__(self) -> Any:
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class _FakeReceiver:
    def __init__(self, messages: list[Any]) -> None:
        self._messages = messages
        self.complete_calls: list[Any] = []

    async def __aenter__(self) -> "_FakeReceiver":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def __aiter__(self) -> _AsyncIter:
        return _AsyncIter(self._messages)

    async def complete_message(self, msg: Any) -> None:
        self.complete_calls.append(msg)


@pytest.mark.asyncio
async def test_consumer_iter_jobs_yields_parsed_job_and_complete_callback(
    mocker: Any,
) -> None:
    job = IngestJob(topic="sichuan", keywords=["chengdu"], max_videos=3)
    fake_msg = MagicMock()
    fake_msg.body = job.to_message_body().encode("utf-8")

    receiver = _FakeReceiver([fake_msg])

    client = MagicMock()
    client.get_queue_receiver = MagicMock(return_value=receiver)
    client_cm = _make_async_cm(client)

    mocker.patch(
        "voyager_tools.servicebus.ServiceBusClient.from_connection_string",
        return_value=client_cm,
    )

    consumer = IngestConsumer("Endpoint=sb://fake/;SharedAccessKey=x")
    yielded: list[Any] = []
    async for got_job, complete in consumer.iter_jobs():
        yielded.append((got_job, complete))
        await complete()

    assert len(yielded) == 1
    got_job, _complete = yielded[0]
    assert got_job.topic == "sichuan"
    assert got_job.max_videos == 3
    assert receiver.complete_calls == [fake_msg]


@pytest.mark.asyncio
async def test_consumer_handles_iterable_body(mocker: Any) -> None:
    job = IngestJob(topic="tibet")
    fake_msg = MagicMock()
    # Service Bus sometimes returns a generator of byte chunks
    fake_msg.body = iter([job.to_message_body().encode("utf-8")])

    receiver = _FakeReceiver([fake_msg])

    client = MagicMock()
    client.get_queue_receiver = MagicMock(return_value=receiver)
    client_cm = _make_async_cm(client)

    mocker.patch(
        "voyager_tools.servicebus.ServiceBusClient.from_connection_string",
        return_value=client_cm,
    )

    consumer = IngestConsumer("Endpoint=sb://fake/;SharedAccessKey=x")
    async for parsed, _ in consumer.iter_jobs():
        assert parsed.topic == "tibet"
        break
