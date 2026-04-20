"""Async Service Bus consumer that runs the Eric data subgraph per job.

Loop:
    for job, complete in consumer.iter_jobs():
        state = EricState(from job)
        graph = build_data_graph(session_factory=...).compile()
        await graph.ainvoke(state)
        await complete()

On exception the message is NOT completed, so the broker will redeliver and
eventually dead-letter after max-delivery-count.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from sqlalchemy import create_engine
from sqlmodel import Session

from voyager_agents.eric import EricState, build_data_graph
from voyager_common import Settings, get_settings
from voyager_tools.servicebus import IngestConsumer, IngestJob

logger = logging.getLogger(__name__)


def _init_langfuse(settings: Settings) -> None:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("langfuse: keys missing, skipping init")
        return
    try:
        from langfuse import Langfuse  # type: ignore

        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or "https://cloud.langfuse.com",
        )
        # TODO: thread langfuse traces through node boundaries in M1.9.
        logger.info("langfuse: initialized")
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse: init failed: %s", exc)


def _build_session_factory(db_url: str) -> Callable[[], Session]:
    engine = create_engine(db_url, pool_pre_ping=True)

    def _factory() -> Session:
        return Session(engine)

    return _factory


async def _process_job(
    job: IngestJob,
    session_factory: Callable[[], Session],
) -> None:
    state = EricState(
        topic=job.topic,
        keywords=job.keywords,
        region_code=job.region_code,
        language=job.language,
        max_videos=job.max_videos,
    )
    graph = build_data_graph(session_factory=session_factory).compile()
    await graph.ainvoke(state)


async def run_loop(
    consumer: IngestConsumer,
    session_factory: Callable[[], Session],
    process_job: Callable[[IngestJob, Callable[[], Session]], Awaitable[None]] = _process_job,
) -> None:
    """Drive the async loop. Broken out so tests can call it with mocks."""
    async for job, complete in consumer.iter_jobs():
        logger.info("worker: received job %s topic=%r", job.job_id, job.topic)
        try:
            await process_job(job, session_factory)
            await complete()
            logger.info("worker: completed job %s", job.job_id)
        except Exception as exc:  # noqa: BLE001
            # Do NOT complete; let Service Bus redeliver / dead-letter.
            logger.exception("worker: job %s failed: %s", job.job_id, exc)


async def run() -> None:
    settings = get_settings()
    if not settings.service_bus_conn:
        raise RuntimeError("service_bus_conn is not configured")
    if not settings.database_url:
        raise RuntimeError("database_url is not configured")

    _init_langfuse(settings)
    consumer = IngestConsumer(settings.service_bus_conn)
    session_factory = _build_session_factory(settings.database_url)

    logger.info("worker: starting loop env=%s", settings.env)
    await run_loop(consumer, session_factory)


# Silence unused-import for mypy strict setups.
_ = Any
