"""
Stage 8 — консолідований аудит tenant-ізоляції (CLAUDE.md, інваріант №1).

Для кожного ендпоінта, що читає/пише дані конкретного магазину, доводимо,
що магазин A не може прочитати чи змінити дані магазину B: чужий
id -> 404 (ніколи 500/200 з чужими даними), список ніколи не містить чужих
рядків, і shop_id в усіх відповідях відповідає викликачу.

Окремі стадії вже покривали частину цього (2a/2b/4a/4b/6b/7c) — тут не
дублюємо їх повністю, а збираємо ОДНЕ місце, що явно проходить по всіх
ресурсах (каталог/варіанти/склад/резерви/замовлення/фото/білінг/налаштування
магазину), плюс закриваємо прогалини, яких там не було (список резервів,
список замовлень, чужий variant_id у website-замовленні, колізія
api_key_prefix, ізоляція білінгу/налаштувань магазину).
"""
from __future__ import annotations

import io
import secrets
from decimal import Decimal
from uuid import uuid4

import aioboto3
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app import db
from app.config import settings
from app.models import Product, Shop, Subscription, Variant
from app.security.crypto import encrypt
from app.services.shop import generate_api_key
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"
API_KEY_HEADER = "X-API-Key"


# --------------------------------------------------------------------------- #
#  Хелпери
# --------------------------------------------------------------------------- #
async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _bootstrap_with_api_key(
    client: AsyncClient, tg_id: int, name: str = "Тест"
) -> tuple[str, int, str]:
    init_data, shop_id = await _bootstrap(client, tg_id, name)
    async with db.async_session() as session:
        shop = await session.get(Shop, shop_id)
        assert shop is not None
        plaintext_key = await generate_api_key(session, shop)
    return init_data, shop_id, plaintext_key


async def _add_variant(shop_id: int, on_hand: int = 5, price: str = "100") -> int:
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


async def _create_product(client: AsyncClient, init_data: str, name: str = "Товар") -> int:
    payload = {"name": name, "variants": [{"axis_values": {}, "price": "10"}]}
    r = await client.post("/api/products", json=payload, headers={HEADER: init_data})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _reserve(client: AsyncClient, init_data: str, variant_id: int, qty: int = 1) -> int:
    r = await client.post(
        f"/api/variants/{variant_id}/reserve",
        json={"qty": qty},
        headers={HEADER: init_data},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# --------------------------------------------------------------------------- #
#  Каталог: товари/варіанти                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_products_list_and_mutation_isolation(client: AsyncClient) -> None:
    init_a, _shop_a = await _bootstrap(client, 80001, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 80002, "Шоп Б")

    product_id = await _create_product(client, init_a, "Товар А")

    r_list_b = await client.get("/api/products", headers={HEADER: init_b})
    assert r_list_b.status_code == 200
    assert all(p["id"] != product_id for p in r_list_b.json())

    r_patch_b = await client.patch(
        f"/api/products/{product_id}", json={"name": "Захоплено"}, headers={HEADER: init_b}
    )
    assert r_patch_b.status_code == 404

    r_delete_b = await client.delete(f"/api/products/{product_id}", headers={HEADER: init_b})
    assert r_delete_b.status_code == 404

    # перевірка, що дані не змінились
    r_list_a = await client.get("/api/products", headers={HEADER: init_a})
    own = next(p for p in r_list_a.json() if p["id"] == product_id)
    assert own["name"] == "Товар А"
    assert own["archived"] is False


@pytest.fixture
def _patch_r2(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    class _FakeS3Client:
        async def __aenter__(self) -> "_FakeS3Client":
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

        async def put_object(self, **kwargs: object) -> dict:
            calls.append(kwargs)
            return {}

    class _FakeR2Session:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def client(self, *args: object, **kwargs: object) -> _FakeS3Client:
            return _FakeS3Client()

    monkeypatch.setattr(aioboto3, "Session", _FakeR2Session)
    monkeypatch.setattr(settings, "R2_PUBLIC_URL", "https://cdn.example.test")
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY", "test-access-key")
    monkeypatch.setattr(settings, "R2_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "R2_BUCKET", "test-bucket")
    return calls


@pytest.mark.asyncio
async def test_photo_upload_isolation(client: AsyncClient, _patch_r2: list[dict]) -> None:
    _init_a, shop_a = await _bootstrap(client, 80003, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 80004, "Шоп Б")

    variant_a = await _add_variant(shop_a)

    image = Image.new("RGB", (10, 10), color=(1, 2, 3))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")

    r = await client.post(
        f"/api/variants/{variant_a}/photo",
        files={"file": ("photo.jpg", buf.getvalue(), "image/jpeg")},
        headers={HEADER: init_b},
    )
    assert r.status_code == 404
    assert _patch_r2 == []


# --------------------------------------------------------------------------- #
#  Склад: restock/adjust/reserve, резерви                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_inventory_mutation_isolation(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 80101, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 80102, "Шоп Б")

    variant_a = await _add_variant(shop_a, on_hand=10)

    r_restock = await client.post(
        f"/api/variants/{variant_a}/restock", json={"qty": 1}, headers={HEADER: init_b}
    )
    assert r_restock.status_code == 404

    r_adjust = await client.post(
        f"/api/variants/{variant_a}/adjust", json={"new_on_hand": 0}, headers={HEADER: init_b}
    )
    assert r_adjust.status_code == 404

    r_reserve = await client.post(
        f"/api/variants/{variant_a}/reserve", json={"qty": 1}, headers={HEADER: init_b}
    )
    assert r_reserve.status_code == 404

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_a)
        assert variant is not None
        assert variant.on_hand == 10
        assert variant.reserved == 0


@pytest.mark.asyncio
async def test_reservation_list_and_action_isolation(client: AsyncClient) -> None:
    init_a, shop_a = await _bootstrap(client, 80103, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 80104, "Шоп Б")

    variant_a = await _add_variant(shop_a, on_hand=10)
    reservation_id = await _reserve(client, init_a, variant_a, qty=2)

    r_list_b = await client.get("/api/reservations", headers={HEADER: init_b})
    assert r_list_b.status_code == 200
    assert all(res["id"] != reservation_id for res in r_list_b.json())

    r_list_a = await client.get("/api/reservations", headers={HEADER: init_a})
    assert any(res["id"] == reservation_id for res in r_list_a.json())

    r_release_b = await client.post(
        f"/api/reservations/{reservation_id}/release", headers={HEADER: init_b}
    )
    assert r_release_b.status_code == 404

    r_fulfill_b = await client.post(
        f"/api/reservations/{reservation_id}/fulfill", headers={HEADER: init_b}
    )
    assert r_fulfill_b.status_code == 404

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_a)
        assert variant is not None
        assert variant.reserved == 2  # резерв не зняли і не списали чужим запитом


# --------------------------------------------------------------------------- #
#  Замовлення                                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_orders_list_and_action_isolation(client: AsyncClient) -> None:
    init_a, shop_a, api_key_a = await _bootstrap_with_api_key(client, 80201, "Шоп А")
    init_b, _shop_b, _api_key_b = await _bootstrap_with_api_key(client, 80202, "Шоп Б")

    variant_a = await _add_variant(shop_a, on_hand=10)
    r_order = await client.post(
        "/api/website/orders",
        json={"items": [{"variant_id": variant_a, "qty": 1}], "idempotency_key": "k-iso-1"},
        headers={API_KEY_HEADER: api_key_a},
    )
    assert r_order.status_code == 201, r_order.text
    order_id = r_order.json()["id"]

    r_list_b = await client.get("/api/orders", headers={HEADER: init_b})
    assert r_list_b.status_code == 200
    assert all(o["id"] != order_id for o in r_list_b.json())

    r_confirm_b = await client.post(f"/api/orders/{order_id}/confirm", headers={HEADER: init_b})
    assert r_confirm_b.status_code == 404

    r_cancel_b = await client.post(f"/api/orders/{order_id}/cancel", headers={HEADER: init_b})
    assert r_cancel_b.status_code == 404

    r_list_a = await client.get("/api/orders", headers={HEADER: init_a})
    assert any(o["id"] == order_id for o in r_list_a.json())


@pytest.mark.asyncio
async def test_website_order_cannot_reference_other_shops_variant(client: AsyncClient) -> None:
    """Ключ магазину A валідний, але товар у замовленні належить B — інакше
    A міг би списувати/резервувати склад B через свій власний (легітимний)
    API-ключ просто підставивши чужий variant_id."""
    _init_a, _shop_a, api_key_a = await _bootstrap_with_api_key(client, 80203, "Шоп А")
    _init_b, shop_b, _api_key_b = await _bootstrap_with_api_key(client, 80204, "Шоп Б")

    variant_b = await _add_variant(shop_b, on_hand=10)

    r = await client.post(
        "/api/website/orders",
        json={"items": [{"variant_id": variant_b, "qty": 1}], "idempotency_key": "k-iso-2"},
        headers={API_KEY_HEADER: api_key_a},
    )
    assert r.status_code == 404

    async with db.async_session() as session:
        variant = await session.get(Variant, variant_b)
        assert variant is not None
        assert variant.reserved == 0  # резерв не пройшов чужим ключем


# --------------------------------------------------------------------------- #
#  Білінг                                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_billing_cancel_does_not_affect_other_shop(client: AsyncClient) -> None:
    init_a, _shop_a = await _bootstrap(client, 80301, "Шоп А")
    _init_b, shop_b = await _bootstrap(client, 80302, "Шоп Б")

    r_cancel = await client.post("/api/billing/cancel", headers={HEADER: init_a})
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "canceled"

    async with db.async_session() as session:
        sub_b = await session.scalar(
            select(Subscription).where(Subscription.shop_id == shop_b)
        )
        assert sub_b is not None
        assert sub_b.status.value == "trial"
        assert sub_b.canceled_at is None


# --------------------------------------------------------------------------- #
#  Налаштування магазину                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_shop_webhook_config_does_not_leak_to_other_shop(client: AsyncClient) -> None:
    init_a, _shop_a = await _bootstrap(client, 80401, "Шоп А")
    _init_b, shop_b = await _bootstrap(client, 80402, "Шоп Б")

    r = await client.post(
        "/api/shop/webhook", json={"url": "https://shop-a.example/hook"}, headers={HEADER: init_a}
    )
    assert r.status_code == 200

    async with db.async_session() as session:
        shop_b_row = await session.get(Shop, shop_b)
        assert shop_b_row is not None
        assert shop_b_row.webhook_url is None
        assert shop_b_row.webhook_secret_encrypted is None


@pytest.mark.asyncio
async def test_clear_demos_does_not_touch_other_shop(client: AsyncClient) -> None:
    init_a, _shop_a = await _bootstrap(client, 80403, "Шоп А")
    init_b, _shop_b = await _bootstrap(client, 80404, "Шоп Б")

    r_clear = await client.post("/api/shop/clear-demos", headers={HEADER: init_a})
    assert r_clear.status_code == 200
    assert r_clear.json()["removed"] == 2

    r_products_b = await client.get("/api/products", headers={HEADER: init_b})
    assert any(p["is_demo"] for p in r_products_b.json())  # магазин B свої демо не втратив


# --------------------------------------------------------------------------- #
#  Публічний каталог                                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_public_catalog_scoped_by_slug_only(client: AsyncClient) -> None:
    _init_a, shop_a = await _bootstrap(client, 80501, "Шоп А")
    _init_b, shop_b = await _bootstrap(client, 80502, "Шоп Б")

    await _add_variant(shop_a, price="111.11")
    await _add_variant(shop_b, price="999.99")

    async with db.async_session() as session:
        shop_a_row = await session.get(Shop, shop_a)
        assert shop_a_row is not None
        shop_a_row.public_catalog_enabled = True
        slug_a = shop_a_row.slug
        await session.commit()

    r = await client.get(f"/api/public/{slug_a}")
    assert r.status_code == 200
    prices = {v["price"] for p in r.json()["products"] for v in p["variants"]}
    assert "999.99" not in prices


# --------------------------------------------------------------------------- #
#  X-API-Key: колізія api_key_prefix (Стадія 8, item 3)                       #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_api_key_prefix_collision_resolves_to_correct_shop(client: AsyncClient) -> None:
    """`api_key_prefix` не унікальний — навмисно форсуємо колізію між двома
    магазинами і доводимо, що це НЕ дає ані 500 (`MultipleResultsFound`),
    ані хибної авторизації під чужим магазином."""
    _init_a, shop_a, api_key_a = await _bootstrap_with_api_key(client, 80601, "Шоп А")
    _init_b, shop_b, _original_key_b = await _bootstrap_with_api_key(client, 80602, "Шоп Б")

    # Справжня колізія: інший ПОВНИЙ ключ, що випадково починається тими
    # самими 8 символами, що й ключ A (а не просто підмінений стовпець
    # без зміни самого ключа).
    crafted_key_b = api_key_a[:8] + secrets.token_urlsafe(32)
    async with db.async_session() as session:
        shop_b_row = await session.get(Shop, shop_b)
        assert shop_b_row is not None
        shop_b_row.api_key_prefix = crafted_key_b[:8]
        shop_b_row.api_key_encrypted = encrypt(crafted_key_b)
        await session.commit()
    api_key_b = crafted_key_b

    variant_a = await _add_variant(shop_a, on_hand=5)
    variant_b = await _add_variant(shop_b, on_hand=5)

    # ключ A з префіксом, що колізує -> все одно резолвиться у власний товар A
    r_a_own = await client.post(
        "/api/website/orders",
        json={"items": [{"variant_id": variant_a, "qty": 1}], "idempotency_key": "k-col-1"},
        headers={API_KEY_HEADER: api_key_a},
    )
    assert r_a_own.status_code == 201, r_a_own.text

    # ...і НЕ пускає до товару B (інакше колізія дала б доступ під чужим shop)
    r_a_cross = await client.post(
        "/api/website/orders",
        json={"items": [{"variant_id": variant_b, "qty": 1}], "idempotency_key": "k-col-2"},
        headers={API_KEY_HEADER: api_key_a},
    )
    assert r_a_cross.status_code == 404

    # ключ B (та сама колізія) резолвиться у власний товар B
    r_b_own = await client.post(
        "/api/website/orders",
        json={"items": [{"variant_id": variant_b, "qty": 1}], "idempotency_key": "k-col-3"},
        headers={API_KEY_HEADER: api_key_b},
    )
    assert r_b_own.status_code == 201, r_b_own.text

    # невідомий ключ з тим самим префіксом -> 401, НЕ 500
    forged = api_key_a[:8] + "x" * (len(api_key_a) - 8)
    r_forged = await client.post(
        "/api/website/orders",
        json={"items": [{"variant_id": variant_a, "qty": 1}], "idempotency_key": "k-col-4"},
        headers={API_KEY_HEADER: forged},
    )
    assert r_forged.status_code == 401
