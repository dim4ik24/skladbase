"""
Data-міграція 722d93030623 (клас "Одяг" -> атрибут product_type), пункт 11 фідбеку.

Ця міграція виконує select+update поза ORM-моделями (app.models), тож і
тест навмисно НЕ використовує async-фікстуру `_isolated_db` з conftest.py
(яка будує схему з поточних моделей — там уже нова схема сіда, ідемпотентність
міграції нічим не перевірити). Замість цього — окремий синхронний sqlite-рушій
із рядком шаблону у СТАРІЙ формі (як на проді до релізу), і виклик
upgrade()/downgrade() напряму з підміненим `op` (щоб не піднімати повний
Alembic runtime заради двох SELECT/UPDATE).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "722d93030623_clothing_template_product_type_attribute.py"
)

OLD_SCHEMA = {
    "attributes": [
        {"key": "material", "label": "Матеріал", "type": "string"},
        {"key": "brand", "label": "Бренд", "type": "string"},
    ],
    "variant_axes": [
        {"key": "size", "label": "Розмір", "type": "enum",
         "options": ["XS", "S", "M", "L", "XL", "XXL"]},
        {"key": "color", "label": "Колір", "type": "string"},
    ],
}


class _FakeOp:
    """Підміняє `alembic.op` у модулі міграції — потрібен лише get_bind()."""

    def __init__(self, connection: sa.engine.Connection) -> None:
        self._connection = connection

    def get_bind(self) -> sa.engine.Connection:
        return self._connection


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_product_type_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_engine_with_clothing_row() -> tuple[sa.engine.Engine, sa.Table]:
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    metadata = sa.MetaData()
    product_templates = sa.Table(
        "product_templates", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shop_id", sa.Integer, nullable=True),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("field_schema", sa.JSON, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            product_templates.insert().values(
                shop_id=None, code="clothing", field_schema=OLD_SCHEMA,
            )
        )
    return engine, product_templates


def _clothing_attributes(engine: sa.engine.Engine, table: sa.Table) -> list[dict]:
    with engine.connect() as conn:
        schema = conn.execute(
            sa.select(table.c.field_schema).where(
                table.c.shop_id.is_(None), table.c.code == "clothing"
            )
        ).scalar_one()
    return schema["attributes"]


def test_upgrade_prepends_product_type_on_clean_db() -> None:
    migration = _load_migration()
    engine, table = _make_engine_with_clothing_row()

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()

    attributes = _clothing_attributes(engine, table)
    assert attributes[0]["key"] == "product_type"
    assert attributes[0]["type"] == "enum"
    assert "Худі" in attributes[0]["options"]
    # решта старих атрибутів лишаються, у тому ж порядку
    assert [a["key"] for a in attributes[1:]] == ["material", "brand"]


def test_upgrade_is_idempotent() -> None:
    migration = _load_migration()
    engine, table = _make_engine_with_clothing_row()

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()
    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()  # другий прогін — не має продублювати

    attributes = _clothing_attributes(engine, table)
    assert [a["key"] for a in attributes] == ["product_type", "material", "brand"]


def test_downgrade_removes_product_type_and_is_idempotent() -> None:
    migration = _load_migration()
    engine, table = _make_engine_with_clothing_row()

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()
    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.downgrade()

    attributes = _clothing_attributes(engine, table)
    assert [a["key"] for a in attributes] == ["material", "brand"]

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.downgrade()  # другий прогін — не має падати чи щось міняти

    attributes = _clothing_attributes(engine, table)
    assert [a["key"] for a in attributes] == ["material", "brand"]


def test_upgrade_noop_when_clothing_template_missing() -> None:
    migration = _load_migration()
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    metadata = sa.MetaData()
    sa.Table(
        "product_templates", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shop_id", sa.Integer, nullable=True),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("field_schema", sa.JSON, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()  # порожня таблиця — не повинно кидати помилку
