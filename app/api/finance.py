from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_permission
from app.models import (
    Membership,
    MovementType,
    Product,
    Reservation,
    StockMovement,
    Variant,
    utcnow,
)

router = APIRouter(prefix="/api/finance", tags=["finance"])

Period = Literal["week", "month", "year", "all"]
_PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}
_TOP_PRODUCTS_LIMIT = 5
_HISTORY_LIMIT = 100
_HISTORY_TYPES = (MovementType.sale, MovementType.ret, MovementType.release)


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

    revenue_buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    units_buckets: dict[str, int] = defaultdict(int)
    fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m"
    for created_at, delta, price_at in rows:
        key = created_at.strftime(fmt)
        units_buckets[key] += abs(delta)
        if price_at is None:
            continue
        revenue_buckets[key] += abs(delta) * price_at

    return [
        {
            "date": key,
            "revenue": str(revenue_buckets[key].quantize(Decimal("0.01"))),
            "units": units_buckets[key],
        }
        for key in sorted(units_buckets)
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


def _variant_label(variant: Variant) -> str:
    return " / ".join(v for v in variant.axis_values.values() if v) or (variant.sku or "")


@router.get("/history")
async def finance_history(
    period: Period = "all",
    date: str | None = None,
    membership: Membership = require_permission("can_view_finance"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Стрічка подій каси/складу: продаж/повернення/зняття, DESC, ліміт 100.

    `date` (YYYY-MM-DD) звужує до ОДНОГО дня і ПЕРЕВАЖАЄ `period` (день
    вужчий за будь-який період) — саме так подвійний тап на денний стовпець
    графіка відкриває історію лише за цей день. customer/ttn — з резерву,
    ЯКЩО рух ним породжений (reservation_id, див. models.StockMovement);
    прямий продаж/списання (sell_direct/write_off) їх не має — і не мусить."""
    stmt = (
        select(StockMovement, Variant, Product, Reservation)
        .join(Variant, Variant.id == StockMovement.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .outerjoin(Reservation, Reservation.id == StockMovement.reservation_id)
        .where(
            StockMovement.shop_id == membership.shop_id,
            StockMovement.type.in_(_HISTORY_TYPES),
        )
        .order_by(StockMovement.created_at.desc())
        .limit(_HISTORY_LIMIT)
    )

    if date is not None:
        try:
            day_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise HTTPException(422, "date має бути у форматі YYYY-MM-DD") from exc
        day_end = day_start + timedelta(days=1)
        stmt = stmt.where(StockMovement.created_at >= day_start, StockMovement.created_at < day_end)
    else:
        since = _period_since(period)
        if since is not None:
            stmt = stmt.where(StockMovement.created_at >= since)

    rows = (await session.execute(stmt)).all()

    events = []
    for movement, variant, product, reservation in rows:
        amount = None
        if movement.price_at is not None:
            amount = str((abs(movement.delta) * movement.price_at).quantize(Decimal("0.01")))
        events.append({
            "id": movement.id,
            "date": movement.created_at.isoformat(),
            "type": movement.type.value,
            "product_name": product.name,
            "variant_label": _variant_label(variant),
            "qty": abs(movement.delta),
            "amount": amount,
            "reason": movement.reason,
            "customer": reservation.customer_note if reservation else None,
            "ttn": reservation.ttn if reservation else None,
        })
    return events
