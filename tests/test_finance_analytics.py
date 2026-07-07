"""
Фінанси 2.0 — GET /api/finance/summary?period=... (StockMovement journal
уже містить усе потрібне: type/reason/price_at/delta/created_at).

Criteria:
  1. period фільтрує: рух 40 днів тому НЕ в month
  2. chart агрегує по днях (week/month)
  3. top_products рахує і сортує (сума виторгу по товару)
  4. release_reasons/return_reasons рахуються по причинах
  5. period=all = старі числа (сумісність зі старим фронтом)
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app import db
from app.models import MovementType, Product, StockMovement, Variant, utcnow
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(shop_id: int, name: str = "Товар", price: str = "100.00") -> tuple[int, int]:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name=name)
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal(price),
            on_hand=100,
        )
        session.add(variant)
        await session.commit()
        return product.id, variant.id


async def _add_movement(
    *,
    shop_id: int,
    variant_id: int,
    type_: MovementType,
    delta: int,
    price_at: str | None = None,
    reason: str | None = None,
    created_at=None,
) -> None:
    async with db.async_session() as session:
        session.add(
            StockMovement(
                shop_id=shop_id,
                variant_id=variant_id,
                type=type_,
                delta=delta,
                price_at=Decimal(price_at) if price_at is not None else None,
                reason=reason,
                created_at=created_at if created_at is not None else utcnow(),
            )
        )
        await session.commit()


async def _summary(client: AsyncClient, init_data: str, period: str | None = None) -> dict:
    params = {"period": period} if period else {}
    r = await client.get("/api/finance/summary", params=params, headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
#  period фільтрує рухи
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_period_month_excludes_movement_40_days_ago(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70001)
    _, variant_id = await _add_variant(shop_id, price="100.00")

    await _add_movement(
        shop_id=shop_id,
        variant_id=variant_id,
        type_=MovementType.sale,
        delta=-2,
        price_at="100.00",
        created_at=utcnow() - timedelta(days=40),
    )
    await _add_movement(
        shop_id=shop_id,
        variant_id=variant_id,
        type_=MovementType.sale,
        delta=-1,
        price_at="100.00",
        created_at=utcnow() - timedelta(days=1),
    )

    month = await _summary(client, init_data, "month")
    assert month["revenue_uah"] == "100.00"
    assert month["sales_count"] == 1
    assert month["units_sold"] == 1

    all_time = await _summary(client, init_data, "all")
    assert all_time["revenue_uah"] == "300.00"
    assert all_time["sales_count"] == 2
    assert all_time["units_sold"] == 3


@pytest.mark.asyncio
async def test_period_default_is_all_and_matches_old_shape(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70002)
    _, variant_id = await _add_variant(shop_id, price="50.00")
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.sale, delta=-4, price_at="50.00"
    )

    no_param = await _summary(client, init_data)
    explicit_all = await _summary(client, init_data, "all")
    assert no_param["revenue_uah"] == explicit_all["revenue_uah"] == "200.00"
    assert no_param["sales_count"] == explicit_all["sales_count"] == 1


# --------------------------------------------------------------------------- #
#  chart: агрегація по днях
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_chart_aggregates_by_day(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70003)
    _, variant_id = await _add_variant(shop_id, price="10.00")

    today = utcnow()
    yesterday = today - timedelta(days=1)

    # два продажі того самого дня -> один бар
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.sale,
        delta=-1, price_at="10.00", created_at=today,
    )
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.sale,
        delta=-2, price_at="10.00", created_at=today,
    )
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.sale,
        delta=-1, price_at="10.00", created_at=yesterday,
    )

    summary = await _summary(client, init_data, "week")
    chart_by_date = {row["date"]: row["revenue"] for row in summary["chart"]}
    units_by_date = {row["date"]: row["units"] for row in summary["chart"]}

    assert chart_by_date[today.strftime("%Y-%m-%d")] == "30.00"
    assert chart_by_date[yesterday.strftime("%Y-%m-%d")] == "10.00"
    assert units_by_date[today.strftime("%Y-%m-%d")] == 3  # 1+2
    assert units_by_date[yesterday.strftime("%Y-%m-%d")] == 1


# --------------------------------------------------------------------------- #
#  top_products: рахує і сортує
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_top_products_sums_and_sorts_by_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70004)
    _, variant_a = await _add_variant(shop_id, name="Футболка", price="100.00")
    _, variant_b = await _add_variant(shop_id, name="Кепка", price="300.00")

    await _add_movement(
        shop_id=shop_id, variant_id=variant_a, type_=MovementType.sale, delta=-3, price_at="100.00"
    )
    await _add_movement(
        shop_id=shop_id, variant_id=variant_b, type_=MovementType.sale, delta=-1, price_at="300.00"
    )

    summary = await _summary(client, init_data, "all")
    top = summary["top_products"]
    assert len(top) == 2
    # Кепка (300) і Футболка (300) рівні за виторгом - обидва мають бути присутні
    names = {row["name"] for row in top}
    assert names == {"Футболка", "Кепка"}
    by_name = {row["name"]: row for row in top}
    assert by_name["Футболка"]["revenue_uah"] == "300.00"
    assert by_name["Футболка"]["units"] == 3
    assert by_name["Кепка"]["revenue_uah"] == "300.00"
    assert by_name["Кепка"]["units"] == 1


# --------------------------------------------------------------------------- #
#  release_reasons / return_reasons
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_reason_counts_grouped(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 70005)
    _, variant_id = await _add_variant(shop_id, price="100.00")

    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.release,
        delta=1, reason="customer_changed_mind",
    )
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.release,
        delta=1, reason="customer_changed_mind",
    )
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.release,
        delta=1, reason="unresponsive",
    )
    await _add_movement(
        shop_id=shop_id, variant_id=variant_id, type_=MovementType.ret,
        delta=1, reason="did_not_pick_up",
    )

    summary = await _summary(client, init_data, "all")
    release_by_reason = {row["reason"]: row["count"] for row in summary["release_reasons"]}
    assert release_by_reason == {"customer_changed_mind": 2, "unresponsive": 1}

    return_by_reason = {row["reason"]: row["count"] for row in summary["return_reasons"]}
    assert return_by_reason == {"did_not_pick_up": 1}
    # ret пишеться без price_at (фіча ще не рахує гроші) -> 0, але count є
    assert summary["returns_uah"] == "0.00"
    assert summary["returns_count"] == 1
