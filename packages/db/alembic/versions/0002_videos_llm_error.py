"""add videos.llm_error column for failure diagnostics

Revision ID: 0002_videos_llm_error
Revises: 0001_initial_schema
Create Date: 2026-04-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_videos_llm_error"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("llm_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("videos", "llm_error")
