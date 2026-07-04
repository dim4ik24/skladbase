from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_permission
from app.models import Membership, MovementType, StockMovement

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _to_decimal(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


async def _movement_totals(
    session: AsyncSession, shop_id: int, movement_type: MovementType
) -> tuple[int, int, Decimal]:
    """(кількість рухів, сума |delta|, сума |delta| * price_at) для одного типу.

    price_at може бути NULL для рухів, записаних до цієї фічі (стара БД) —
    SUM ігнорує NULL-доданки, тож такі рухи просто не додають доходу, а не
    ламають запит."""
    row = (
        await session.execute(
            select(
                func.count(StockMovement.id),
                func.coalesce(func.sum(func.abs(StockMovement.delta)), 0),
                func.coalesce(func.sum(func.abs(StockMovement.delta) * StockMovement.price_at), 0),
            ).where(StockMovement.shop_id == shop_id, StockMovement.type == movement_type)
        )
    ).one()
    count, units, revenue = row
    return count, units, _to_decimal(revenue)


@router.get("/summary")
async def finance_summary(
    membership: Membership = require_permission("can_view_finance"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Дохід = агрегат StockMovement, не окрема таблиця — один журнал і для
    складу, і для каси. sale -> дохід, ret -> віднімається (ret поки нічим
    не пишеться, фіча A; формула вже готова до неї)."""
    sales_count, units_sold, sales_revenue = await _movement_totals(
        session, membership.shop_id, MovementType.sale
    )
    _, _, returns_revenue = await _movement_totals(session, membership.shop_id, MovementType.ret)

    revenue = sales_revenue - returns_revenue

    return {
        "shop_id": membership.shop_id,
        "revenue_uah": str(revenue.quantize(Decimal("0.01"))),
        "sales_count": sales_count,
        "units_sold": units_sold,
    }
