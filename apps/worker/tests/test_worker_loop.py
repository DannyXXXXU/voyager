"""Tests for the worker async loop — mock consumer + process fn."""
from __future__ import annotations

from typing import AsyncIterator

import pytest

from voyager_tools.servicebus import IngestJob
from voyager_worker.main import run_loop


class FakeConsumer:
    def __init__(self, jobs: list[IngestJob]):
        self._jobs = jobs
        self.completed: list[str] = []

    def iter_jobs(self) -> AsyncIterator:
        return self._iter()

    async def _iter(self):
        for j in self._jobs:
            async def _complete(jid=j.job_id):
                self.completed.append(jid)
            yield j, _complete


async def test_run_loop_success_completes_messages():
    jobs = [IngestJob(topic="a"), IngestJob(topic="b")]
    consumer = FakeConsumer(jobs)

    calls: list[str] = []

    async def _process(job, _sf):
        calls.append(job.job_id)

    await run_loop(consumer, session_factory=lambda: None, process_job=_process)

    assert len(calls) == 2
    assert set(consumer.completed) == {jobs[0].job_id, jobs[1].job_id}


async def test_run_loop_exception_does_not_complete():
    jobs = [IngestJob(topic="boom")]
    consumer = FakeConsumer(jobs)

    async def _process(job, _sf):
        raise RuntimeError("transient failure")

    await run_loop(consumer, session_factory=lambda: None, process_job=_process)
    assert consumer.completed == []  # left for redelivery


async def test_run_loop_mixed_success_and_failure():
    jobs = [IngestJob(topic="ok"), IngestJob(topic="fail"), IngestJob(topic="ok2")]
    consumer = FakeConsumer(jobs)

    async def _process(job, _sf):
        if job.topic == "fail":
            raise RuntimeError("bad")

    await run_loop(consumer, session_factory=lambda: None, process_job=_process)

    assert set(consumer.completed) == {jobs[0].job_id, jobs[2].job_id}
    assert jobs[1].job_id not in consumer.completed
