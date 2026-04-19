"""Alembic env — reads DATABASE_URL from environment (never hardcode)."""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import models so SQLModel.metadata is populated.
from voyager_db import models  # noqa: F401

load_dotenv()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError(
        "DATABASE_URL env var required for alembic. "
        "Example: postgresql+psycopg://user:pwd@host:5432/voyager?sslmode=require"
    )
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
