"""stock movement reservation link

Revision ID: 7aeff9226ecc
Revises: cc1b9eb2b2a7
Create Date: 2026-07-07 00:20:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7aeff9226ecc'
down_revision: str | Sequence[str] | None = 'cc1b9eb2b2a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reservation_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_stock_movements_reservation_id',
            'reservations',
            ['reservation_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            batch_op.f('ix_stock_movements_reservation_id'), ['reservation_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stock_movements_reservation_id'))
        batch_op.drop_constraint('fk_stock_movements_reservation_id', type_='foreignkey')
        batch_op.drop_column('reservation_id')
