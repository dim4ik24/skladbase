"""
Стадія 2а — deep-link інвайти (t.me/<bot>?startapp=invite_<token>) + керування
командою (app/api/team.py). Усі ендпоінти — лише owner (require_owner).
"""
from __future__ import annotations

import secrets
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db
from app.models import Invite, MemberRole, Membership, Shop, utcnow
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


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


async def _make_manager(shop_id: int, tg_id: int) -> str:
    m = Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager)
    async with db.async_session() as s:
        s.add(m)
        await s.commit()
    return make_init_data(tg_id)


async def _create_invite(client: AsyncClient, owner_init_data: str) -> dict:
    r = await client.post("/api/team/invites", headers={HEADER: owner_init_data})
    assert r.status_code == 201, r.text
    return r.json()


async def _insert_invite(
    shop_id: int, *, expires_delta: timedelta = timedelta(hours=48), revoked: bool = False
) -> Invite:
    invite = Invite(
        shop_id=shop_id,
        token=secrets.token_urlsafe(16),
        created_by_tg_id=1,
        expires_at=utcnow() + expires_delta,
        revoked_at=utcnow() if revoked else None,
    )
    async with db.async_session() as s:
        s.add(invite)
        await s.commit()
    return invite


# --------------------------------------------------------------------------- #
#  Створення / список / revoke                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_owner_creates_invite_with_correct_url(client: AsyncClient) -> None:
    init_data, _me = await _bootstrap(client, 3001)

    r = await client.post("/api/team/invites", headers={HEADER: init_data})
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["token"]
    assert body["url"] == f"https://t.me/sklad_base_bot?startapp=invite_{body['token']}"
    assert "expires_at" in body


@pytest.mark.asyncio
async def test_manager_cannot_create_invite(client: AsyncClient) -> None:
    _owner_init, owner_me = await _bootstrap(client, 3002)
    manager_init = await _make_manager(owner_me["shop_id"], 3003)

    r = await client.post("/api/team/invites", headers={HEADER: manager_init})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_invites_hides_revoked_and_expired(client: AsyncClient) -> None:
    init_data, me = await _bootstrap(client, 3010)

    active = await _create_invite(client, init_data)
    revoked = await _create_invite(client, init_data)
    r = await client.delete(f"/api/team/invites/{revoked['id']}", headers={HEADER: init_data})
    assert r.status_code == 204

    expired = await _insert_invite(me["shop_id"], expires_delta=timedelta(hours=-1))

    r = await client.get("/api/team/invites", headers={HEADER: init_data})
    assert r.status_code == 200
    tokens = {inv["token"] for inv in r.json()}

    assert active["token"] in tokens
    assert revoked["token"] not in tokens
    assert expired.token not in tokens


@pytest.mark.asyncio
async def test_revoke_invite_then_token_no_longer_joins(client: AsyncClient) -> None:
    """Відкликаний токен для НОВОГО юзера — авто-bootstrap-у нема (shop lifecycle),
    тож замість тихого створення власної крамниці -> 404 no_shop, магазин не виникає."""
    init_data, _me = await _bootstrap(client, 3020)
    invite = await _create_invite(client, init_data)

    r = await client.delete(f"/api/team/invites/{invite['id']}", headers={HEADER: init_data})
    assert r.status_code == 204

    joiner_init = make_init_data(3021, start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: joiner_init})
    assert r.status_code == 404

    async with db.async_session() as session:
        own_shops = (await session.scalars(select(Shop).where(Shop.owner_tg_id == 3021))).all()
    assert own_shops == []


@pytest.mark.asyncio
async def test_revoke_invite_wrong_shop_returns_404(client: AsyncClient) -> None:
    owner_a_init, _owner_a_me = await _bootstrap(client, 3030)
    owner_b_init, _owner_b_me = await _bootstrap(client, 3031, first_name="Б")
    invite_a = await _create_invite(client, owner_a_init)

    r = await client.delete(f"/api/team/invites/{invite_a['id']}", headers={HEADER: owner_b_init})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_revoke_missing_invite_returns_404(client: AsyncClient) -> None:
    init_data, _me = await _bootstrap(client, 3032)
    r = await client.delete("/api/team/invites/999999", headers={HEADER: init_data})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
#  Приєднання по інвайту (bootstrap)                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_join_via_valid_invite_creates_manager_in_invite_shop(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3040)
    invite = await _create_invite(client, owner_init)

    joiner_init = make_init_data(3041, start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: joiner_init})
    assert r.status_code == 200
    body = r.json()

    assert body["invite_status"] == "joined"
    assert body["shop_id"] == owner_me["shop_id"]
    assert body["role"] == "manager"

    async with db.async_session() as s:
        membership = await s.scalar(select(Membership).where(Membership.tg_id == 3041))
    assert membership is not None
    assert membership.shop_id == owner_me["shop_id"]
    assert membership.role == MemberRole.manager
    for perm in (
        "can_view_inventory", "can_edit_products", "can_manage_reservations",
        "can_manage_stock", "can_view_finance", "can_manage_billing",
    ):
        assert getattr(membership, perm) is True


@pytest.mark.asyncio
async def test_invite_is_reusable_by_multiple_users(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3050)
    invite = await _create_invite(client, owner_init)

    for tg_id in (3051, 3052):
        joiner_init = make_init_data(tg_id, start_param=f"invite_{invite['token']}")
        r = await client.get("/api/me", headers={HEADER: joiner_init})
        assert r.status_code == 200
        body = r.json()
        assert body["invite_status"] == "joined"
        assert body["shop_id"] == owner_me["shop_id"]
        assert body["role"] == "manager"


@pytest.mark.asyncio
async def test_join_with_expired_token_gets_no_shop(client: AsyncClient) -> None:
    """Протермінований токен для НОВОГО юзера — те саме: 404 no_shop, а не
    тиха власна крамниця (авто-bootstrap прибрано, shop lifecycle)."""
    _owner_init, owner_me = await _bootstrap(client, 3060)
    invite = await _insert_invite(owner_me["shop_id"], expires_delta=timedelta(hours=-1))

    joiner_init = make_init_data(3061, start_param=f"invite_{invite.token}")
    r = await client.get("/api/me", headers={HEADER: joiner_init})
    assert r.status_code == 404

    async with db.async_session() as session:
        own_shops = (await session.scalars(select(Shop).where(Shop.owner_tg_id == 3061))).all()
    assert own_shops == []


@pytest.mark.asyncio
async def test_no_start_param_gives_none_invite_status(client: AsyncClient) -> None:
    _init_data, me = await _bootstrap(client, 3065)
    assert me["invite_status"] is None


@pytest.mark.asyncio
async def test_member_retapping_own_shop_invite_gets_already_in_shop(client: AsyncClient) -> None:
    """Multi-shop (Стадія 3а): re-tap інвайту СВОГО Ж магазину не дублює
    Membership. (Приєднання до ІНШОГО магазину — tests/test_multi_shop.py,
    там "joined", а не "already_in_shop".)"""
    owner_init, owner_me = await _bootstrap(client, 3070)
    invite = await _create_invite(client, owner_init)

    retap_init = make_init_data(3070, start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: retap_init})
    assert r.status_code == 200
    body = r.json()

    assert body["invite_status"] == "already_in_shop"
    assert body["shop_id"] == owner_me["shop_id"]

    async with db.async_session() as s:
        count = len(
            (
                await s.scalars(
                    select(Membership).where(
                        Membership.tg_id == 3070, Membership.shop_id == owner_me["shop_id"]
                    )
                )
            ).all()
        )
    assert count == 1


# --------------------------------------------------------------------------- #
#  Учасники                                                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_owner_sees_member_list(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3080)
    await _make_manager(owner_me["shop_id"], 3081)

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    assert r.status_code == 200
    tg_ids = {m["tg_id"] for m in r.json()}
    assert {3080, 3081} <= tg_ids


@pytest.mark.asyncio
async def test_owner_deletes_member(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3090)
    await _make_manager(owner_me["shop_id"], 3091)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3091))
    r = await client.delete(f"/api/team/members/{member.id}", headers={HEADER: owner_init})
    assert r.status_code == 204

    async with db.async_session() as s:
        gone = await s.scalar(select(Membership).where(Membership.tg_id == 3091))
    assert gone is None


@pytest.mark.asyncio
async def test_owner_cannot_delete_self(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3100)

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    owner_membership_id = next(m["id"] for m in r.json() if m["tg_id"] == 3100)

    r = await client.delete(
        f"/api/team/members/{owner_membership_id}", headers={HEADER: owner_init}
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_cannot_delete_a_membership_with_owner_role(client: AsyncClient) -> None:
    """Захист незалежний від self-check: один магазин має рівно одного owner
    архітектурно, але ендпоінт відмовляє за role==owner саме по собі, не лише
    через збіг id."""
    owner_init, owner_me = await _bootstrap(client, 3110)

    other_owner = Membership(shop_id=owner_me["shop_id"], tg_id=3111, role=MemberRole.owner)
    async with db.async_session() as s:
        s.add(other_owner)
        await s.commit()

    async with db.async_session() as s:
        other_owner_row = await s.scalar(select(Membership).where(Membership.tg_id == 3111))
    r = await client.delete(
        f"/api/team/members/{other_owner_row.id}", headers={HEADER: owner_init}
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_manager_cannot_list_or_delete_members(client: AsyncClient) -> None:
    _owner_init, owner_me = await _bootstrap(client, 3120)
    manager_init = await _make_manager(owner_me["shop_id"], 3121)

    r = await client.get("/api/team/members", headers={HEADER: manager_init})
    assert r.status_code == 403

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3121))
    r = await client.delete(f"/api/team/members/{member.id}", headers={HEADER: manager_init})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Дозволи (Стадія 3) — PATCH /members/{id}/permissions                       #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_owner_revokes_finance_permission_and_gate_takes_effect(
    client: AsyncClient,
) -> None:
    owner_init, owner_me = await _bootstrap(client, 3130)
    manager_init = await _make_manager(owner_me["shop_id"], 3131)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3131))

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_view_finance"] is False
    # решта прапорів лишились True (частковий патч)
    assert body["can_view_inventory"] is True
    assert body["can_manage_billing"] is True

    r = await client.get("/api/finance/summary", headers={HEADER: manager_init})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_permissions_on_owner_returns_409(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3140)

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    owner_membership_id = next(m["id"] for m in r.json() if m["tg_id"] == 3140)

    r = await client.patch(
        f"/api/team/members/{owner_membership_id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_patch_permissions_wrong_shop_returns_404(client: AsyncClient) -> None:
    owner_a_init, _owner_a_me = await _bootstrap(client, 3150)
    _owner_b_init, owner_b_me = await _bootstrap(client, 3151, first_name="Б")
    await _make_manager(owner_b_me["shop_id"], 3152)

    async with db.async_session() as s:
        member_b = await s.scalar(select(Membership).where(Membership.tg_id == 3152))

    r = await client.patch(
        f"/api/team/members/{member_b.id}/permissions",
        headers={HEADER: owner_a_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_permissions_missing_member_returns_404(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3160)

    r = await client.patch(
        "/api/team/members/999999/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_manager_cannot_patch_permissions(client: AsyncClient) -> None:
    _owner_init, owner_me = await _bootstrap(client, 3170)
    manager_init = await _make_manager(owner_me["shop_id"], 3171)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3171))

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: manager_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_permissions_partial_update_does_not_touch_other_fields(
    client: AsyncClient,
) -> None:
    owner_init, owner_me = await _bootstrap(client, 3180)
    await _make_manager(owner_me["shop_id"], 3181)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3181))

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_manage_stock": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_manage_stock"] is False
    for perm in (
        "can_view_inventory", "can_edit_products", "can_manage_reservations",
        "can_view_finance", "can_manage_billing",
    ):
        assert body[perm] is True
