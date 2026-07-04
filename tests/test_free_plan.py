"""
Тести FREE-план: слот-ліміт, frozen-товари, enforce-перевірки.
FREE_PLAN_SPEC.md — джерело правди.

Сценарії:
  1. Free, 20 товарів → 21-й → 402.
  2. Free, 50 товарів (pre-seeded) → 20 active / 30 frozen; frozen edit → 402;
     active edit → 200; frozen delete → 204.
  3. Free, photos:False → upload → 402.
  4. Апгрейд free→basic → усі розморожуються (≤ 200).
  5. Pro (max_products=None) → жодного frozen, безліміт.
  6. Публічна вітрина без frozen.
  7. Tenant-ізоляція (frozen одного магазину не впливає на інший).
  8. Active trial → no limits (full access).
  9. /api/me повертає limits / products_count / active_count / max_products.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db as db_module
from app.models import (
    Plan,
    Product,
    Shop,
    Subscription,
    SubStatus,
    Variant,
    utcnow,
)
from app.seed import clear_demo_catalog, seed_plans
from tests.conftest import make_init_data

# --------------------------------------------------------------------------- #
#  Helpers                                                                      #
# --------------------------------------------------------------------------- #

_VARIANT = {"price": "100.00", "axis_values": {}, "sku": None, "on_hand": 5}


def _hdr(tg_id: int) -> dict:
    return {"X-Telegram-Init-Data": make_init_data(tg_id)}


async def _bootstrap(client: AsyncClient, tg_id: int) -> dict:
    """Перший запит bootstraps магазин. Повертає дані /api/me."""
    r = await client.get("/api/me", headers=_hdr(tg_id))
    assert r.status_code == 200
    return r.json()


async def _create_product(client: AsyncClient, tg_id: int, name: str):
    return await client.post(
        "/api/products",
        json={"name": name, "variants": [_VARIANT]},
        headers=_hdr(tg_id),
    )


async def _expire_trial(shop_id: int) -> None:
    """Переводимо магазин у free-стан: тріал завершився вчора."""
    async with db_module.async_session() as s:
        sub = await s.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        if sub is not None:
            sub.status = SubStatus.trial
            sub.trial_ends_at = utcnow() - timedelta(days=1)
            await s.commit()


async def _set_expired(shop_id: int) -> None:
    """Переводимо підписку у стан expired."""
    async with db_module.async_session() as s:
        sub = await s.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        if sub is not None:
            sub.status = SubStatus.expired
            await s.commit()


async def _activate_plan(shop_id: int, plan_code: str) -> None:
    """Активуємо платний план (симуляція вебхука провайдера)."""
    async with db_module.async_session() as s:
        plan = await s.scalar(select(Plan).where(Plan.code == plan_code))
        assert plan is not None, f"Plan '{plan_code}' not found — run seed_plans first"
        sub = await s.scalar(select(Subscription).where(Subscription.shop_id == shop_id))
        assert sub is not None
        sub.status = SubStatus.active
        sub.plan_id = plan.id
        sub.current_period_end = utcnow() + timedelta(days=30)
        sub.auto_renew = True
        await s.commit()


async def _clear_demos(shop_id: int) -> None:
    """Прибирає demo-товари, щоб тести починали з чистого рахунку."""
    async with db_module.async_session() as s:
        shop = await s.get(Shop, shop_id)
        assert shop is not None
        await clear_demo_catalog(s, shop)


async def _seed_n_products(shop_id: int, n: int, *, base_dt: datetime | None = None) -> list[int]:
    """Вставляє N товарів напряму в БД з детермінованим created_at.

    base_dt: стартова точка (за замовчуванням 2024-01-01). Тести, що вимагають
    конкретний порядок «найстаріший → найновіший», передають цей параметр явно.
    Кожен наступний товар +1 хвилина.
    """
    if base_dt is None:
        base_dt = datetime(2024, 1, 1, tzinfo=UTC)

    ids: list[int] = []
    async with db_module.async_session() as s:
        for i in range(n):
            p = Product(
                shop_id=shop_id,
                name=f"Product {i + 1}",
                attributes={},
                created_at=base_dt + timedelta(minutes=i),
            )
            s.add(p)
            await s.flush()
            s.add(
                Variant(
                    shop_id=shop_id,
                    product_id=p.id,
                    axis_values={},
                    price=Decimal("100"),
                    on_hand=5,
                )
            )
            ids.append(p.id)
        await s.commit()
    return ids


# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
async def plans() -> None:
    """Засіває плани перед кожним тестом."""
    async with db_module.async_session() as s:
        await seed_plans(s)


# --------------------------------------------------------------------------- #
#  1. Free: 20 товарів → 21-й → 402                                           #
# --------------------------------------------------------------------------- #

async def test_free_limit_21st_product(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1001)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 20)

    r = await _create_product(client, tg_id=1001, name="Product 21")
    assert r.status_code == 402, r.text
    assert "Ліміт плану" in r.json()["detail"]


async def test_free_limit_exactly_at_limit_allowed(client: AsyncClient) -> None:
    """19 товарів + 1 через API → 201 (ще в межах ліміту)."""
    me = await _bootstrap(client, tg_id=1002)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 19)

    r = await _create_product(client, tg_id=1002, name="Product 20")
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
#  2. Free, 50 товарів: 20 active / 30 frozen                                 #
# --------------------------------------------------------------------------- #

async def test_frozen_set_correct(client: AsyncClient) -> None:
    """50 товарів → 20 найновіших активних, 30 frozen."""
    from app.services.catalog import frozen_product_ids

    me = await _bootstrap(client, tg_id=1010)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    # ids[0] = найстаріший (2024-01-01 00:00), ids[49] = найновіший

    async with db_module.async_session() as s:
        frozen = await frozen_product_ids(shop_id, s)

    # Топ-20 = ids[30..49] (20 найновіших) → active.
    expected_frozen = set(ids[:30])

    assert frozen == expected_frozen, (
        f"frozen mismatch: got {len(frozen)} ids, expected {len(expected_frozen)}"
    )
    assert set(ids[30:]).isdisjoint(frozen), "Active products leaked into frozen set"


async def test_frozen_edit_returns_402(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1011)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    frozen_id = ids[0]  # найстаріший → заморожений

    r = await client.patch(
        f"/api/products/{frozen_id}",
        json={"name": "Renamed frozen"},
        headers=_hdr(1011),
    )
    assert r.status_code == 402, r.text
    assert "заморожено" in r.json()["detail"]


async def test_active_edit_returns_200(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1012)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    active_id = ids[49]  # найновіший → активний

    r = await client.patch(
        f"/api/products/{active_id}",
        json={"name": "Renamed active"},
        headers=_hdr(1012),
    )
    assert r.status_code == 200, r.text


async def test_frozen_delete_allowed(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1013)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    frozen_id = ids[0]

    r = await client.delete(f"/api/products/{frozen_id}", headers=_hdr(1013))
    assert r.status_code == 204, r.text


async def test_list_products_is_frozen_flag(client: AsyncClient) -> None:
    """GET /api/products: is_frozen=True для frozen, False для active."""
    me = await _bootstrap(client, tg_id=1014)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 25)
    # ids[0..4] — 5 найстаріших → frozen; ids[5..24] — 20 найновіших → active

    r = await client.get("/api/products", headers=_hdr(1014))
    assert r.status_code == 200
    products = r.json()

    frozen_in_resp = {p["id"] for p in products if p["is_frozen"]}
    active_in_resp = {p["id"] for p in products if not p["is_frozen"]}

    assert frozen_in_resp == set(ids[:5])
    assert active_in_resp == set(ids[5:])


async def test_frozen_restock_returns_402(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1015)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    frozen_product_id = ids[0]

    async with db_module.async_session() as s:
        v = await s.scalar(select(Variant).where(Variant.product_id == frozen_product_id))
    assert v is not None

    r = await client.post(
        f"/api/variants/{v.id}/restock",
        json={"qty": 1},
        headers=_hdr(1015),
    )
    assert r.status_code == 402, r.text


async def test_frozen_adjust_returns_402(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1016)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    frozen_product_id = ids[0]

    async with db_module.async_session() as s:
        v = await s.scalar(select(Variant).where(Variant.product_id == frozen_product_id))

    r = await client.post(
        f"/api/variants/{v.id}/adjust",
        json={"qty": 1, "reason": "sold"},
        headers=_hdr(1016),
    )
    assert r.status_code == 402, r.text


async def test_frozen_reserve_returns_402(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1017)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    frozen_product_id = ids[0]

    async with db_module.async_session() as s:
        v = await s.scalar(select(Variant).where(Variant.product_id == frozen_product_id))

    r = await client.post(
        f"/api/variants/{v.id}/reserve",
        json={"qty": 1},
        headers=_hdr(1017),
    )
    assert r.status_code == 402, r.text


# --------------------------------------------------------------------------- #
#  3. Free, photos:False → upload → 402                                       #
# --------------------------------------------------------------------------- #

async def test_free_photo_upload_blocked(client: AsyncClient) -> None:
    """На free-плані фото недоступні → 402."""
    me = await _bootstrap(client, tg_id=1020)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 1)

    async with db_module.async_session() as s:
        v = await s.scalar(select(Variant).where(Variant.product_id == ids[0]))

    r = await client.post(
        f"/api/variants/{v.id}/photo",
        files={"file": ("test.jpg", b"FAKEJPEG", "image/jpeg")},
        headers=_hdr(1020),
    )
    assert r.status_code == 402, r.text
    assert "Basic+" in r.json()["detail"] or "Фото" in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  4. Апгрейд free→basic → усі розморожуються                                #
# --------------------------------------------------------------------------- #

async def test_upgrade_to_basic_unfreezes_all(client: AsyncClient) -> None:
    from app.services.catalog import frozen_product_ids

    me = await _bootstrap(client, tg_id=1030)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 50)

    async with db_module.async_session() as s:
        frozen_before = await frozen_product_ids(shop_id, s)
    assert len(frozen_before) == 30

    await _activate_plan(shop_id, "basic")

    async with db_module.async_session() as s:
        frozen_after = await frozen_product_ids(shop_id, s)

    assert frozen_after == set(), f"Expected empty frozen after upgrade, got {len(frozen_after)}"


async def test_upgrade_to_basic_allows_edit_previously_frozen(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1031)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    ids = await _seed_n_products(shop_id, 50)
    was_frozen_id = ids[0]

    await _activate_plan(shop_id, "basic")

    r = await client.patch(
        f"/api/products/{was_frozen_id}",
        json={"name": "Now editable"},
        headers=_hdr(1031),
    )
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
#  5. Pro (max_products=None) → жодного frozen, безліміт                     #
# --------------------------------------------------------------------------- #

async def test_pro_no_frozen(client: AsyncClient) -> None:
    from app.services.catalog import frozen_product_ids

    me = await _bootstrap(client, tg_id=1040)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _activate_plan(shop_id, "pro")

    await _seed_n_products(shop_id, 100)

    async with db_module.async_session() as s:
        frozen = await frozen_product_ids(shop_id, s)

    assert frozen == set()


async def test_pro_create_unlimited(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1041)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _activate_plan(shop_id, "pro")
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 300)

    r = await _create_product(client, tg_id=1041, name="Product 301")
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
#  6. Публічна вітрина без frozen                                             #
# --------------------------------------------------------------------------- #

async def test_public_catalog_excludes_frozen(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1050)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 25)
    # ids[0..4] = frozen (5 найстаріших), ids[5..24] = active (20 найновіших)

    async with db_module.async_session() as s:
        shop = await s.get(Shop, shop_id)
        shop.public_catalog_enabled = True
        shop_slug = shop.slug
        await s.commit()

    r = await client.get(f"/api/public/{shop_slug}")
    assert r.status_code == 200
    catalog = r.json()

    product_names_in_catalog = {p["name"] for p in catalog["products"]}

    frozen_names = {f"Product {i + 1}" for i in range(5)}   # найстаріші 5
    active_names = {f"Product {i + 1}" for i in range(5, 25)}

    assert product_names_in_catalog == active_names, (
        f"Public catalog should show only active products. "
        f"Frozen leaked: {product_names_in_catalog & frozen_names}"
    )


# --------------------------------------------------------------------------- #
#  7. Tenant-ізоляція                                                          #
# --------------------------------------------------------------------------- #

async def test_tenant_isolation_frozen(client: AsyncClient) -> None:
    """Frozen одного магазину не впливає на стан іншого."""
    from app.services.catalog import frozen_product_ids

    # Магазин A: 50 товарів на free → 30 frozen.
    me_a = await _bootstrap(client, tg_id=1060)
    shop_a = me_a["shop_id"]
    await _expire_trial(shop_a)
    await _clear_demos(shop_a)
    await _seed_n_products(shop_a, 50)

    # Магазин B: 5 товарів на free → жодного frozen.
    me_b = await _bootstrap(client, tg_id=1061)
    shop_b = me_b["shop_id"]
    await _expire_trial(shop_b)
    await _clear_demos(shop_b)
    await _seed_n_products(shop_b, 5)

    async with db_module.async_session() as s:
        frozen_a = await frozen_product_ids(shop_a, s)
        frozen_b = await frozen_product_ids(shop_b, s)

    assert len(frozen_a) == 30
    assert frozen_b == set(), "Shop B should have no frozen products"
    assert frozen_a.isdisjoint(frozen_b)


async def test_tenant_cannot_edit_other_shop_product(client: AsyncClient) -> None:
    """Магазин B не може редагувати товар магазину A (tenant ізоляція)."""
    me_a = await _bootstrap(client, tg_id=1062)
    shop_a = me_a["shop_id"]
    await _expire_trial(shop_a)
    await _clear_demos(shop_a)
    ids_a = await _seed_n_products(shop_a, 1)

    me_b = await _bootstrap(client, tg_id=1063)
    shop_b = me_b["shop_id"]
    await _activate_plan(shop_b, "pro")

    r = await client.patch(
        f"/api/products/{ids_a[0]}",
        json={"name": "Cross-tenant hack"},
        headers=_hdr(1063),
    )
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
#  8. Active trial → повний доступ                                            #
# --------------------------------------------------------------------------- #

async def test_active_trial_no_limits(client: AsyncClient) -> None:
    from app.services.catalog import frozen_product_ids

    me = await _bootstrap(client, tg_id=1070)
    shop_id = me["shop_id"]
    await _clear_demos(shop_id)
    # НЕ expire trial — залишаємо активним.

    await _seed_n_products(shop_id, 50)

    async with db_module.async_session() as s:
        frozen = await frozen_product_ids(shop_id, s)

    assert frozen == set(), "Active trial should have no frozen products"


async def test_active_trial_can_create_beyond_free_limit(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1071)
    shop_id = me["shop_id"]
    await _clear_demos(shop_id)
    # НЕ expire trial.

    await _seed_n_products(shop_id, 20)

    r = await _create_product(client, tg_id=1071, name="Product 21 in trial")
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
#  9. /api/me — limits / products_count / active_count / max_products         #
# --------------------------------------------------------------------------- #

async def test_me_free_plan_fields(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1080)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 25)

    r = await client.get("/api/me", headers=_hdr(1080))
    assert r.status_code == 200
    data = r.json()

    assert data["max_products"] == 20
    assert data["products_count"] == 25
    assert data["active_count"] == 20
    assert data["limits"]["photos"] is False
    assert data["limits"]["max_products"] == 20


async def test_me_pro_plan_fields(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1081)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)
    await _activate_plan(shop_id, "pro")
    await _clear_demos(shop_id)

    await _seed_n_products(shop_id, 10)

    r = await client.get("/api/me", headers=_hdr(1081))
    data = r.json()

    assert data["max_products"] is None
    assert data["products_count"] == 10
    assert data["active_count"] == 10
    assert data["limits"]["photos"] is True


async def test_me_is_writable_free(client: AsyncClient) -> None:
    """Free-план (expired trial) → is_writable=True (не стіна)."""
    me = await _bootstrap(client, tg_id=1082)
    shop_id = me["shop_id"]
    await _expire_trial(shop_id)

    r = await client.get("/api/me", headers=_hdr(1082))
    data = r.json()
    assert data["is_writable"] is True


async def test_me_is_writable_expired_status(client: AsyncClient) -> None:
    """Статус expired → is_writable=True (free-план, не read-only)."""
    me = await _bootstrap(client, tg_id=1083)
    shop_id = me["shop_id"]
    await _set_expired(shop_id)

    r = await client.get("/api/me", headers=_hdr(1083))
    data = r.json()
    assert data["is_writable"] is True
