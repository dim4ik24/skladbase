"""nova poshta key and tracking status

Revision ID: 501d3f657117
Revises: f6c8ca057eb5
Create Date: 2026-07-05 00:36:53.277545

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '501d3f657117'
down_revision: str | Sequence[str] | None = 'f6c8ca057eb5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.add_column(sa.Column('np_api_key_encrypted', sa.String(length=500), nullable=True))

    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('np_status', sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.drop_column('np_status')

    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.drop_column('np_api_key_encrypted')
