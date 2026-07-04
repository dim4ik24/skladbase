"""
Data-міграція c4d8f1a29b3e (backfill price_at для існуючих sale-рухів).

Той самий підхід, що test_migration_product_type.py: міграція працює поза
ORM-моделями (app.models), тож окремий синхронний sqlite-рушій з ad-hoc
таблицями замість `_isolated_db`-фікстури з conftest.py, і виклик
upgrade()/downgrade() напряму з підміненим `op`.
"""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions" / "c4d8f1a29b3e_backfill_sale_movement_price_at.py"
)


class _FakeOp:
    """Підміняє `alembic.op` у модулі міграції — потрібен лише get_bind()."""

    def __init__(self, connection: sa.engine.Connection) -> None:
        self._connection = connection

    def get_bind(self) -> sa.engine.Connection:
        return self._connection


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_backfill_price_at_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_engine() -> tuple[sa.engine.Engine, sa.Table, sa.Table]:
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    metadata = sa.MetaData()
    variants = sa.Table(
        "variants", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
    )
    stock_movements = sa.Table(
        "stock_movements", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("variant_id", sa.Integer, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("price_at", sa.Numeric(12, 2), nullable=True),
    )
    metadata.create_all(engine)
    return engine, variants, stock_movements


def _price_at(engine: sa.engine.Engine, table: sa.Table, movement_id: int) -> Decimal | None:
    with engine.connect() as conn:
        return conn.execute(
            sa.select(table.c.price_at).where(table.c.id == movement_id)
        ).scalar_one()


def test_upgrade_backfills_price_at_for_null_sale_movements() -> None:
    migration = _load_migration()
    engine, variants, stock_movements = _make_engine()

    with engine.begin() as conn:
        conn.execute(variants.insert().values(id=1, price=Decimal("150.00")))
        conn.execute(
            stock_movements.insert().values(
                id=1, variant_id=1, type="sale", price_at=None
            )
        )

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()

    assert _price_at(engine, stock_movements, 1) == Decimal("150.00")


def test_upgrade_does_not_touch_non_sale_movements() -> None:
    migration = _load_migration()
    engine, variants, stock_movements = _make_engine()

    with engine.begin() as conn:
        conn.execute(variants.insert().values(id=1, price=Decimal("150.00")))
        conn.execute(
            stock_movements.insert().values(
                id=1, variant_id=1, type="adjustment", price_at=None
            )
        )

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()

    assert _price_at(engine, stock_movements, 1) is None


def test_upgrade_does_not_overwrite_already_set_price_at() -> None:
    """Захист і від подвійного прогону, і від затирання legit-значень, які
    застосунок (fulfill()/write_off) уже встиг проставити САМ після схема-
    міграції, до того як цей backfill колись запустився."""
    migration = _load_migration()
    engine, variants, stock_movements = _make_engine()

    with engine.begin() as conn:
        conn.execute(variants.insert().values(id=1, price=Decimal("150.00")))
        conn.execute(
            stock_movements.insert().values(
                id=1, variant_id=1, type="sale", price_at=Decimal("99.00")
            )
        )

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()

    # variant.price змінилась би на 150, але тут уже БУЛО значення — не чіпаємо
    assert _price_at(engine, stock_movements, 1) == Decimal("99.00")


def test_upgrade_is_idempotent() -> None:
    migration = _load_migration()
    engine, variants, stock_movements = _make_engine()

    with engine.begin() as conn:
        conn.execute(variants.insert().values(id=1, price=Decimal("150.00")))
        conn.execute(
            stock_movements.insert().values(
                id=1, variant_id=1, type="sale", price_at=None
            )
        )

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()
    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()  # другий прогін — не має падати чи щось міняти

    assert _price_at(engine, stock_movements, 1) == Decimal("150.00")


def test_downgrade_is_noop() -> None:
    migration = _load_migration()
    engine, variants, stock_movements = _make_engine()

    with engine.begin() as conn:
        conn.execute(variants.insert().values(id=1, price=Decimal("150.00")))
        conn.execute(
            stock_movements.insert().values(
                id=1, variant_id=1, type="sale", price_at=None
            )
        )

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()
    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.downgrade()

    # downgrade() свідомий no-op — backfilled значення лишається
    assert _price_at(engine, stock_movements, 1) == Decimal("150.00")


def test_upgrade_noop_on_empty_table() -> None:
    migration = _load_migration()
    engine, _variants, _stock_movements = _make_engine()

    with engine.begin() as conn:
        migration.op = _FakeOp(conn)
        migration.upgrade()  # порожні таблиці — не повинно кидати помилку
