"""
Фіча B1 — крон-трекінг shipped-резервів через Нова Пошта (app/tasks.py::np_tracking).

track() підмінюється фейковою функцією (як wfp_provider у charge_due_card_subscriptions,
tests/test_stage6.py) — живий НП API не викликаємо.

Criteria:
  1. StatusCode у PICKED_CODES (9) -> pick_up: fulfilled, sale-рух, дохід зріс, notify
  2. StatusCode у RETURNED_CODES (103) -> not_picked_up: released, on_hand повернувся,
     дохід НЕ змінився, notify
  3. невідомий код -> np_status записаний, статус резерву НЕ змінився
  4. поганий ключ/збій одного магазину -> другий магазин все одно оброблений
  5. 409 від pick_up (вже оброблено вручну паралельно) -> тихий скіп, без падіння
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import db, tasks
from app.models import (
    Product,
    Reservation,
    ReservationSource,
    ReservationStatus,
    Shop,
    Variant,
)
from app.security.crypto import encrypt
from app.services import inventory
from app.services.inventory import InventoryError
from app.services.novaposhta import NovaPoshtaError
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


class _StubNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def __call__(self, tg_id: int, text: str) -> None:
        self.calls.append((tg_id, text))


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _set_np_key(shop_id: int, plaintext_key: str) -> None:
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        shop.np_api_key_encrypted = encrypt(plaintext_key)
        await session.commit()


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


async def _reserve_and_ship(shop_id: int, variant_id: int, ttn: str, qty: int = 2) -> int:
    async with db.async_session() as session:
        reservation = await inventory.reserve(
            session,
            shop_id=shop_id,
            variant_id=variant_id,
            qty=qty,
            source=ReservationSource.manual,
            commit=False,
        )
        await session.flush()
        reservation_id = reservation.id
        await session.commit()

    async with db.async_session() as session:
        await inventory.ship(session, shop_id=shop_id, reservation_id=reservation_id, ttn=ttn)

    return reservation_id


async def _finance_summary(client: AsyncClient, init_data: str) -> dict:
    r = await client.get("/api/finance/summary", headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    return r.json()


async def _get_reservation(reservation_id: int) -> Reservation:
    async with db.async_session() as session:
        reservation = await session.get(Reservation, reservation_id)
    assert reservation is not None
    return reservation


async def _get_variant(variant_id: int) -> Variant:
    async with db.async_session() as session:
        variant = await session.get(Variant, variant_id)
    assert variant is not None
    return variant


def _make_track(responses: dict[str, list[dict] | Exception]):
    async def _track(api_key: str, ttns: list[str]) -> list[dict]:
        resp = responses.get(api_key, [])
        if isinstance(resp, Exception):
            raise resp
        return resp

    return _track


@pytest.mark.asyncio
async def test_picked_status_triggers_pick_up_and_grows_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 91001)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")
    await _set_np_key(shop_id, "np-key-1")
    reservation_id = await _reserve_and_ship(shop_id, variant_id, ttn="20450000000001", qty=2)

    before = await _finance_summary(client, init_data)
    assert before["revenue_uah"] == "0.00"

    track = _make_track(
        {"np-key-1": [{"Number": "20450000000001", "StatusCode": 9, "Status": "Відправлення отримано"}]}
    )
    notifier = _StubNotifier()

    async with db.async_session() as session:
        processed = await tasks.np_tracking(session, notifier, track)
    assert processed == 1

    reservation = await _get_reservation(reservation_id)
    assert reservation.status == ReservationStatus.fulfilled

    after = await _finance_summary(client, init_data)
    assert after["revenue_uah"] == "300.00"  # 2 * 150

    assert len(notifier.calls) == 1
    _tg_id, text = notifier.calls[0]
    assert "20450000000001" in text
    assert "300" in text


@pytest.mark.asyncio
async def test_returned_status_triggers_not_picked_up_without_revenue(client: AsyncClient) -> None:
    init_data, shop_id = await _bootstrap(client, 91002)
    variant_id = await _add_variant(shop_id, on_hand=10, price="150.00")
    await _set_np_key(shop_id, "np-key-2")
    reservation_id = await _reserve_and_ship(shop_id, variant_id, ttn="20450000000002", qty=2)

    variant_after_ship = await _get_variant(variant_id)
    assert variant_after_ship.on_hand == 8

    track = _make_track(
        {"np-key-2": [{"Number": "20450000000002", "StatusCode": 103, "Status": "Відмова одержувача"}]}
    )
    notifier = _StubNotifier()

    async with db.async_session() as session:
        processed = await tasks.np_tracking(session, notifier, track)
    assert processed == 1

    reservation = await _get_reservation(reservation_id)
    assert reservation.status == ReservationStatus.released

    variant = await _get_variant(variant_id)
    assert variant.on_hand == 10  # повернулось рівно те, що зняв ship()
    assert variant.reserved == 0

    summary = await _finance_summary(client, init_data)
    assert summary["revenue_uah"] == "0.00"

    assert len(notifier.calls) == 1
    assert "20450000000002" in notifier.calls[0][1]


@pytest.mark.asyncio
async def test_unknown_status_code_only_saves_np_status(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, 91003)
    variant_id = await _add_variant(shop_id, on_hand=10)
    await _set_np_key(shop_id, "np-key-3")
    reservation_id = await _reserve_and_ship(shop_id, variant_id, ttn="20450000000003", qty=1)

    track = _make_track(
        {"np-key-3": [{"Number": "20450000000003", "StatusCode": 6, "Status": "У дорозі"}]}
    )
    notifier = _StubNotifier()

    async with db.async_session() as session:
        processed = await tasks.np_tracking(session, notifier, track)
    assert processed == 0

    reservation = await _get_reservation(reservation_id)
    assert reservation.status == ReservationStatus.shipped
    assert reservation.np_status == "У дорозі"
    assert notifier.calls == []


@pytest.mark.asyncio
async def test_bad_key_shop_does_not_block_other_shops(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 91004, "Магазин А")
    variant_a = await _add_variant(shop_a, on_hand=10, price="100.00")
    await _set_np_key(shop_a, "np-key-bad")
    await _reserve_and_ship(shop_a, variant_a, ttn="20450000000004", qty=1)

    _init_b, shop_b = await _bootstrap(client, 91005, "Магазин Б")
    variant_b = await _add_variant(shop_b, on_hand=10, price="100.00")
    await _set_np_key(shop_b, "np-key-good")
    reservation_b = await _reserve_and_ship(shop_b, variant_b, ttn="20450000000005", qty=1)

    track = _make_track(
        {
            "np-key-bad": NovaPoshtaError("НП API недоступний"),
            "np-key-good": [
                {"Number": "20450000000005", "StatusCode": 9, "Status": "Відправлення отримано"}
            ],
        }
    )
    notifier = _StubNotifier()

    async with db.async_session() as session:
        processed = await tasks.np_tracking(session, notifier, track)
    assert processed == 1  # тільки магазин Б

    reservation = await _get_reservation(reservation_b)
    assert reservation.status == ReservationStatus.fulfilled


@pytest.mark.asyncio
async def test_already_processed_reservation_is_skipped_without_crash(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_data, shop_id = await _bootstrap(client, 91006)
    variant_id = await _add_variant(shop_id, on_hand=10, price="100.00")
    await _set_np_key(shop_id, "np-key-6")
    already_done_id = await _reserve_and_ship(shop_id, variant_id, ttn="20450000000006", qty=1)
    still_open_id = await _reserve_and_ship(shop_id, variant_id, ttn="20450000000007", qty=1)

    real_pick_up = inventory.pick_up

    async def _pick_up_conflicting_first(
        session: AsyncSession, *, shop_id: int, reservation_id: int, commit: bool = True
    ) -> Reservation:
        if reservation_id == already_done_id:
            raise InventoryError(409, "Резерв не активний")
        return await real_pick_up(session, shop_id=shop_id, reservation_id=reservation_id, commit=commit)

    monkeypatch.setattr(inventory, "pick_up", _pick_up_conflicting_first)

    track = _make_track(
        {
            "np-key-6": [
                {"Number": "20450000000006", "StatusCode": 9, "Status": "Відправлення отримано"},
                {"Number": "20450000000007", "StatusCode": 9, "Status": "Відправлення отримано"},
            ]
        }
    )
    notifier = _StubNotifier()

    async with db.async_session() as session:
        processed = await tasks.np_tracking(session, notifier, track)
    assert processed == 1  # лише still_open_id

    conflicting = await _get_reservation(already_done_id)
    assert conflicting.status == ReservationStatus.shipped  # не займали далі

    resolved = await _get_reservation(still_open_id)
    assert resolved.status == ReservationStatus.fulfilled
