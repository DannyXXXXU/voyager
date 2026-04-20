"""Test-wide fixtures: teach SQLite compiler how to render Postgres-only types.

The production schema uses JSONB and ARRAY columns. For offline tests we run
against SQLite in-memory, so we register @compiles hooks that fall back to
JSON/TEXT on SQLite.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # type: ignore[no-untyped-def]
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):  # type: ignore[no-untyped-def]
    return "JSON"
