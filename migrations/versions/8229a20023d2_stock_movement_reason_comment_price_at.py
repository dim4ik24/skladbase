"""stock movement reason comment price_at

Revision ID: 8229a20023d2
Revises: 245bf88efba3
Create Date: 2026-07-04 10:55:42.880660

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '8229a20023d2'
down_revision: str | Sequence[str] | None = '245bf88efba3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reason', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('comment', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('price_at', sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('stock_movements', schema=None) as batch_op:
        batch_op.drop_column('price_at')
        batch_op.drop_column('comment')
        batch_op.drop_column('reason')
