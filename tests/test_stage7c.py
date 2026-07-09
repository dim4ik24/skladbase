"""
Stage 7c acceptance tests (backend half: subscription summary, is_demo, clear-demos).

Criteria:
  1. GET /api/me віддає зведення підписки: status, is_writable, trial_ends_at,
     current_period_end, plan_code (новий магазин -> trial, is_writable=True)
  2. ProductOut містить is_demo
  3. POST /api/shop/clear-demos прибирає лише is_demo товари свого магазину
     (ізоляція — товари іншого магазину не зачіпає), require_owner (manager -> 403)
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app import db
from app.models import MemberRole, Membership
from tests.conftest import get_system_role_id, make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


@pytest.mark.asyncio
async def test_me_returns_subscription_summary(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 7001)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "trial"
    assert body["is_writable"] is True
    assert body["trial_ends_at"] is not None
    assert body["current_period_end"] is not None
    assert body["plan_code"] is None


@pytest.mark.asyncio
async def test_product_out_includes_is_demo(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 7002)

    r_seeded = await client.get("/api/products", headers={HEADER: init_data})
    assert r_seeded.status_code == 200
    seeded = r_seeded.json()
    assert all("is_demo" in p for p in seeded)
    assert any(p["is_demo"] for p in seeded)

    payload = {"name": "Свій товар", "variants": [{"axis_values": {}, "price": "10"}]}
    r_created = await client.post("/api/products", json=payload, headers={HEADER: init_data})
    assert r_created.status_code == 201
    assert r_created.json()["is_demo"] is False


@pytest.mark.asyncio
async def test_clear_demos_removes_only_own_shop_demo_products(client: AsyncClient) -> None:
    init_data_a, _shop_a = await _bootstrap(client, 7101, "Шоп А")
    init_data_b, _shop_b = await _bootstrap(client, 7102, "Шоп Б")

    own_payload = {"name": "Не демо", "variants": [{"axis_values": {}, "price": "10"}]}
    r_own = await client.post("/api/products", json=own_payload, headers={HEADER: init_data_a})
    assert r_own.status_code == 201

    r_before_b = await client.get("/api/products", headers={HEADER: init_data_b})
    demo_count_b_before = sum(1 for p in r_before_b.json() if p["is_demo"])
    assert demo_count_b_before > 0

    r_clear = await client.post("/api/shop/clear-demos", headers={HEADER: init_data_a})
    assert r_clear.status_code == 200
    assert r_clear.json()["removed"] == 2  # засіяні демо: футболка + свічка

    r_after_a = await client.get("/api/products", headers={HEADER: init_data_a})
    products_a = r_after_a.json()
    assert all(not p["is_demo"] for p in products_a)
    assert any(p["name"] == "Не демо" for p in products_a)

    r_after_b = await client.get("/api/products", headers={HEADER: init_data_b})
    demo_count_b_after = sum(1 for p in r_after_b.json() if p["is_demo"])
    assert demo_count_b_after == demo_count_b_before  # інший магазин не зачепило


@pytest.mark.asyncio
async def test_clear_demos_requires_owner(client: AsyncClient) -> None:
    owner_init_data, shop_id = await _bootstrap(client, 7201, "Власник")

    manager_tg_id = 7202
    role_id = await get_system_role_id(shop_id, "Менеджер")
    async with db.async_session() as session:
        session.add(
            Membership(
                shop_id=shop_id, tg_id=manager_tg_id, role=MemberRole.manager, role_id=role_id
            )
        )
        await session.commit()

    manager_init_data = make_init_data(manager_tg_id, first_name="Менеджер")

    r_manager = await client.post("/api/shop/clear-demos", headers={HEADER: manager_init_data})
    assert r_manager.status_code == 403

    r_owner = await client.post("/api/shop/clear-demos", headers={HEADER: owner_init_data})
    assert r_owner.status_code == 200
    assert r_owner.json()["removed"] == 2
