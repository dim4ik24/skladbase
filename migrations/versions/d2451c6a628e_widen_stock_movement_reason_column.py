"""widen stock movement reason column

Revision ID: d2451c6a628e
Revises: c4d8f1a29b3e
Create Date: 2026-07-04 23:25:53.252615

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd2451c6a628e'
down_revision: str | Sequence[str] | None = 'c4d8f1a29b3e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.alter_column(
            'reason',
            existing_type=sa.String(length=20),
            type_=sa.String(length=40),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.alter_column(
            'reason',
            existing_type=sa.String(length=40),
            type_=sa.String(length=20),
            existing_nullable=True,
        )
