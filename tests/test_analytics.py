"""
Owner-only зведення продажів/виручки (`GET /api/analytics/summary`).

Criteria:
  1. owner отримує summary; manager -> 403
  2. units_sold/revenue коректні: точний знімок OrderItem.price_at_order,
     коли рух прив'язаний до замовлення; variant.price (наближення) —
     коли order_id відсутній (ручний резерв/sell_direct)
  3. фільтр періоду (today/7d/30d/all): продаж поза вікном не враховується
  4. тенантна ізоляція: продажі магазину B не потрапляють у summary А
  5. порожній магазин -> нулі, порожній top_products
  6. top_products обрізається до 5, сортується за units_sold
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app import db
from app.models import (
    MemberRole,
    Membership,
    MovementType,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Product,
    StockMovement,
    Variant,
    utcnow,
)
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(shop_id: int, on_hand: int = 50, price: str = "100", name: str = "Товар") -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name=name)
        session.add(product)
        await session.flush()

        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal(price),
            on_hand=on_hand,
        )
        session.add(variant)
        await session.commit()
        return variant.id


async def _seed_sale(
    shop_id: int,
    variant_id: int,
    qty: int,
    *,
    order_id: int | None = None,
    created_at: datetime | None = None,
) -> None:
    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
        assert variant is not None
        variant.on_hand -= qty

        movement = StockMovement(
            shop_id=shop_id,
            variant_id=variant_id,
            order_id=order_id,
            type=MovementType.sale,
            delta=-qty,
        )
        if created_at is not None:
            movement.created_at = created_at
        session.add(movement)
        await session.commit()


async def _make_order_with_item(shop_id: int, variant_id: int, qty: int, price: str) -> int:
    async with db.async_session() as session:
        order = Order(
            shop_id=shop_id,
            source=OrderSource.website,
            status=OrderStatus.fulfilled,
            total=Decimal(price) * qty,
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                variant_id=variant_id,
                qty=qty,
                price_at_order=Decimal(price),
            )
        )
        await session.commit()
        return order.id


@pytest.mark.asyncio
async def test_owner_gets_summary_manager_forbidden(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, 41001, "Власник")

    manager_tg_id = 41002
    manager_init = make_init_data(manager_tg_id, first_name="Менеджер")
    # створюємо membership напряму — той самий приклад, що в test_stage1.py
    async with db.async_session() as session:
        session.add(Membership(shop_id=shop_id, tg_id=manager_tg_id, role=MemberRole.manager))
        await session.commit()

    r_owner = await client.get("/api/analytics/summary", headers={HEADER: owner_init})
    assert r_owner.status_code == 200, r_owner.text
    assert r_owner.json()["period"] == "7d"

    r_manager = await client.get("/api/analytics/summary", headers={HEADER: manager_init})
    assert r_manager.status_code == 403


@pytest.mark.asyncio
async def test_revenue_uses_order_item_price_snapshot_when_available(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 41010)
    # Поточна ціна варіанта (100) відрізняється від ціни на момент продажу
    # (80) — щоб довести, що рахується саме знімок, а не поточна ціна.
    variant_id = await _add_variant(shop_id, price="100")
    order_id = await _make_order_with_item(shop_id, variant_id, qty=3, price="80")
    await _seed_sale(shop_id, variant_id, qty=3, order_id=order_id)

    r = await client.get("/api/analytics/summary?period=all", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["units_sold"] == 3
    assert Decimal(body["revenue"]) == Decimal("240")  # 3 * 80, не 3 * 100
    assert body["sales_count"] == 1


@pytest.mark.asyncio
async def test_revenue_falls_back_to_variant_price_without_order(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 41020)
    variant_id = await _add_variant(shop_id, price="50")
    await _seed_sale(shop_id, variant_id, qty=4, order_id=None)  # ручний резерв -> fulfill

    r = await client.get("/api/analytics/summary?period=all", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["units_sold"] == 4
    assert Decimal(body["revenue"]) == Decimal("200")  # 4 * 50 (поточна ціна, наближення)


@pytest.mark.asyncio
async def test_period_filter_excludes_sales_outside_window(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 41030)
    variant_id = await _add_variant(shop_id, price="10")

    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Контрольні точки за межами today_start (а не "N годин тому") — інакше
    # тест мав би шанс зафлакати, якщо запуститься одразу після півночі UTC.
    await _seed_sale(shop_id, variant_id, qty=1, created_at=today_start + timedelta(minutes=1))  # сьогодні
    await _seed_sale(shop_id, variant_id, qty=2, created_at=now - timedelta(days=1))  # в межах 7d, не "today"
    await _seed_sale(shop_id, variant_id, qty=4, created_at=now - timedelta(days=10))  # в межах 30d, не 7d
    await _seed_sale(shop_id, variant_id, qty=8, created_at=now - timedelta(days=40))  # лише "all"

    r_today = await client.get("/api/analytics/summary?period=today", headers={HEADER: init_data})
    assert r_today.json()["units_sold"] == 1

    r_7d = await client.get("/api/analytics/summary?period=7d", headers={HEADER: init_data})
    assert r_7d.json()["units_sold"] == 1 + 2

    r_30d = await client.get("/api/analytics/summary?period=30d", headers={HEADER: init_data})
    assert r_30d.json()["units_sold"] == 1 + 2 + 4

    r_all = await client.get("/api/analytics/summary?period=all", headers={HEADER: init_data})
    assert r_all.json()["units_sold"] == 1 + 2 + 4 + 8


@pytest.mark.asyncio
async def test_tenant_isolation_shop_b_sales_not_in_shop_a_summary(client: AsyncClient) -> None:
    init_a, shop_a = await _bootstrap(client, 41040, "Шоп А")
    _init_b, shop_b = await _bootstrap(client, 41041, "Шоп Б")

    variant_a = await _add_variant(shop_a, price="10")
    variant_b = await _add_variant(shop_b, price="999")

    await _seed_sale(shop_a, variant_a, qty=2)
    await _seed_sale(shop_b, variant_b, qty=5)

    r = await client.get("/api/analytics/summary?period=all", headers={HEADER: init_a})
    body = r.json()
    assert body["units_sold"] == 2
    assert Decimal(body["revenue"]) == Decimal("20")


@pytest.mark.asyncio
async def test_empty_shop_returns_zeros_and_empty_top_products(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 41050)

    r = await client.get("/api/analytics/summary?period=all", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["units_sold"] == 0
    assert Decimal(body["revenue"]) == Decimal("0")
    assert body["sales_count"] == 0
    assert body["top_products"] == []


@pytest.mark.asyncio
async def test_top_products_capped_at_five_sorted_by_units_sold(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 41060)

    # 6 різних товарів із різною кількістю продажів — top_products має
    # лишити топ-5 за units_sold, найбільший першим.
    for index, units in enumerate([1, 2, 3, 4, 5, 6]):
        variant_id = await _add_variant(shop_id, price="10", name=f"Товар-{index}")
        await _seed_sale(shop_id, variant_id, qty=units)

    r = await client.get("/api/analytics/summary?period=all", headers={HEADER: init_data})
    body = r.json()
    top = body["top_products"]
    assert len(top) == 5
    assert [item["units_sold"] for item in top] == [6, 5, 4, 3, 2]
    assert body["units_sold"] == 1 + 2 + 3 + 4 + 5 + 6
