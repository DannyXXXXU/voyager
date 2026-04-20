"""Dev smoke script — NOT a unit test.

Enqueues one IngestJob and polls Postgres for Video rows.
Requires live Azure resources (secrets via env vars or Key Vault).

Usage:
    export KEY_VAULT_NAME=kv-voyager-sexwh5
    az login
    uv run python scripts/smoke_local.py
"""
from __future__ import annotations

import asyncio
import sys
import time

from sqlalchemy import create_engine
from sqlmodel import Session, select

from voyager_common import get_settings
from voyager_db.models import Video
from voyager_tools.servicebus import IngestJob, IngestProducer

POLL_INTERVAL_S = 10
POLL_MAX_S = 300


async def _send(producer: IngestProducer, job: IngestJob) -> None:
    await producer.send(job)


def main() -> int:
    settings = get_settings()
    if not (settings.service_bus_conn and settings.database_url):
        print("error: missing service_bus_conn or database_url", file=sys.stderr)
        return 2

    job = IngestJob(topic="west sichuan travel", max_videos=3)
    print(f"→ enqueuing job_id={job.job_id} topic={job.topic!r}")
    producer = IngestProducer(settings.service_bus_conn)
    asyncio.run(_send(producer, job))

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    deadline = time.time() + POLL_MAX_S
    print(f"→ polling Postgres every {POLL_INTERVAL_S}s for up to {POLL_MAX_S}s…")
    while time.time() < deadline:
        with Session(engine) as s:
            rows = s.exec(select(Video).limit(10)).all()
            print(f"  videos in DB: {len(rows)}")
            if rows:
                for v in rows[:5]:
                    print(f"    - {v.video_id}: {v.title!r} status={v.llm_status}")
                return 0
        time.sleep(POLL_INTERVAL_S)

    print("timeout: no videos appeared in 300s")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
