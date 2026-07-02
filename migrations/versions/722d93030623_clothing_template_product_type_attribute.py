"""clothing template product type attribute

Revision ID: 722d93030623
Revises: a1b2c3d4e5f6
Create Date: 2026-07-02 13:01:06.001693

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '722d93030623'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Сід (app/seed.py) лише СТВОРЮЄ рядок, якщо його нема — на БД, де глобальний
# шаблон "Одяг" вже засіяний зі старою схемою, новий код сіда його не оновить.
# Тому product_type довставляємо тут, окремою data-міграцією.
PRODUCT_TYPE_ATTRIBUTE = {
    "key": "product_type",
    "label": "Тип",
    "type": "enum",
    "options": [
        "Футболка", "Худі", "Светр", "Сорочка", "Штани", "Шорти",
        "Куртка", "Взуття", "Аксесуар", "Інше",
    ],
}

# Легка ad-hoc проекція таблиці (а не імпорт app.models) — щоб міграція
# лишалась коректною навіть якщо модель зміниться в майбутньому.
product_templates = sa.table(
    "product_templates",
    sa.column("id", sa.Integer),
    sa.column("shop_id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("field_schema", sa.JSON),
)


def _get_clothing_row(conn: sa.engine.Connection) -> sa.engine.Row | None:
    return conn.execute(
        sa.select(product_templates.c.id, product_templates.c.field_schema).where(
            product_templates.c.shop_id.is_(None),
            # code — нативний Postgres ENUM (templatecode) у проді, plain TEXT
            # на sqlite (CI). Ad-hoc sa.table()/sa.column() тут не знає
            # реального типу колонки, тож порівняння з голим рядком генерує
            # `operator does not exist: templatecode = character varying` на
            # Postgres. Каст КОЛОНКИ до Text прибирає розбіжність на обох базах
            # (sqlite: no-op, Postgres: enum::text = varchar — валідно).
            sa.cast(product_templates.c.code, sa.Text) == "clothing",
        )
    ).first()


def upgrade() -> None:
    conn = op.get_bind()
    row = _get_clothing_row(conn)
    if row is None:
        return  # глобальний шаблон "Одяг" ще не засіяний — сід сам додасть нову схему

    schema = dict(row.field_schema or {})
    attributes = list(schema.get("attributes") or [])
    if any(attr.get("key") == "product_type" for attr in attributes):
        return  # вже застосовано (ідемпотентність)

    schema["attributes"] = [PRODUCT_TYPE_ATTRIBUTE, *attributes]
    conn.execute(
        product_templates.update()
        .where(product_templates.c.id == row.id)
        .values(field_schema=schema)
    )


def downgrade() -> None:
    conn = op.get_bind()
    row = _get_clothing_row(conn)
    if row is None:
        return

    schema = dict(row.field_schema or {})
    attributes = list(schema.get("attributes") or [])
    filtered = [attr for attr in attributes if attr.get("key") != "product_type"]
    if len(filtered) == len(attributes):
        return  # вже відсутнє (ідемпотентність)

    schema["attributes"] = filtered
    conn.execute(
        product_templates.update()
        .where(product_templates.c.id == row.id)
        .values(field_schema=schema)
    )
