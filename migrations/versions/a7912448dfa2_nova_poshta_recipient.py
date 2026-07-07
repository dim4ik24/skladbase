"""nova poshta recipient

Revision ID: a7912448dfa2
Revises: c6a97e0f6791
Create Date: 2026-07-07 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7912448dfa2'
down_revision: str | Sequence[str] | None = 'c6a97e0f6791'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('np_recipient', sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.drop_column('np_recipient')
