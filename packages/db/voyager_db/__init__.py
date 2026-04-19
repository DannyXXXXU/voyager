"""voyager_db — Postgres schema + session helpers for Voyager."""
from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from .models import (
    Brief,
    Comment,
    Insight,
    InsightKind,
    LLMStatus,
    Transcript,
    Video,
)

__all__ = [
    "Brief",
    "Comment",
    "Insight",
    "InsightKind",
    "LLMStatus",
    "Transcript",
    "Video",
    "get_engine",
    "get_session",
    "sync_engine",
]


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Expected e.g. "
            "postgresql+psycopg://user:pwd@host:5432/voyager?sslmode=require"
        )
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a process-wide cached SQLAlchemy engine built from DATABASE_URL."""
    return create_engine(_database_url(), pool_pre_ping=True, future=True)


def sync_engine() -> Engine:
    """Alias for get_engine() — returned engine is synchronous (psycopg v3)."""
    return get_engine()


def get_session() -> Generator[Session, None, None]:
    """FastAPI-compatible dependency that yields a SQLModel Session."""
    with Session(get_engine()) as session:
        yield session
