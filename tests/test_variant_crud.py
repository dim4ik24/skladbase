"""
Variant CRUD acceptance tests (feat-variant-crud).

PATCH /api/variants/{id}            — edit price/sku/axis_values
POST  /api/products/{id}/variants   — add variant to existing product
DELETE /api/variants/{id}           — delete variant
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient

from app import db
from app.models import (
    MemberRole,
    Membership,
    Product,
    ProductTemplate,
    Reservation,
    ReservationSource,
    ReservationStatus,
    TemplateCode,
    Variant,
)
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


# --------------------------------------------------------------------------- #
#  Shared helpers
# --------------------------------------------------------------------------- #

async def _bootstrap(client: AsyncClient, tg_id: int) -> tuple[str, int]:
    init_data = make_init_data(tg_id)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _make_manager(shop_id: int, tg_id: int, **perms: bool) -> str:
    m = Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager)
    for perm in _ALL_PERMS:
        setattr(m, perm, perms.get(perm, True))
    async with db.async_session() as s:
        s.add(m)
        await s.commit()
    return make_init_data(tg_id)


async def _mk_product(shop_id: int, n_variants: int = 1) -> tuple[int, list[int]]:
    """Create templateless product with n empty-axis variants. Returns (product_id, [variant_ids])."""
    async with db.async_session() as session:
        product = Product(shop_id=shop_id, name="Тест-товар")
        session.add(product)
        await session.flush()
        ids: list[int] = []
        for _ in range(n_variants):
            v = Variant(
                shop_id=shop_id,
                product_id=product.id,
                price=Decimal("100"),
                axis_values={},
            )
            session.add(v)
            await session.flush()
            ids.append(v.id)
        await session.commit()
        return product.id, ids


async def _mk_product_with_size_template(
    shop_id: int,
) -> tuple[int, int]:
    """Create product with size-enum template (S/M/L) + initial M variant.

    Returns (product_id, m_variant_id).
    Direct DB insert — bypasses API plan/writable checks so tests stay focused.
    """
    async with db.async_session() as session:
        tpl = ProductTemplate(
            shop_id=shop_id,
            code=TemplateCode.generic,
            name="Розміри",
            field_schema={
                "attributes": [],
                "variant_axes": [
                    {
                        "key": "size",
                        "label": "Розмір",
                        "type": "enum",
                        "options": ["S", "M", "L"],
                    }
                ],
            },
        )
        session.add(tpl)
        await session.flush()

        product = Product(shop_id=shop_id, name="Товар з шаблоном", template_id=tpl.id)
        session.add(product)
        await session.flush()

        v = Variant(
            shop_id=shop_id,
            product_id=product.id,
            price=Decimal("100"),
            axis_values={"size": "M"},
        )
        session.add(v)
        await session.flush()
        v_id = v.id
        await session.commit()
        return product.id, v_id


async def _add_variant_direct(
    shop_id: int, product_id: int, axis_values: dict
) -> int:
    async with db.async_session() as session:
        v = Variant(
            shop_id=shop_id,
            product_id=product_id,
            price=Decimal("100"),
            axis_values=axis_values,
        )
        session.add(v)
        await session.flush()
        v_id = v.id
        await session.commit()
        return v_id


async def _add_active_reservation(shop_id: int, variant_id: int) -> None:
    async with db.async_session() as session:
        res = Reservation(
            shop_id=shop_id,
            variant_id=variant_id,
            qty=1,
            status=ReservationStatus.active,
            source=ReservationSource.manual,
        )
        session.add(res)
        await session.commit()


# --------------------------------------------------------------------------- #
#  Test 1: PATCH price + sku + axis → 200, all fields saved
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_patch_price_sku_axis_ok(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90001)
    product_id, m_v_id = await _mk_product_with_size_template(shop_id)
    # Add a second variant so M→S change doesn't conflict
    await _add_variant_direct(shop_id, product_id, {"size": "L"})

    r = await client.patch(
        f"/api/variants/{m_v_id}",
        json={"price": "199.00", "sku": "SKU-M-001", "axis_values": {"size": "S"}},
        headers={HEADER: owner_init},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["price"] == "199.00"
    assert data["sku"] == "SKU-M-001"
    assert data["axis_values"] == {"size": "S"}

    # Verify persisted in DB
    async with db.async_session() as session:
        v = await session.get(Variant, m_v_id)
        assert v is not None
        assert v.price == Decimal("199.00")
        assert v.sku == "SKU-M-001"
        assert v.axis_values == {"size": "S"}


# --------------------------------------------------------------------------- #
#  Test 2: PATCH with on_hand in body — field is ignored by schema, value unchanged
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_patch_ignores_on_hand(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90011)
    _, [v_id] = await _mk_product(shop_id, n_variants=1)

    async with db.async_session() as session:
        v = await session.get(Variant, v_id)
        assert v is not None
        v.on_hand = 42
        await session.commit()

    # Send on_hand=99 in body — VariantPatch schema ignores it
    r = await client.patch(
        f"/api/variants/{v_id}",
        json={"price": "77.00", "on_hand": 99},
        headers={HEADER: owner_init},
    )
    assert r.status_code == 200
    assert r.json()["on_hand"] == 42  # unchanged


# --------------------------------------------------------------------------- #
#  Test 3: PATCH variant belonging to another shop → 404
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_patch_foreign_variant_404(client: AsyncClient) -> None:
    owner_init, _shop_id = await _bootstrap(client, tg_id=90021)
    _other_init, other_shop_id = await _bootstrap(client, tg_id=90022)
    _, [other_v_id] = await _mk_product(other_shop_id, n_variants=1)

    r = await client.patch(
        f"/api/variants/{other_v_id}",
        json={"price": "1.00"},
        headers={HEADER: owner_init},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
#  Test 4: PATCH axis to combination that already exists → 409
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_patch_axis_duplicate_409(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90031)
    product_id, m_v_id = await _mk_product_with_size_template(shop_id)
    # L variant already exists
    await _add_variant_direct(shop_id, product_id, {"size": "L"})

    # Try to PATCH M → L (L already taken by the other variant)
    r = await client.patch(
        f"/api/variants/{m_v_id}",
        json={"axis_values": {"size": "L"}},
        headers={HEADER: owner_init},
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  Test 5: POST add new variant to existing product → 201
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_add_variant_ok(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90041)
    product_id, _m_v_id = await _mk_product_with_size_template(shop_id)

    r = await client.post(
        f"/api/products/{product_id}/variants",
        json={"price": "120.00", "axis_values": {"size": "L"}, "sku": "NEW-L"},
        headers={HEADER: owner_init},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["axis_values"] == {"size": "L"}
    assert data["on_hand"] == 0
    assert data["sku"] == "NEW-L"
    assert data["price"] == "120.00"


# --------------------------------------------------------------------------- #
#  Test 6: POST with duplicate axis_values → 409
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_add_variant_duplicate_axis_409(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90051)
    product_id, _m_v_id = await _mk_product_with_size_template(shop_id)

    # M already exists — POSTing another M must be rejected
    r = await client.post(
        f"/api/products/{product_id}/variants",
        json={"price": "100.00", "axis_values": {"size": "M"}},
        headers={HEADER: owner_init},
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  Test 7: DELETE one of two variants (no reservations) → 204, gone from DB
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_delete_variant_ok(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90061)
    _, [v1_id, _v2_id] = await _mk_product(shop_id, n_variants=2)

    r = await client.delete(f"/api/variants/{v1_id}", headers={HEADER: owner_init})
    assert r.status_code == 204

    async with db.async_session() as session:
        assert await session.get(Variant, v1_id) is None


# --------------------------------------------------------------------------- #
#  Test 8: DELETE the only variant → 409
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_delete_last_variant_409(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90071)
    _, [only_v_id] = await _mk_product(shop_id, n_variants=1)

    r = await client.delete(f"/api/variants/{only_v_id}", headers={HEADER: owner_init})
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  Test 9: DELETE variant with active reservation → 409
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_delete_variant_active_reservation_409(client: AsyncClient) -> None:
    owner_init, shop_id = await _bootstrap(client, tg_id=90081)
    _, [v1_id, _v2_id] = await _mk_product(shop_id, n_variants=2)
    await _add_active_reservation(shop_id, v1_id)

    r = await client.delete(f"/api/variants/{v1_id}", headers={HEADER: owner_init})
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  Test 10: manager with can_edit_products=False → 403 on all three mutations
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_edit_products_variant_403(client: AsyncClient) -> None:
    _owner_init, shop_id = await _bootstrap(client, tg_id=90091)
    product_id, [v_id] = await _mk_product(shop_id, n_variants=1)
    mgr = await _make_manager(shop_id, 90092, can_edit_products=False)

    r_patch = await client.patch(
        f"/api/variants/{v_id}",
        json={"price": "1.00"},
        headers={HEADER: mgr},
    )
    assert r_patch.status_code == 403

    r_post = await client.post(
        f"/api/products/{product_id}/variants",
        json={"price": "1.00", "axis_values": {}},
        headers={HEADER: mgr},
    )
    assert r_post.status_code == 403

    r_delete = await client.delete(f"/api/variants/{v_id}", headers={HEADER: mgr})
    assert r_delete.status_code == 403
