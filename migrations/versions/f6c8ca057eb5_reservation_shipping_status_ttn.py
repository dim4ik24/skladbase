"""reservation shipping status ttn

Revision ID: f6c8ca057eb5
Revises: d2451c6a628e
Create Date: 2026-07-04 23:53:08.263151

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6c8ca057eb5'
down_revision: str | Sequence[str] | None = 'd2451c6a628e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Нативний enum-тип (reservationstatus) на Postgres — ADD VALUE не можна
        # виконати в межах звичайної транзакції на старих PG, тому autocommit_block.
        # На sqlite (dev/CI) ReservationStatus рендериться як VARCHAR(9) без
        # CHECK-обмеження (звірено дампом схеми) — нове значення там DDL не потребує,
        # "shipped" (7 симв.) вже влазить у наявний VARCHAR(9).
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE reservationstatus ADD VALUE IF NOT EXISTS 'shipped'")

    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ttn', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Postgres не підтримує ALTER TYPE ... DROP VALUE — прибрати значення з
    # нативного enum можна лише перестворенням типу, що небезпечно якщо в
    # таблиці вже є рядки зі status='shipped'. Downgrade навмисно не чіпає
    # enum-тип, лише знімає додані колонки.
    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.drop_column('shipped_at')
        batch_op.drop_column('ttn')
