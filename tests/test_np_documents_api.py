"""
Нова Пошта — створення накладної для резерву та довідники
(app/api/np_documents.py, services/np_shipping.py).

novaposhta.create_document підмінюється монкіпатчем на рівні
app.services.np_shipping (де воно імпортоване як ім'я) — той самий патерн,
що й np_module.ping у test_np_key_api.py. Сам 5-кроковий ланцюг НП-викликів
уже покритий tests/test_novaposhta.py, тут — лише оркестрація/гварди/API.

Criteria:
  1. happy path: ttn + status=shipped у резерві, delivery_cost у відповіді
  2. cod=false (дефолт) -> cod_amount=None передається в create_document
  3. cod=true -> cod_amount дефолт = сума резерву (price * qty)
  4. cod=true + явний cod_amount -> саме він, не дефолт
  5. weight/description дефолти (0.5, назва товару), і що явні значення їх перекривають
  6. помилка НП (NovaPoshtaError) -> 422 з текстом "НП: ...", резерв лишається active
  7. без даних відправника -> 422, до НП не доходить
  8. без підключеного ключа НП -> 422
  9. резерв не active -> 409, до НП не доходить
  10. GET/PUT /api/shop/np-sender round-trip
  11. /api/np/cities, /api/np/warehouses проксі (і 422 без ключа)
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app import db
from app.api import np as np_key_module
from app.api import np_documents as np_documents_module
from app.models import Product, Reservation, ReservationStatus, Variant
from app.services import np_shipping as np_shipping_module
from app.services.novaposhta import DocumentResult, NovaPoshtaError
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"

SENDER_PAYLOAD = {
    "city_ref": "sender-city-ref",
    "city_name": "Київ",
    "warehouse_ref": "sender-wh-ref",
    "warehouse_name": "Відділення №1",
    "phone": "380501112233",
    "name": "ФОП Іваненко",
}

RECIPIENT_PAYLOAD = {
    "recipient_name": "Петро Сидоренко",
    "recipient_phone": "380671112233",
    "recipient_city_ref": "rec-city-ref",
    "recipient_warehouse_ref": "rec-wh-ref",
}


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _add_variant(shop_id: int, name: str = "Футболка", price: str = "450.00") -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name=name)
        session.add(product)
        await session.flush()
        variant = Variant(
            shop_id=shop_id,
            product_id=product.id,
            sku=f"SKU-{uuid4().hex[:8]}",
            price=Decimal(price),
            on_hand=10,
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


async def _true() -> bool:
    return True


async def _connect_np_key(client: AsyncClient, init_data: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(np_key_module, "ping", lambda api_key: _true())
    r = await client.put(
        "/api/shop/np-key", json={"api_key": "np-live-key"}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text


async def _set_sender(client: AsyncClient, init_data: str, payload: dict | None = None) -> None:
    r = await client.put(
        "/api/shop/np-sender", json=payload or SENDER_PAYLOAD, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text


async def _get_reservation(reservation_id: int) -> Reservation:
    async with db.async_session() as session:
        reservation = await session.get(Reservation, reservation_id)
    assert reservation is not None
    return reservation


class _FakeCreateDocument:
    """Записує аргументи виклику create_document і повертає канонічний
    DocumentResult (або кидає задану помилку) — без живого НП API."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.result = DocumentResult(
            ttn="20450000000099", ref="doc-ref", cost=Decimal("75.00"), estimated_delivery="2026-07-07"
        )
        self.error: NovaPoshtaError | None = None

    async def __call__(self, api_key: str, **kwargs: object) -> DocumentResult:
        self.calls.append({"api_key": api_key, **kwargs})
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture()
def fake_create_document(monkeypatch: pytest.MonkeyPatch) -> _FakeCreateDocument:
    fake = _FakeCreateDocument()
    monkeypatch.setattr(np_shipping_module, "create_document", fake)
    return fake


# --------------------------------------------------------------------------- #
#  create-ttn: happy path + дефолти
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_ttn_happy_path_ships_reservation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91001)
    await _connect_np_key(client, init_data, monkeypatch)
    await _set_sender(client, init_data)
    variant_id = await _add_variant(shop_id, price="450.00")
    reservation_id = await _reserve(client, init_data, variant_id, qty=2)

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json=RECIPIENT_PAYLOAD,
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ttn": "20450000000099", "delivery_cost": "75.00"}

    reservation = await _get_reservation(reservation_id)
    assert reservation.status == ReservationStatus.shipped
    assert reservation.ttn == "20450000000099"

    call = fake_create_document.calls[0]
    assert call["sender_city_ref"] == "sender-city-ref"
    assert call["sender_warehouse_ref"] == "sender-wh-ref"
    assert call["sender_phone"] == "380501112233"
    assert call["recipient_city_ref"] == "rec-city-ref"
    assert call["weight"] == 0.5
    assert call["description"] == "Футболка"  # дефолт = назва товару
    assert call["cost"] == Decimal("900.00")  # 450 * 2 — сума резерву
    assert call["cod_amount"] is None  # cod дефолт False


@pytest.mark.asyncio
async def test_create_ttn_cod_defaults_amount_to_reservation_total(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91002)
    await _connect_np_key(client, init_data, monkeypatch)
    await _set_sender(client, init_data)
    variant_id = await _add_variant(shop_id, price="200.00")
    reservation_id = await _reserve(client, init_data, variant_id, qty=3)

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json={**RECIPIENT_PAYLOAD, "cod": True},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert fake_create_document.calls[0]["cod_amount"] == Decimal("600.00")


@pytest.mark.asyncio
async def test_create_ttn_cod_amount_override_wins_over_default(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91003)
    await _connect_np_key(client, init_data, monkeypatch)
    await _set_sender(client, init_data)
    variant_id = await _add_variant(shop_id, price="200.00")
    reservation_id = await _reserve(client, init_data, variant_id, qty=3)

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json={**RECIPIENT_PAYLOAD, "cod": True, "cod_amount": "123.45"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    assert fake_create_document.calls[0]["cod_amount"] == Decimal("123.45")


@pytest.mark.asyncio
async def test_create_ttn_explicit_weight_and_description_override_defaults(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91004)
    await _connect_np_key(client, init_data, monkeypatch)
    await _set_sender(client, init_data)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id, qty=1)

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json={**RECIPIENT_PAYLOAD, "weight": 2.5, "description": "Кросівки в коробці"},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    call = fake_create_document.calls[0]
    assert call["weight"] == 2.5
    assert call["description"] == "Кросівки в коробці"


# --------------------------------------------------------------------------- #
#  Гварди
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_ttn_np_error_returns_422_and_keeps_reservation_active(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91005)
    await _connect_np_key(client, init_data, monkeypatch)
    await _set_sender(client, init_data)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    fake_create_document.error = NovaPoshtaError("невірний формат телефону одержувача")

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json=RECIPIENT_PAYLOAD,
        headers={HEADER: init_data},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail.startswith("НП:")
    assert "телефону" in detail

    reservation = await _get_reservation(reservation_id)
    assert reservation.status == ReservationStatus.active
    assert reservation.ttn is None


@pytest.mark.asyncio
async def test_create_ttn_without_sender_data_returns_422(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91006)
    await _connect_np_key(client, init_data, monkeypatch)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json=RECIPIENT_PAYLOAD,
        headers={HEADER: init_data},
    )
    assert r.status_code == 422
    assert "відправника" in r.json()["detail"]
    assert fake_create_document.calls == []


@pytest.mark.asyncio
async def test_create_ttn_without_np_key_returns_422(
    client: AsyncClient, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91007)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json=RECIPIENT_PAYLOAD,
        headers={HEADER: init_data},
    )
    assert r.status_code == 422
    assert "ключ" in r.json()["detail"].lower()
    assert fake_create_document.calls == []


@pytest.mark.asyncio
async def test_create_ttn_reservation_not_active_returns_409(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, fake_create_document: _FakeCreateDocument
) -> None:
    init_data, shop_id = await _bootstrap(client, 91008)
    await _connect_np_key(client, init_data, monkeypatch)
    await _set_sender(client, init_data)
    variant_id = await _add_variant(shop_id)
    reservation_id = await _reserve(client, init_data, variant_id)

    r_release = await client.post(
        f"/api/reservations/{reservation_id}/release", headers={HEADER: init_data}
    )
    assert r_release.status_code == 200, r_release.text

    r = await client.post(
        f"/api/reservations/{reservation_id}/create-ttn",
        json=RECIPIENT_PAYLOAD,
        headers={HEADER: init_data},
    )
    assert r.status_code == 409
    assert fake_create_document.calls == []


# --------------------------------------------------------------------------- #
#  Профіль відправника
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_np_sender_put_then_get_roundtrip(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 91009)

    r0 = await client.get("/api/shop/np-sender", headers={HEADER: init_data})
    assert r0.status_code == 200
    assert r0.json()["city_ref"] is None

    await _set_sender(client, init_data)

    r1 = await client.get("/api/shop/np-sender", headers={HEADER: init_data})
    assert r1.status_code == 200
    body = r1.json()
    assert body["city_ref"] == "sender-city-ref"
    assert body["warehouse_name"] == "Відділення №1"
    assert body["phone"] == "380501112233"
    assert body["name"] == "ФОП Іваненко"


# --------------------------------------------------------------------------- #
#  Довідники: cities/warehouses проксі
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_cities_proxies_search_cities(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_data, _shop_id = await _bootstrap(client, 91010)
    await _connect_np_key(client, init_data, monkeypatch)

    async def _fake_search_cities(api_key: str, query: str) -> list[dict]:
        assert query == "Киї"
        return [{"ref": "city-ref-1", "name": "Київ"}]

    monkeypatch.setattr(np_documents_module, "search_cities", _fake_search_cities)

    r = await client.get("/api/np/cities", params={"q": "Киї"}, headers={HEADER: init_data})
    assert r.status_code == 200, r.text
    assert r.json() == [{"ref": "city-ref-1", "name": "Київ"}]


@pytest.mark.asyncio
async def test_list_warehouses_proxies_get_warehouses(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_data, _shop_id = await _bootstrap(client, 91011)
    await _connect_np_key(client, init_data, monkeypatch)

    async def _fake_get_warehouses(api_key: str, city_ref: str) -> list[dict]:
        assert city_ref == "city-ref-1"
        return [{"ref": "wh-ref-1", "name": "Відділення №1"}]

    monkeypatch.setattr(np_documents_module, "get_warehouses", _fake_get_warehouses)

    r = await client.get(
        "/api/np/warehouses", params={"city_ref": "city-ref-1"}, headers={HEADER: init_data}
    )
    assert r.status_code == 200, r.text
    assert r.json() == [{"ref": "wh-ref-1", "name": "Відділення №1"}]


@pytest.mark.asyncio
async def test_list_cities_without_np_key_returns_422(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 91012)

    r = await client.get("/api/np/cities", params={"q": "Ки"}, headers={HEADER: init_data})
    assert r.status_code == 422
