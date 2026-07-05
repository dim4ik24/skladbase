"""nova poshta sender profile

Revision ID: c6a97e0f6791
Revises: 501d3f657117
Create Date: 2026-07-05 10:30:23.536311

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c6a97e0f6791'
down_revision: str | Sequence[str] | None = '501d3f657117'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.add_column(sa.Column('np_sender_city_ref', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('np_sender_city_name', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('np_sender_warehouse_ref', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('np_sender_warehouse_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('np_sender_phone', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('np_sender_name', sa.String(length=160), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.drop_column('np_sender_name')
        batch_op.drop_column('np_sender_phone')
        batch_op.drop_column('np_sender_warehouse_name')
        batch_op.drop_column('np_sender_warehouse_ref')
        batch_op.drop_column('np_sender_city_name')
        batch_op.drop_column('np_sender_city_ref')
