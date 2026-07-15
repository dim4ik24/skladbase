"""shop owner language code

Revision ID: 9b84d24b200f
Revises: 8d3e46c65646
Create Date: 2026-07-15 16:51:14.197250

i18n Стадія 4: джерело мови для cron-пушів бота (app/tasks.py), де немає
live Telegram Update, щоб узяти language_code напряму. Знімається з
initData при bootstrap_shop (app/services/bootstrap.py); nullable=False з
server_default='uk' — існуючі магазини (створені до цієї стадії) просто
отримують дефолт, не мігруються заднім числом.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9b84d24b200f'
down_revision: str | Sequence[str] | None = '8d3e46c65646'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('owner_language_code', sa.String(length=8), server_default='uk', nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.drop_column('owner_language_code')
