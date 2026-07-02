"""invites table

Revision ID: 245bf88efba3
Revises: 722d93030623
Create Date: 2026-07-02 13:46:31.576554

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '245bf88efba3'
down_revision: str | Sequence[str] | None = '722d93030623'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('created_by_tg_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    with op.batch_alter_table('invites', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invites_shop_id'), ['shop_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_invites_token'), ['token'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('invites', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invites_token'))
        batch_op.drop_index(batch_op.f('ix_invites_shop_id'))

    op.drop_table('invites')
