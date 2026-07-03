"""
Стадія 3а — multi-shop: одна людина може мати Membership у кількох магазинах.

БД вже готова (UniqueConstraint("shop_id", "tg_id") композитний, tg_id НЕ
unique) — обмеження було лише в коді: resolve_membership брав перший-ліпший
membership, а invite-гілка не приєднувала existing юзера до нового магазину.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app import db
from app.models import MemberRole, Membership
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"
SHOP_HEADER = "X-Shop-Id"

_ALL_PERMS = [
    "can_view_inventory",
    "can_edit_products",
    "can_manage_reservations",
    "can_manage_stock",
    "can_view_finance",
    "can_manage_billing",
]


async def _bootstrap(
    client: AsyncClient, tg_id: int, *, start_param: str | None = None, first_name: str = "Тест"
) -> tuple[str, dict]:
    init_data = make_init_data(tg_id, first_name=first_name, start_param=start_param)
    if start_param is None:
        # Без invite-токена: явне створення (авто-bootstrap прибрано).
        # З токеном — join-гілка сама розрулить (existing/new-via-invite).
        r = await client.post(
            "/api/shops", headers={HEADER: init_data}, json={"name": f"Магазин {tg_id}"}
        )
        assert r.status_code == 201, r.text
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()


async def _create_invite(client: AsyncClient, owner_init_data: str) -> dict:
    r = await client.post("/api/team/invites", headers={HEADER: owner_init_data})
    assert r.status_code == 201, r.text
    return r.json()


async def _make_manager(shop_id: int, tg_id: int, **perms: bool) -> None:
    """Insert an ADDITIONAL Membership for tg_id in shop_id (multi-shop —
    the person may already own or manage other shops)."""
    m = Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager)
    for perm in _ALL_PERMS:
        setattr(m, perm, perms.get(perm, True))
    async with db.async_session() as s:
        s.add(m)
        await s.commit()


# --------------------------------------------------------------------------- #
#  Вибір активного магазину (X-Shop-Id)                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_no_header_picks_first_membership_deterministically(client: AsyncClient) -> None:
    init_data, me_a = await _bootstrap(client, 5001)
    shop_a = me_a["shop_id"]

    owner_b_init, _owner_b_me = await _bootstrap(client, 5002, first_name="Б")
    invite = await _create_invite(client, owner_b_init)
    join_init = make_init_data(5001, start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: join_init})
    assert r.status_code == 200
    assert r.json()["invite_status"] == "joined"
    shop_b = r.json()["shop_id"]
    assert shop_b != shop_a

    # без X-Shop-Id — перше (найменше id) membership: shop_a, створений раніше
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    assert r.json()["shop_id"] == shop_a

    # з X-Shop-Id=shop_b — саме він
    r = await client.get("/api/me", headers={HEADER: init_data, SHOP_HEADER: str(shop_b)})
    assert r.status_code == 200
    assert r.json()["shop_id"] == shop_b


@pytest.mark.asyncio
async def test_foreign_shop_id_returns_403(client: AsyncClient) -> None:
    init_data, _me = await _bootstrap(client, 5010)
    _other_init, other_me = await _bootstrap(client, 5011, first_name="Інший")

    r = await client.get(
        "/api/me", headers={HEADER: init_data, SHOP_HEADER: str(other_me["shop_id"])}
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Приєднання existing юзера до ІНШОГО магазину по інвайту                    #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_existing_owner_joins_another_shop_via_invite(client: AsyncClient) -> None:
    _owner_a_init, owner_a_me = await _bootstrap(client, 5020)
    owner_b_init, owner_b_me = await _bootstrap(client, 5021, first_name="Б")
    invite = await _create_invite(client, owner_b_init)

    join_init = make_init_data(5020, start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: join_init})
    assert r.status_code == 200
    body = r.json()

    assert body["invite_status"] == "joined"
    assert body["shop_id"] == owner_b_me["shop_id"]
    assert body["role"] == "manager"

    async with db.async_session() as s:
        new_membership = await s.scalar(
            select(Membership).where(
                Membership.tg_id == 5020, Membership.shop_id == owner_b_me["shop_id"]
            )
        )
    assert new_membership is not None
    assert new_membership.role == MemberRole.manager
    for perm in _ALL_PERMS:
        assert getattr(new_membership, perm) is True

    # Власний магазин лишається — це ДОДАТКОВЕ членство, не заміна.
    async with db.async_session() as s:
        own_membership = await s.scalar(
            select(Membership).where(
                Membership.tg_id == 5020, Membership.shop_id == owner_a_me["shop_id"]
            )
        )
    assert own_membership is not None
    assert own_membership.role == MemberRole.owner


@pytest.mark.asyncio
async def test_retapping_same_invite_gives_already_in_shop_no_duplicate(
    client: AsyncClient,
) -> None:
    _owner_a_init, _owner_a_me = await _bootstrap(client, 5030)
    owner_b_init, owner_b_me = await _bootstrap(client, 5031, first_name="Б")
    invite = await _create_invite(client, owner_b_init)

    join_init = make_init_data(5030, start_param=f"invite_{invite['token']}")
    r1 = await client.get("/api/me", headers={HEADER: join_init})
    assert r1.json()["invite_status"] == "joined"

    r2 = await client.get("/api/me", headers={HEADER: join_init})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["invite_status"] == "already_in_shop"
    assert body2["shop_id"] == owner_b_me["shop_id"]

    async with db.async_session() as s:
        count = len(
            (
                await s.scalars(
                    select(Membership).where(
                        Membership.tg_id == 5030, Membership.shop_id == owner_b_me["shop_id"]
                    )
                )
            ).all()
        )
    assert count == 1


@pytest.mark.asyncio
async def test_existing_user_with_dead_token_stays_in_own_shop_no_new_one(
    client: AsyncClient,
) -> None:
    init_data, me = await _bootstrap(client, 5040)

    dead_init = make_init_data(5040, start_param="invite_does-not-exist")
    r = await client.get("/api/me", headers={HEADER: dead_init})
    assert r.status_code == 200
    body = r.json()

    assert body["invite_status"] == "invite_invalid"
    assert body["shop_id"] == me["shop_id"]

    async with db.async_session() as s:
        memberships_count = await s.scalar(
            select(func.count(Membership.id)).where(Membership.tg_id == 5040)
        )
    assert memberships_count == 1

    # header лишається робочим на своєму магазині
    r2 = await client.get("/api/me", headers={HEADER: init_data})
    assert r2.json()["shop_id"] == me["shop_id"]


# --------------------------------------------------------------------------- #
#  /api/me — shops[] + active_shop_id                                         #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_me_lists_all_shops_and_active_shop_id(client: AsyncClient) -> None:
    owner_a_init, owner_a_me = await _bootstrap(client, 5050)
    owner_b_init, owner_b_me = await _bootstrap(client, 5051, first_name="Б")
    invite = await _create_invite(client, owner_b_init)

    join_init = make_init_data(5050, start_param=f"invite_{invite['token']}")
    await client.get("/api/me", headers={HEADER: join_init})  # consume invite

    r = await client.get("/api/me", headers={HEADER: owner_a_init})
    assert r.status_code == 200
    body = r.json()

    shop_ids = {s["shop_id"] for s in body["shops"]}
    assert shop_ids == {owner_a_me["shop_id"], owner_b_me["shop_id"]}
    assert body["active_shop_id"] == owner_a_me["shop_id"]

    roles_by_shop = {s["shop_id"]: s["role"] for s in body["shops"]}
    assert roles_by_shop[owner_a_me["shop_id"]] == "owner"
    assert roles_by_shop[owner_b_me["shop_id"]] == "manager"

    r2 = await client.get(
        "/api/me", headers={HEADER: owner_a_init, SHOP_HEADER: str(owner_b_me["shop_id"])}
    )
    assert r2.status_code == 200
    assert r2.json()["active_shop_id"] == owner_b_me["shop_id"]
    assert r2.json()["shop_id"] == owner_b_me["shop_id"]


# --------------------------------------------------------------------------- #
#  Гейти — права різні в різних магазинах                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_permissions_are_scoped_per_shop(client: AsyncClient) -> None:
    owner_a_init, _owner_a_me = await _bootstrap(client, 5060)
    _owner_b_init, owner_b_me = await _bootstrap(client, 5061, first_name="Б")

    # Той самий tg_id — owner у A, manager БЕЗ can_view_finance у B.
    await _make_manager(owner_b_me["shop_id"], 5060, can_view_finance=False)

    r = await client.get("/api/finance/summary", headers={HEADER: owner_a_init})
    assert r.status_code == 200

    r = await client.get(
        "/api/finance/summary",
        headers={HEADER: owner_a_init, SHOP_HEADER: str(owner_b_me["shop_id"])},
    )
    assert r.status_code == 403
