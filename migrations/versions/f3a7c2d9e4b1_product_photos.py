"""product photos gallery

Revision ID: f3a7c2d9e4b1
Revises: e7f4db7e4cdc
Create Date: 2026-06-27 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a7c2d9e4b1'
down_revision: str | Sequence[str] | None = 'e7f4db7e4cdc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'product_photos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_product_photos_product_id'), 'product_photos', ['product_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_product_photos_product_id'), table_name='product_photos')
    op.drop_table('product_photos')
