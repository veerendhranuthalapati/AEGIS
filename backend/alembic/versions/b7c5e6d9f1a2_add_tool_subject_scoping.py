"""add subject_scoped + resource_id_argument to tools

Revision ID: b7c5e6d9f1a2
Revises: 7f3a4b0c1d2e
Create Date: 2026-08-12 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b7c5e6d9f1a2'
down_revision: str | None = '7f3a4b0c1d2e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'tools',
        sa.Column('subject_scoped', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'tools', sa.Column('resource_id_argument', sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tools', 'resource_id_argument')
    op.drop_column('tools', 'subject_scoped')
