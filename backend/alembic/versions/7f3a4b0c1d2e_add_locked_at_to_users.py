"""add locked_at to users

Revision ID: 7f3a4b0c1d2e
Revises: e12d31b238c8
Create Date: 2026-08-12 09:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '7f3a4b0c1d2e'
down_revision: str | None = 'e12d31b238c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('users', 'locked_at')
