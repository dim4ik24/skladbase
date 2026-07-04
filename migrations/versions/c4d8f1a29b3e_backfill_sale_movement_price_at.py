"""backfill price_at for existing sale movements

Revision ID: c4d8f1a29b3e
Revises: 8229a20023d2
Create Date: 2026-07-04 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d8f1a29b3e'
down_revision: str | Sequence[str] | None = '8229a20023d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Ad-hoc проекції (не app.models — інцидент 722d93030623: моделі можуть
# змінитись, а міграція має лишатись коректним знімком СХЕМИ на цей момент,
# незалежно від майбутнього коду).
stock_movements = sa.table(
    "stock_movements",
    sa.column("id", sa.Integer),
    sa.column("variant_id", sa.Integer),
    sa.column("type", sa.String),
    sa.column("price_at", sa.Numeric(12, 2)),
)
variants = sa.table(
    "variants",
    sa.column("id", sa.Integer),
    sa.column("price", sa.Numeric(12, 2)),
)


def upgrade() -> None:
    conn = op.get_bind()

    price_subquery = (
        sa.select(variants.c.price)
        .where(variants.c.id == stock_movements.c.variant_id)
        .scalar_subquery()
    )

    conn.execute(
        stock_movements.update()
        .where(
            # type — нативний Postgres ENUM (movementtype) у проді, plain
            # TEXT на sqlite (CI/dev). Ad-hoc sa.column тут заявлений як
            # sa.String, тож порівняння з голим рядком без касту падає на
            # Postgres так само, як у 722d93030623: "operator does not
            # exist: movementtype = character varying". Каст КОЛОНКИ до
            # Text прибирає розбіжність на обох базах (sqlite: no-op,
            # Postgres: enum::text = varchar — валідно).
            sa.cast(stock_movements.c.type, sa.Text) == "sale",
            stock_movements.c.price_at.is_(None),
        )
        .values(price_at=price_subquery)
    )


def downgrade() -> None:
    # Свідомо no-op, не симетричний upgrade(). Одноразовий backfill
    # некоректно реверсувати: після upgrade() застосунок (fulfill()/
    # write_off(reason="sold")) сам продовжує ставити price_at для НОВИХ
    # sale-рухів — на момент можливого downgrade їх уже не відрізнити від
    # тих, що заповнив саме цей backfill (обидва мають price_at NOT NULL,
    # той самий тип руху). Обнулити ВСІ price_at за type=sale знищило б і
    # легітимні, щойно записані застосунком значення — гірше, ніж нічого
    # не робити.
    pass
