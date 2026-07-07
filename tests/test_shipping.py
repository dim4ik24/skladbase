"""
Фіча A — відправки резерву (ship/pick_up/not_picked_up, ТТН).

Модель грошей: дохід нараховується ТІЛЬКИ при "Забрав" (pick_up, як і fulfill) —
sale-рух + price_at. Незабір (not_picked_up) повертає товар на склад БЕЗ
грошового руху (type=ret, price_at=None), доходу не було — нема що віднімати.

Модель складу: ship() знімає on_hand І reserved ОДРАЗУ (товар фізично поїхав,
earmark більше не потрібен) — тому pick_up() далі нічого зі складом не робить
(лише фіксує продаж), а not_picked_up() повертає on_hand назад (без подвійного
плюсу — рівно те, що зняв ship()).

Criteria:
  1. ship: active -> shipped, ttn/shipped_at записані, on_hand/reserved зняті
  2. ship на вже shipped -> 409
  3. pick_up: shipped -> fulfilled, sale-рух з price_at, дохід зростає
  4. not_picked_up: shipped -> released, ret-рух БЕЗ price_at, on_hand
     повертається до вихідного (без подвійного плюсу), дохід НЕ змінюється
  5. release на shipped -> 409 (лише active/shipped-специфічні переходи)
  6. cron release_expired_reservations не чіпає shipped
  7. PATCH ttn на shipped
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db, tasks
from app.models import (
    MemberRole,
    Membership,
    MovementType,
    Product,
    Reservation,
    ReservationSource,
    ReservationStatus,
    Shop,
    StockMovement,
    Variant,
    utcnow,
)
from app.services import inventory
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


async def _reserve(client: AsyncClient, init_data: str, variant_id: int, qty: int = 2) -> int:
    r = await client.post(
        f"/api/variants/{variant_id}/reserve", json={"qty": qty}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _finance_summary(client: AsyncClient, init_data: str) -> dict:
    r = await client.get("/api/finance/summary", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    return r.json()


async def _get_variant(variant_id: int) -> Variant:
    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    return variant


async def _get_reservation(reservation_id: int) -> Reservation:
    async with db.async_session() as session:
        reservation = await session.get(Reservation, reservation_id)
    assert reservation is not None
    return reservation


async def _last_movement(variant_id: int, type_: MovementType) -> StockMovement:
    async with db.async_session() as session:
        movement = await session.scalar(
            select(StockMovement)
            .where(StockMovement.variant_id == variant_id, StockMovement.type == type_)
            .order_by(StockMovement.id.desc())
        )
    assert movement is not None
    return movement


# --------------------------------------------------------------------------- #
#  ship
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ship_moves_active_to_shipped_and_records_ttn(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80001)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=2)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship",
        json={"ttn": "20450123456789"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "shipped"
    assert body["ttn"] == "20450123456789"
    assert body["shipped_at"] is not None

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 8  # знято одразу разом з reserved
    assert variant.reserved == 0
    assert variant.available == 8


@pytest.mark.asyncio
async def test_ship_without_ttn_is_optional(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80002)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    assert r.json()["ttn"] is None
    assert r.json()["status"] == "shipped"


@pytest.mark.asyncio
async def test_ship_on_already_shipped_reservation_returns_409(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80003)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r2.status_code == 409


# --------------------------------------------------------------------------- #
#  PATCH ttn
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_patch_ttn_updates_shipped_reservation(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80004)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    r2 = await client.patch(
        f"/api/reservations/{reservation_id}/ttn",
        json={"ttn": "20450000000000"},
        headers={HEADER: init_data},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["ttn"] == "20450000000000"


@pytest.mark.asyncio
async def test_patch_ttn_on_active_reservation_returns_409(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80005)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.patch(
        f"/api/reservations/{reservation_id}/ttn",
        json={"ttn": "20450000000000"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  ТТН — формат Нової Пошти (14 цифр, "20"/"59")
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_ttn",
    [
        "2045012345678",  # 13 цифр
        "204501234567890",  # 15 цифр
        "2045012345678a",  # містить літеру
        "10450123456789",  # невалідний префікс
    ],
)
async def test_ship_with_invalid_ttn_returns_422(client: AsyncClient, bad_ttn: str) -> None:
    init_data, shop_id = await _bootstrap(client, 80013)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship",
        json={"ttn": bad_ttn},
        headers={HEADER: init_data},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_ttn_with_invalid_format_returns_422(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80014)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    r2 = await client.patch(
        f"/api/reservations/{reservation_id}/ttn",
        json={"ttn": "not-a-ttn-1234"},
        headers={HEADER: init_data},
    )
    assert r2.status_code == 422


# --------------------------------------------------------------------------- #
#  pick_up -> дохід
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pick_up_fulfills_and_grows_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80006)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")
    reservation_id = await _reserve(client, init_data, variant_id, qty=2)

    before = await _finance_summary(client, init_data)
    assert before["revenue_uah"] == "0.00"

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/pick-up", headers={HEADER: init_data}
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "fulfilled"

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 8  # знято на ship(), pick_up вдруге не чіпає
    assert variant.reserved == 0

    movement = await _last_movement(variant_id, MovementType.sale)
    assert movement.delta == -2
    assert movement.price_at == Decimal("150.00")

    after = await _finance_summary(client, init_data)
    assert after["revenue_uah"] == "300.00"  # 2 * 150


@pytest.mark.asyncio
async def test_pick_up_without_shipping_returns_409(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80007)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/pick-up", headers={HEADER: init_data}
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  not_picked_up -> товар на склад, без доходу
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_not_picked_up_returns_stock_without_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80008)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")
    reservation_id = await _reserve(client, init_data, variant_id, qty=2)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    variant_after_ship = await _get_variant(variant_id)
    assert variant_after_ship.on_hand == 8

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/not-picked-up",
        json={"reason": "did_not_pick_up"},
        headers={HEADER: init_data},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "released"

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 10  # рівно як було ДО reserve — без подвійного плюсу
    assert variant.reserved == 0
    assert variant.available == 10

    movement = await _last_movement(variant_id, MovementType.ret)
    assert movement.delta == 2
    assert movement.price_at is None
    assert movement.reason == "did_not_pick_up"

    summary = await _finance_summary(client, init_data)
    assert summary["revenue_uah"] == "0.00"  # доходу не було - нема що віднімати


@pytest.mark.asyncio
async def test_not_picked_up_other_without_comment_returns_422(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80009)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/not-picked-up",
        json={"reason": "other"},
        headers={HEADER: init_data},
    )
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_not_picked_up_without_shipping_returns_409(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80010)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/not-picked-up",
        json={"reason": "did_not_pick_up"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  release на shipped -> 409 (лише pick_up/not_picked_up знімають shipped)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_release_on_shipped_reservation_returns_409(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 80011)
    variant_id = await _add_variant(shop_id, on_hand=10)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/ship", headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text

    r2 = await client.post(
        f"/api/reservations/{reservation_id}/release", headers={HEADER: init_data}
    )
    assert r2.status_code == 409


# --------------------------------------------------------------------------- #
#  cron release_expired_reservations не чіпає shipped
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cron_release_expired_reservations_ignores_shipped() -> None:
    async with db.async_session() as session:
        shop = Shop(owner_tg_id=80012, name="Тест", slug=f"shop-{uuid4().hex[:8]}")
        session.add(shop)
        await session.flush()
        session.add(Membership(shop_id=shop.id, tg_id=80012, role=MemberRole.owner))
        product = Product(shop_id=shop.id, name="Товар")
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop.id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal("10"),
            on_hand=10,
        )
        session.add(variant)
        await session.flush()
        shop_id, variant_id = shop.id, variant.id

        reservation = await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=2,
            source=ReservationSource.manual,
            commit=False,
        )
        await session.flush()
        reservation_id = reservation.id
        await session.commit()

    async with db.async_session() as session:
        await inventory.ship(session, shop_id=shop_id, reservation_id=reservation_id)

    async with db.async_session() as session:
        stored = await session.get(Reservation, reservation_id)
        assert stored is not None
        stored.expires_at = utcnow() - timedelta(hours=1)
        await session.commit()

    async with db.async_session() as session:
        count = await tasks.release_expired_reservations(session)
    assert count == 0  # cron фільтрує тільки status=active, shipped не чіпає

    reservation = await _get_reservation(reservation_id)
    assert reservation.status == ReservationStatus.shipped
