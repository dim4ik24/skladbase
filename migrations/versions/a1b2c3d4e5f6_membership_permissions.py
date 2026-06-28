"""membership granular permissions

Revision ID: a1b2c3d4e5f6
Revises: f3a7c2d9e4b1
Create Date: 2026-06-28 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = 'f3a7c2d9e4b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERM_COLUMNS = [
    'can_view_inventory',
    'can_edit_products',
    'can_manage_reservations',
    'can_manage_stock',
    'can_view_finance',
    'can_manage_billing',
]


def upgrade() -> None:
    with op.batch_alter_table('memberships', schema=None) as batch_op:
        for col in _PERM_COLUMNS:
            batch_op.add_column(
                sa.Column(col, sa.Boolean(), nullable=False, server_default='1')
            )


def downgrade() -> None:
    with op.batch_alter_table('memberships', schema=None) as batch_op:
        for col in _PERM_COLUMNS:
            batch_op.drop_column(col)
