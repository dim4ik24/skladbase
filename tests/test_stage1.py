"""
Stage 1 acceptance tests (auth + tenancy).

Criteria (ROADMAP.md, Стадія 1):
  1. Підроблений або протермінований initData -> 401
  2. Валідний initData -> резолвиться правильний shop_id
  3. manager отримує 403 на /api/finance/summary, owner -> 200

  (Демо-каталог + 7-денний тріал нового магазину — тепер
  tests/test_shop_lifecycle.py, POST /api/shops.)
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app import db
from app.models import MemberRole, Membership, utcnow
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


@pytest.mark.asyncio
async def test_forged_init_data_returns_401(client: AsyncClient) -> None:
    init_data = make_init_data(111, tamper_hash=True)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_expired_init_data_returns_401(client: AsyncClient) -> None:
    stale_auth_date = int((utcnow() - timedelta(hours=48)).timestamp())
    init_data = make_init_data(112, auth_date=stale_auth_date)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_valid_init_data_resolves_correct_shop(client: AsyncClient) -> None:
    init_data_a = make_init_data(201, first_name="Аліса")
    init_data_b = make_init_data(202, first_name="Боб")

    r = await client.post("/api/shops", headers={HEADER: init_data_a}, json={"name": "Магазин А"})
    assert r.status_code == 201, r.text
    r = await client.post("/api/shops", headers={HEADER: init_data_b}, json={"name": "Магазин Б"})
    assert r.status_code == 201, r.text

    r_a = await client.get("/api/me", headers={HEADER: init_data_a})
    r_b = await client.get("/api/me", headers={HEADER: init_data_b})

    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.json()["shop_id"] != r_b.json()["shop_id"]

    # повторний вхід тим самим tg_id резолвиться у той самий shop_id, без повторного bootstrap
    r_a_again = await client.get("/api/me", headers={HEADER: init_data_a})
    assert r_a_again.json()["shop_id"] == r_a.json()["shop_id"]


@pytest.mark.asyncio
async def test_finance_access_by_role(client: AsyncClient) -> None:
    """Stage 1b: GET /finance/summary uses require_permission(can_view_finance).
    Manager with default can_view_finance=True → 200 (same as owner).
    Granular 403 (can_view_finance=False) is in test_permissions_gates.py."""
    owner_init_data = make_init_data(301, first_name="Власник")
    r = await client.post(
        "/api/shops", headers={HEADER: owner_init_data}, json={"name": "Магазин Власника"}
    )
    assert r.status_code == 201, r.text
    r_owner = await client.get("/api/me", headers={HEADER: owner_init_data})
    shop_id = r_owner.json()["shop_id"]

    manager_tg_id = 302
    async with db.async_session() as session:
        session.add(
            Membership(
                shop_id=shop_id,
                tg_id=manager_tg_id,
                role=MemberRole.manager,
            )
        )
        await session.commit()

    manager_init_data = make_init_data(manager_tg_id, first_name="Менеджер")

    # Manager with default can_view_finance=True → 200 (not 403 since Stage 1b)
    r_manager = await client.get("/api/finance/summary", headers={HEADER: manager_init_data})
    assert r_manager.status_code == 200

    r_owner_finance = await client.get("/api/finance/summary", headers={HEADER: owner_init_data})
    assert r_owner_finance.status_code == 200

# test_new_shop_gets_demo_catalog_and_seven_day_trial перенесено у
# test_shop_lifecycle.py — тепер це природно тест POST /api/shops,
# а не побічного ефекту GET /api/me (авто-bootstrap прибрано).
