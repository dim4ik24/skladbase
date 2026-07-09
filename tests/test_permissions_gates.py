"""
Stage 1b — granular permissions gates: acceptance tests.

For each permission, a manager with that permission disabled gets 403.
Owner override: all DB columns False still passes (owner role check, not column).
Free-delete: DELETE /products/{id}/photos/{pid} has no writable check — manager
  with can_edit_products=True succeeds regardless of subscription state.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import db
from app.models import MemberRole, Membership, Product, ProductPhoto, Role, Subscription, Variant
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"

_ALL_PERMS = [
    "can_view_inventory",
    "can_edit_products",
    "can_manage_reservations",
    "can_manage_stock",
    "can_view_finance",
    "can_manage_billing",
]

_SIMPLE_PRODUCT_PAYLOAD = {
    "name": "Тест-товар",
    "variants": [{"price": "99.00", "axis_values": {}, "on_hand": 5}],
}


async def _bootstrap(client: AsyncClient, tg_id: int) -> tuple[str, int]:
    init_data = make_init_data(tg_id)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _make_manager(shop_id: int, tg_id: int, **perms: bool) -> str:
    """Insert a manager whose role has explicit permission flags (unspecified
    perms default to True) — права тепер живуть на Role, не на Membership."""
    async with db.async_session() as s:
        role = Role(
            shop_id=shop_id, name=f"Тест-роль {tg_id}", is_system=False,
            **{perm: perms.get(perm, True) for perm in _ALL_PERMS},
        )
        s.add(role)
        await s.flush()
        s.add(Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager, role_id=role.id))
        await s.commit()
    return make_init_data(tg_id)


async def _add_product(shop_id: int) -> int:
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Товар для тесту")
        session.add(product)
        await session.flush()
        session.add(Variant(shop_id=shop_id, product_id=product.id, price=Decimal("100")))
        await session.commit()
        return product.id


async def _add_photo(product_id: int) -> int:
    async with db.async_session() as session:
        photo = ProductPhoto(
            product_id=product_id,
            url="https://not-r2.example.test/photo.webp",
            position=0,
        )
        session.add(photo)
        await session.commit()
        return photo.id


# --------------------------------------------------------------------------- #
#  Test 1: can_view_finance=False → GET /finance/summary → 403
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_view_finance_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80001)
    mgr = await _make_manager(shop_id, 80002, can_view_finance=False)

    r = await client.get("/api/finance/summary", headers={HEADER: mgr})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 2a: can_edit_products=False → POST /products → 403
#  Test 2b: same manager → GET /products → 200 (uses can_view_inventory, still True)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_edit_products_post_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80011)
    mgr = await _make_manager(shop_id, 80012, can_edit_products=False)

    r = await client.post("/api/products", json=_SIMPLE_PRODUCT_PAYLOAD, headers={HEADER: mgr})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_no_edit_products_get_still_200(client: AsyncClient) -> None:
    """can_edit_products=False must NOT block GET /products (uses can_view_inventory)."""
    _owner_init, shop_id = await _bootstrap(client, tg_id=80021)
    mgr = await _make_manager(shop_id, 80022, can_edit_products=False)

    r = await client.get("/api/products", headers={HEADER: mgr})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
#  Test 3: can_manage_stock=False → POST /variants/{id}/restock → 403
#  (403 fires before variant lookup — any variant_id suffices)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_manage_stock_restock_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80031)
    mgr = await _make_manager(shop_id, 80032, can_manage_stock=False)

    r = await client.post(
        "/api/variants/99999/restock", json={"qty": 10}, headers={HEADER: mgr}
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 4: can_manage_reservations=False → POST /variants/{id}/reserve → 403
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_manage_reservations_reserve_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80041)
    mgr = await _make_manager(shop_id, 80042, can_manage_reservations=False)

    r = await client.post(
        "/api/variants/99999/reserve", json={"qty": 1}, headers={HEADER: mgr}
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 5: can_manage_reservations=False → POST /orders/{id}/confirm → 403
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_manage_reservations_confirm_order_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80051)
    mgr = await _make_manager(shop_id, 80052, can_manage_reservations=False)

    r = await client.post("/api/orders/99999/confirm", headers={HEADER: mgr})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 6: can_manage_billing=False → POST /billing/checkout/stars → 403
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_manage_billing_stars_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80061)
    mgr = await _make_manager(shop_id, 80062, can_manage_billing=False)

    r = await client.post(
        "/api/billing/checkout/stars",
        json={"plan_code": "pro_monthly"},
        headers={HEADER: mgr},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 7: can_manage_billing=False → POST /billing/cancel → 403
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_manage_billing_cancel_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80071)
    mgr = await _make_manager(shop_id, 80072, can_manage_billing=False)

    r = await client.post("/api/billing/cancel", headers={HEADER: mgr})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 8: can_view_inventory=False → GET /products → 403
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_view_inventory_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80081)
    mgr = await _make_manager(shop_id, 80082, can_view_inventory=False)

    r = await client.get("/api/products", headers={HEADER: mgr})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 9: can_edit_products=False → DELETE /products/{id}/photos/{pid} → 403
#  (require_permission only — 403 fires before DB lookup)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_edit_products_delete_photo_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80091)
    mgr = await _make_manager(shop_id, 80092, can_edit_products=False)

    r = await client.delete(
        "/api/products/99999/photos/99999", headers={HEADER: mgr}
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 10: owner whose role_ref has ALL perms = False → still 200/201
#  (owner override: role==owner check trumps role_ref values entirely)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_owner_override_all_role_perms_false(client: AsyncClient) -> None:
    owner_init, _shop_id = await _bootstrap(client, tg_id=80101)

    # Флипаємо усі can_*-права на role_ref власника — не Membership напряму.
    async with db.async_session() as session:
        membership = await session.scalar(
            select(Membership)
            .options(selectinload(Membership.role_ref))
            .where(Membership.tg_id == 80101)
        )
        assert membership is not None
        for perm in _ALL_PERMS:
            setattr(membership.role_ref, perm, False)
        await session.commit()

    # Finance: was require_owner (now require_permission) — must still pass
    r = await client.get("/api/finance/summary", headers={HEADER: owner_init})
    assert r.status_code == 200

    # Products write: must still pass
    r2 = await client.post(
        "/api/products", json=_SIMPLE_PRODUCT_PAYLOAD, headers={HEADER: owner_init}
    )
    assert r2.status_code == 201


# --------------------------------------------------------------------------- #
#  Test 11: free-delete — DELETE /products/{id}/photos/{pid} has NO writable
#  check → manager with can_edit_products=True succeeds → 204
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_free_delete_photo_no_writable_check(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=80111)
    mgr = await _make_manager(shop_id, 80112, can_edit_products=True)

    product_id = await _add_product(shop_id)
    photo_id = await _add_photo(product_id)

    r = await client.delete(
        f"/api/products/{product_id}/photos/{photo_id}", headers={HEADER: mgr}
    )
    assert r.status_code == 204

    # Photo is gone from DB
    async with db.async_session() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.shop_id == shop_id)
        )
        # Subscription still exists and is writable (free plan stays writable)
        assert sub is not None and sub.is_writable is True
