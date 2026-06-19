"""
SkladBase — фінансова аналітика магазину (Стадія: owner-only summary).

Тільки читання: жодних записів, жодного виклику `inventory.py`.

Джерело істини (див. DECISIONS.md):
  * «Продано» — рухи складу `StockMovement.type == MovementType.sale`.
    Цей тип пишеться і з `inventory.fulfill` (резерв -> продаж), і з
    `inventory.sell_direct` (прямий продаж без резерву) — це єдиний і
    повний перелік продажних подій (CLAUDE.md, інваріант №3: лише
    `inventory.py` змінює залишок і завжди пише `StockMovement`).
  * «Виручка» — `StockMovement` зберігає лише `delta` (кількість), без
    ціни/суми. Коли рух прив'язаний до замовлення (`order_id` не NULL —
    `website`/`app` замовлення через `services/orders.py`), беремо точний
    знімок `OrderItem.price_at_order` для пари (order_id, variant_id).
    Коли `order_id` NULL (ручний резерв «Відклади» -> fulfill, або
    `sell_direct` без замовлення) — точного знімка ціни немає, наближаємо
    `variant.price` (ПОТОЧНА ціна; могла змінитись після факту продажу).
    Обмеження навмисне — схему БД у цьому кроці не змінюємо.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MovementType, OrderItem, Product, StockMovement, Variant, utcnow

PERIODS = ("today", "7d", "30d", "all")


@dataclass
class ProductSales:
    product_id: int
    name: str
    units_sold: int = 0
    revenue: Decimal = Decimal("0")


@dataclass
class AnalyticsSummary:
    period: str
    units_sold: int = 0
    revenue: Decimal = Decimal("0")
    sales_count: int = 0
    top_products: list[ProductSales] = field(default_factory=list)


def _period_start(period: str) -> datetime | None:
    """`None` означає «без нижньої межі» (period=all)."""
    now = utcnow()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "all":
        return None
    raise ValueError(f"Невідомий період: {period!r}")


async def get_summary(session: AsyncSession, *, shop_id: int, period: str) -> AnalyticsSummary:
    since = _period_start(period)

    query = (
        select(StockMovement, Variant.price, Variant.product_id, Product.name)
        .join(Variant, Variant.id == StockMovement.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .where(StockMovement.shop_id == shop_id, StockMovement.type == MovementType.sale)
    )
    if since is not None:
        query = query.where(StockMovement.created_at >= since)

    rows = (await session.execute(query)).all()

    # Точний знімок ціни лише для рухів, прив'язаних до замовлення:
    # (order_id, variant_id) -> price_at_order. Один запит замість N+1.
    order_ids = {movement.order_id for movement, *_ in rows if movement.order_id is not None}
    price_at_order: dict[tuple[int, int], Decimal] = {}
    if order_ids:
        item_rows = (
            await session.execute(
                select(OrderItem.order_id, OrderItem.variant_id, OrderItem.price_at_order).where(
                    OrderItem.order_id.in_(order_ids)
                )
            )
        ).all()
        for order_id, variant_id, price in item_rows:
            price_at_order[(order_id, variant_id)] = price

    summary = AnalyticsSummary(period=period)
    per_product: dict[int, ProductSales] = {}

    for movement, variant_price, product_id, product_name in rows:
        qty = -movement.delta  # delta завжди від'ємне для type=sale
        if movement.order_id is not None:
            unit_price = price_at_order.get((movement.order_id, movement.variant_id), variant_price)
        else:
            unit_price = variant_price
        line_revenue = unit_price * qty

        summary.units_sold += qty
        summary.revenue += line_revenue
        summary.sales_count += 1

        entry = per_product.get(product_id)
        if entry is None:
            entry = ProductSales(product_id=product_id, name=product_name)
            per_product[product_id] = entry
        entry.units_sold += qty
        entry.revenue += line_revenue

    summary.top_products = sorted(
        per_product.values(), key=lambda p: p.units_sold, reverse=True
    )[:5]
    return summary
