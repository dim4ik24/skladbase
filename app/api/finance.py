from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_permission
from app.models import Membership, MovementType, Product, StockMovement, Variant, utcnow

router = APIRouter(prefix="/api/finance", tags=["finance"])

Period = Literal["week", "month", "year", "all"]
_PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}
_TOP_PRODUCTS_LIMIT = 5


def _to_decimal(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _period_since(period: Period) -> datetime | None:
    """all -> None (без фільтра, сумісність зі старою поведінкою)."""
    days = _PERIOD_DAYS.get(period)
    if days is None:
        return None
    return utcnow() - timedelta(days=days)


async def _movement_totals(
    session: AsyncSession,
    shop_id: int,
    movement_type: MovementType,
    since: datetime | None,
) -> tuple[int, int, Decimal]:
    """(кількість рухів, сума |delta|, сума |delta| * price_at) для одного типу.

    price_at може бути NULL для рухів, записаних до цієї фічі (стара БД) —
    SUM ігнорує NULL-доданки, тож такі рухи просто не додають доходу, а не
    ламають запит."""
    stmt = select(
        func.count(StockMovement.id),
        func.coalesce(func.sum(func.abs(StockMovement.delta)), 0),
        func.coalesce(func.sum(func.abs(StockMovement.delta) * StockMovement.price_at), 0),
    ).where(StockMovement.shop_id == shop_id, StockMovement.type == movement_type)
    if since is not None:
        stmt = stmt.where(StockMovement.created_at >= since)

    row = (await session.execute(stmt)).one()
    count, units, revenue = row
    return count, units, _to_decimal(revenue)


async def _reason_counts(
    session: AsyncSession,
    shop_id: int,
    movement_type: MovementType,
    since: datetime | None,
) -> list[dict]:
    """GROUP BY reason — портативний агрегат (без дато-функцій, що різняться
    між Postgres/SQLite), тож лишається в SQL. Порівняння типу — через
    ORM-mapped MovementType, не голий рядок (Postgres-інцидент з enum)."""
    stmt = (
        select(StockMovement.reason, func.count(StockMovement.id))
        .where(
            StockMovement.shop_id == shop_id,
            StockMovement.type == movement_type,
            StockMovement.reason.isnot(None),
        )
        .group_by(StockMovement.reason)
        .order_by(func.count(StockMovement.id).desc())
    )
    if since is not None:
        stmt = stmt.where(StockMovement.created_at >= since)

    rows = (await session.execute(stmt)).all()
    return [{"reason": reason, "count": count} for reason, count in rows]


async def _top_products(
    session: AsyncSession, shop_id: int, since: datetime | None
) -> list[dict]:
    """Топ-5 товарів за виторгом. GROUP BY product_id — портативний агрегат,
    лишається в SQL (той самий довід, що й для _reason_counts)."""
    revenue_expr = func.coalesce(
        func.sum(func.abs(StockMovement.delta) * StockMovement.price_at), 0
    )
    units_expr = func.coalesce(func.sum(func.abs(StockMovement.delta)), 0)

    stmt = (
        select(Product.id, Product.name, revenue_expr, units_expr)
        .select_from(StockMovement)
        .join(Variant, Variant.id == StockMovement.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .where(StockMovement.shop_id == shop_id, StockMovement.type == MovementType.sale)
        .group_by(Product.id, Product.name)
        .order_by(revenue_expr.desc())
        .limit(_TOP_PRODUCTS_LIMIT)
    )
    if since is not None:
        stmt = stmt.where(StockMovement.created_at >= since)

    rows = (await session.execute(stmt)).all()
    return [
        {
            "product_id": product_id,
            "name": name,
            "revenue_uah": str(_to_decimal(revenue).quantize(Decimal("0.01"))),
            "units": units,
        }
        for product_id, name, revenue, units in rows
    ]


async def _revenue_chart(
    session: AsyncSession, shop_id: int, since: datetime | None, granularity: Literal["day", "month"]
) -> list[dict]:
    """Групування по датах — єдине місце, де date_trunc (Postgres) і strftime
    (SQLite) розходяться, тож бакетинг навмисно в Python, а не в SQL."""
    stmt = select(StockMovement.created_at, StockMovement.delta, StockMovement.price_at).where(
        StockMovement.shop_id == shop_id, StockMovement.type == MovementType.sale
    )
    if since is not None:
        stmt = stmt.where(StockMovement.created_at >= since)

    rows = (await session.execute(stmt)).all()

    buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m"
    for created_at, delta, price_at in rows:
        if price_at is None:
            continue
        key = created_at.strftime(fmt)
        buckets[key] += abs(delta) * price_at

    return [
        {"date": key, "revenue": str(value.quantize(Decimal("0.01")))}
        for key, value in sorted(buckets.items())
    ]


@router.get("/summary")
async def finance_summary(
    period: Period = "all",
    membership: Membership = require_permission("can_view_finance"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Дохід = агрегат StockMovement, не окрема таблиця — один журнал і для
    складу, і для каси. sale -> дохід, ret -> віднімається (ret поки нічим
    не пишеться грошима, price_at=None — формула вже готова, коли з'явиться)."""
    since = _period_since(period)
    granularity: Literal["day", "month"] = "day" if period in ("week", "month") else "month"

    sales_count, units_sold, sales_revenue = await _movement_totals(
        session, membership.shop_id, MovementType.sale, since
    )
    returns_count, _, returns_revenue = await _movement_totals(
        session, membership.shop_id, MovementType.ret, since
    )

    revenue = sales_revenue - returns_revenue

    return {
        "shop_id": membership.shop_id,
        "revenue_uah": str(revenue.quantize(Decimal("0.01"))),
        "sales_count": sales_count,
        "units_sold": units_sold,
        "returns_uah": str(returns_revenue.quantize(Decimal("0.01"))),
        "returns_count": returns_count,
        "chart": await _revenue_chart(session, membership.shop_id, since, granularity),
        "top_products": await _top_products(session, membership.shop_id, since),
        "release_reasons": await _reason_counts(
            session, membership.shop_id, MovementType.release, since
        ),
        "return_reasons": await _reason_counts(
            session, membership.shop_id, MovementType.ret, since
        ),
    }
