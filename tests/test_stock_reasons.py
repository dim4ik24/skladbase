"""
Списання з причинами + реальний облік доходу (StockMovement.reason/comment/
price_at, POST /api/variants/{id}/adjust переробленого під write_off,
GET /api/finance/summary).

Criteria:
  1. reason=sold -> StockMovement(type=sale, price_at=variant.price), дохід росте
  2. reason=defect/correction -> StockMovement(type=adjustment, price_at=None), дохід НЕ росте
  3. reason=other без comment -> 422
  4. qty > available -> 409 (окремо покрито в test_stage6b.py::test_write_off_more_than_available_is_rejected)
  5. fulfill резерву -> StockMovement(type=sale, price_at=variant.price), дохід росте
  6. /api/finance/summary коректно рахує 2 продажі різних цін
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db
from app.models import MovementType, Product, StockMovement, Variant
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(shop_id: int, on_hand: int = 10, price: str = "100.00") -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар")
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


async def _last_movement(variant_id: int) -> StockMovement:
    async with db.async_session() as session:
        movement = await session.scalar(
            select(StockMovement)
            .where(StockMovement.variant_id == variant_id)
            .order_by(StockMovement.id.desc())
        )
    assert movement is not None
    return movement


async def _finance_summary(client: AsyncClient, init_data: str) -> dict:
    r = await client.get("/api/finance/summary", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
#  write_off: reason=sold -> дохід                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_write_off_sold_creates_sale_movement_and_grows_revenue(
    client: AsyncClient,
) -> None:
    init_data, shop_id = await _bootstrap(client, 60001)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")

    before = await _finance_summary(client, init_data)
    assert before["revenue_uah"] == "0.00"

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"qty": 3, "reason": "sold"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert r.json()["on_hand"] == 7

    movement = await _last_movement(variant_id)
    assert movement.type == MovementType.sale
    assert movement.delta == -3
    assert movement.reason == "sold"
    assert movement.price_at == Decimal("150.00")

    after = await _finance_summary(client, init_data)
    assert after["revenue_uah"] == "450.00"  # 3 * 150
    assert after["sales_count"] == 1
    assert after["units_sold"] == 3


# --------------------------------------------------------------------------- #
#  write_off: defect/correction -> без грошей                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_write_off_defect_creates_adjustment_without_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 60002)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"qty": 2, "reason": "defect"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert r.json()["on_hand"] == 8

    movement = await _last_movement(variant_id)
    assert movement.type == MovementType.adjustment
    assert movement.reason == "defect"
    assert movement.price_at is None

    after = await _finance_summary(client, init_data)
    assert after["revenue_uah"] == "0.00"
    assert after["sales_count"] == 0


@pytest.mark.asyncio
async def test_write_off_correction_has_no_money_movement(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 60003)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"qty": 1, "reason": "correction", "comment": "інвентаризація"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    movement = await _last_movement(variant_id)
    assert movement.type == MovementType.adjustment
    assert movement.reason == "correction"
    assert movement.price_at is None
    assert movement.comment == "інвентаризація"

    after = await _finance_summary(client, init_data)
    assert after["revenue_uah"] == "0.00"


# --------------------------------------------------------------------------- #
#  write_off: reason=other вимагає comment                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_write_off_other_without_comment_returns_422(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 60004)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"qty": 1, "reason": "other"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 422

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    assert variant.on_hand == 10  # незмінено


@pytest.mark.asyncio
async def test_write_off_other_with_comment_succeeds(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 60005)
    variant_id = await _add_variant(shop_id, on_hand=10)

    r = await client.post(
        f"/api/variants/{variant_id}/adjust",
        json={"qty": 1, "reason": "other", "comment": "загубився при переїзді складу"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text

    movement = await _last_movement(variant_id)
    assert movement.reason == "other"
    assert movement.comment == "загубився при переїзді складу"


# --------------------------------------------------------------------------- #
#  fulfill резерву -> дохід (джерело #2)                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_fulfill_creates_sale_movement_with_price_and_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 60006)
    variant_id = await _add_variant(shop_id, on_hand=10, price="200.00")

    r_reserve = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": 2}, headers={HEADER: init_data}
    )
    assert r_reserve.status_code == 200, r_reserve.text
    reservation_id = r_reserve.json()["id"]

    r_fulfill = await client.post(
        f"/api/reservations/{reservation_id}/fulfill", headers={HEADER: init_data}
    )
    assert r_fulfill.status_code == 200, r_fulfill.text

    movement = await _last_movement(variant_id)
    assert movement.type == MovementType.sale
    assert movement.delta == -2
    assert movement.price_at == Decimal("200.00")
    assert movement.reason is None  # fulfill — нормальний продаж, не списання

    after = await _finance_summary(client, init_data)
    assert after["revenue_uah"] == "400.00"  # 2 * 200
    assert after["sales_count"] == 1
    assert after["units_sold"] == 2


# --------------------------------------------------------------------------- #
#  finance summary: кілька продажів різних цін                                #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_finance_summary_sums_two_different_priced_sales(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 60007)
    variant_a = await _add_variant(shop_id, on_hand=10, price="100.00")
    variant_b = await _add_variant(shop_id, on_hand=10, price="250.00")

    r_a = await client.post(
        f"/api/variants/{variant_a}/adjust",
        json={"qty": 2, "reason": "sold"},
        headers={HEADER: init_data},
    )
    assert r_a.status_code == 200, r_a.text

    r_b = await client.post(
        f"/api/variants/{variant_b}/adjust",
        json={"qty": 1, "reason": "sold"},
        headers={HEADER: init_data},
    )
    assert r_b.status_code == 200, r_b.text

    # список списаний (defect) не має впливати на суму
    r_defect = await client.post(
        f"/api/variants/{variant_a}/adjust",
        json={"qty": 1, "reason": "defect"},
        headers={HEADER: init_data},
    )
    assert r_defect.status_code == 200, r_defect.text

    summary = await _finance_summary(client, init_data)
    assert summary["revenue_uah"] == "450.00"  # 2*100 + 1*250
    assert summary["sales_count"] == 2
    assert summary["units_sold"] == 3
