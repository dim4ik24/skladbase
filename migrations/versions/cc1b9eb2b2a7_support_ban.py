"""support ban

Revision ID: cc1b9eb2b2a7
Revises: a7912448dfa2
Create Date: 2026-07-07 00:10:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'cc1b9eb2b2a7'
down_revision: str | Sequence[str] | None = 'a7912448dfa2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'support_bans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tg_id', sa.BigInteger(), nullable=False),
        sa.Column('muted_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('banned', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('support_bans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_support_bans_tg_id'), ['tg_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('support_bans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_support_bans_tg_id'))

    op.drop_table('support_bans')
