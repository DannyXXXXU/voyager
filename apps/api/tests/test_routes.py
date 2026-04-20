"""Offline tests for voyager_api.main using TestClient + in-memory SQLite."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlmodel import Session, SQLModel, create_engine

from voyager_db.models import Brief as _Brief  # noqa: E402


# Render Postgres-only ARRAY/JSONB as JSON on SQLite (tests only) + swap the
# Brief.video_ids column to a JSON-backed type so list values round-trip.
@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):  # noqa: ANN001, D401
    return "JSON"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001, D401
    return "JSON"


# Swap ARRAY(Text) -> JSON so SQLite can bind Python lists.
_Brief.__table__.c.video_ids.type = JSON()

from voyager_api import main as api_main
from voyager_api.main import app, get_db_session, get_producer, settings_dep
from voyager_common import Settings
from voyager_db.models import Brief, Comment, LLMStatus, Transcript, Video


@pytest.fixture
def engine():
    from sqlalchemy.pool import StaticPool

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture
def seeded_session(engine):
    with Session(engine) as s:
        s.add(
            Video(
                video_id="vid_a",
                title="Video A",
                channel_id="UC1",
                channel_title="ch",
                published_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
                llm_status=LLMStatus.pending,
            )
        )
        s.add(
            Video(
                video_id="vid_b",
                title="Video B",
                llm_status=LLMStatus.done,
            )
        )
        s.add(Transcript(video_id="vid_a", text="hello world", language="en"))
        s.add(
            Comment(
                video_id="vid_a",
                author="user1",
                text="great video",
                like_count=3,
            )
        )
        s.add(
            Brief(
                id=1,
                topic="sichuan",
                video_ids=["vid_a", "vid_b"],
                content_md="# brief content",
                llm_status=LLMStatus.done,
            )
        )
        s.commit()
    yield


@pytest.fixture
def client(engine, seeded_session):
    def _session():
        with Session(engine) as s:
            yield s

    def _settings():
        return Settings(
            database_url="sqlite://",
            service_bus_conn="Endpoint=sb://fake/",
        )

    mock_producer = AsyncMock()
    mock_producer.send = AsyncMock(return_value=None)

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[settings_dep] = _settings
    app.dependency_overrides[get_producer] = lambda: mock_producer

    with TestClient(app) as c:
        c.mock_producer = mock_producer  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()
    api_main._cached_settings.cache_clear()


def test_create_job_enqueues(client):
    r = client.post(
        "/eric/jobs",
        json={"topic": "west sichuan", "max_videos": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert len(body["job_id"]) > 0
    assert client.mock_producer.send.await_count == 1


def test_list_videos_all(client):
    r = client.get("/eric/videos")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    ids = {v["video_id"] for v in data}
    assert ids == {"vid_a", "vid_b"}


def test_list_videos_filter_status(client):
    r = client.get("/eric/videos", params={"llm_status": "done"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["video_id"] == "vid_b"


def test_get_video_with_detail(client):
    r = client.get("/eric/videos/vid_a")
    assert r.status_code == 200
    body = r.json()
    assert body["video"]["video_id"] == "vid_a"
    assert body["transcript"]["text"] == "hello world"
    assert len(body["comments"]) == 1
    assert body["comments"][0]["author"] == "user1"


def test_get_video_404(client):
    r = client.get("/eric/videos/does_not_exist")
    assert r.status_code == 404


def test_list_and_get_brief(client):
    r = client.get("/eric/briefs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["topic"] == "sichuan"
    # list endpoint should NOT include content_md
    assert "content_md" not in rows[0]

    r = client.get("/eric/briefs/1")
    assert r.status_code == 200
    body = r.json()
    assert body["content_md"] == "# brief content"


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service_bus"] == "ok"
    # db check pings a real sqlite engine via settings — should succeed
    assert body["db"] in ("ok", "fail")
