"""Offline CLI tests using typer.testing.CliRunner."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from typer.testing import CliRunner

from voyager_db.models import Brief as _Brief


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


_Brief.__table__.c.video_ids.type = JSON()

from voyager_cli import main as cli_main
from voyager_cli.main import app
from voyager_common import Settings
from voyager_db.models import Brief, LLMStatus, Video


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture
def patched(engine, monkeypatch):
    """Patch get_settings + _engine/_session helpers to use sqlite."""

    def _settings():
        return Settings(
            database_url="sqlite://",
            service_bus_conn="Endpoint=sb://fake/",
        )

    monkeypatch.setattr(cli_main, "get_settings", _settings)
    monkeypatch.setattr(cli_main, "_engine", lambda _url: engine)
    monkeypatch.setattr(cli_main, "_session", lambda _url: Session(engine))
    yield engine


@pytest.fixture
def runner():
    return CliRunner()


def test_submit_sends_to_service_bus(patched, runner, monkeypatch):
    mock_send = AsyncMock(return_value=None)

    class FakeProducer:
        def __init__(self, *a, **kw):
            self.send = mock_send

    monkeypatch.setattr(cli_main, "IngestProducer", FakeProducer)

    result = runner.invoke(
        app, ["eric", "submit", "sichuan trip", "--max-videos", "5"]
    )
    assert result.exit_code == 0, result.output
    assert "queued" in result.output
    assert mock_send.await_count == 1


def test_status_empty(patched, runner):
    result = runner.invoke(app, ["eric", "status"])
    assert result.exit_code == 0
    assert "Video LLM status" in result.output
    assert "total videos: 0" in result.output


def test_status_with_rows(patched, runner):
    with Session(patched) as s:
        s.add(Video(video_id="v1", title="t1", llm_status=LLMStatus.pending))
        s.add(Video(video_id="v2", title="t2", llm_status=LLMStatus.done))
        s.add(Video(video_id="v3", title="t3", llm_status=LLMStatus.done))
        s.commit()

    result = runner.invoke(app, ["eric", "status"])
    assert result.exit_code == 0
    assert "total videos: 3" in result.output


def test_process_noop_when_no_pending(patched, runner):
    result = runner.invoke(app, ["eric", "process"])
    assert result.exit_code == 0
    assert "no pending" in result.output


def test_brief_not_found(patched, runner):
    result = runner.invoke(app, ["eric", "brief", "no-such-topic"])
    assert result.exit_code == 1
    assert "no brief" in result.output


def test_brief_prints_markdown(patched, runner):
    with Session(patched) as s:
        s.add(
            Brief(
                topic="sichuan",
                video_ids=["v1"],
                content_md="# Sichuan Brief\n\nHello",
                llm_status=LLMStatus.done,
            )
        )
        s.commit()
    result = runner.invoke(app, ["eric", "brief", "sichuan"])
    assert result.exit_code == 0
    assert "Sichuan" in result.output
