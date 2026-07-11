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
from app.models import Invite, MemberRole, Membership, Role, utcnow
from tests.conftest import get_system_role_id, make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(
    client: AsyncClient, tg_id: int, *, start_param: str | None = None, first_name: str = "Тест"
) -> tuple[str, dict]:
    init_data = make_init_data(tg_id, first_name=first_name, start_param=start_param)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()


async def _make_manager(shop_id: int, tg_id: int) -> str:
    role_id = await get_system_role_id(shop_id, "Менеджер")
    m = Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager, role_id=role_id)
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
    init_data, me = await _bootstrap(client, 3020)
    invite = await _create_invite(client, init_data)

    r = await client.delete(f"/api/team/invites/{invite['id']}", headers={HEADER: init_data})
    assert r.status_code == 204

    joiner_init = make_init_data(3021, start_param=f"invite_{invite['token']}")
    r = await client.get("/api/me", headers={HEADER: joiner_init})
    assert r.status_code == 200
    body = r.json()

    assert body["invite_status"] == "invite_invalid"
    assert body["shop_id"] != me["shop_id"]  # своя нова крамниця, приєднання не відбулось


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
        role = await s.get(Role, membership.role_id)
    assert membership.shop_id == owner_me["shop_id"]
    assert membership.role == MemberRole.manager
    # Права тепер живуть на role_ref, не на can_*-колонках Membership —
    # інвайт садить у системну роль "Менеджер" свого магазину.
    assert role is not None
    assert role.name == "Менеджер"
    assert role.shop_id == owner_me["shop_id"]
    assert role.is_system is True
    for perm in (
        "can_view_inventory", "can_edit_products", "can_manage_reservations",
        "can_manage_stock", "can_view_finance", "can_manage_billing",
    ):
        assert getattr(role, perm) is True


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
async def test_join_with_expired_token_creates_own_shop(client: AsyncClient) -> None:
    _owner_init, owner_me = await _bootstrap(client, 3060)
    invite = await _insert_invite(owner_me["shop_id"], expires_delta=timedelta(hours=-1))

    joiner_init = make_init_data(3061, start_param=f"invite_{invite.token}")
    r = await client.get("/api/me", headers={HEADER: joiner_init})
    assert r.status_code == 200
    body = r.json()

    assert body["invite_status"] == "invite_invalid"
    assert body["shop_id"] != owner_me["shop_id"]
    assert body["role"] == "owner"


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

    owner_role_id = await get_system_role_id(owner_me["shop_id"], "Власник")
    other_owner = Membership(
        shop_id=owner_me["shop_id"], tg_id=3111, role=MemberRole.owner, role_id=owner_role_id
    )
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
#  Кастомні ролі (Стадія 3b) — GET/POST/PATCH/DELETE /roles,                  #
#  PATCH /members/{id}/role (замінює старий PATCH .../permissions)            #
# --------------------------------------------------------------------------- #
async def _create_role(client: AsyncClient, owner_init: str, **payload: object) -> dict:
    body = {"name": "Тест-роль", **payload}
    r = await client.post("/api/team/roles", headers={HEADER: owner_init}, json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_owner_creates_custom_role(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3200)

    role = await _create_role(
        client, owner_init, name="Продавець", can_view_finance=False, can_manage_billing=False,
    )
    assert role["name"] == "Продавець"
    assert role["can_view_finance"] is False
    assert role["can_manage_billing"] is False
    assert role["can_view_inventory"] is True  # дефолт (не передавали)
    assert role["is_system"] is False
    assert role["members_count"] == 0


@pytest.mark.asyncio
async def test_create_role_duplicate_name_returns_409(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3201)

    r = await client.post(
        "/api/team/roles", headers={HEADER: owner_init}, json={"name": "Менеджер"}
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_roles_includes_system_roles_and_members_count(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3210)
    await _make_manager(owner_me["shop_id"], 3211)

    r = await client.get("/api/team/roles", headers={HEADER: owner_init})
    assert r.status_code == 200
    roles_by_name = {role["name"]: role for role in r.json()}
    assert {"Власник", "Менеджер"} <= set(roles_by_name)
    assert roles_by_name["Власник"]["is_system"] is True
    assert roles_by_name["Власник"]["members_count"] == 1
    assert roles_by_name["Менеджер"]["members_count"] == 1


@pytest.mark.asyncio
async def test_manager_cannot_list_roles(client: AsyncClient) -> None:
    _owner_init, owner_me = await _bootstrap(client, 3212)
    manager_init = await _make_manager(owner_me["shop_id"], 3213)

    r = await client.get("/api/team/roles", headers={HEADER: manager_init})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_owner_assigns_role_and_gate_takes_effect(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3220)
    manager_init = await _make_manager(owner_me["shop_id"], 3221)
    role = await _create_role(client, owner_init, name="Без фінансів", can_view_finance=False)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3221))

    r = await client.patch(
        f"/api/team/members/{member.id}/role",
        headers={HEADER: owner_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role_id"] == role["id"]
    assert body["role_name"] == "Без фінансів"
    assert body["can_view_finance"] is False

    r = await client.get("/api/finance/summary", headers={HEADER: manager_init})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_editing_role_changes_all_holders_effective_permissions(
    client: AsyncClient,
) -> None:
    """Редагування ролі одразу міняє права ВСІХ її носіїв — без окремого
    перепризначення кожному."""
    owner_init, owner_me = await _bootstrap(client, 3280)
    manager1_init = await _make_manager(owner_me["shop_id"], 3281)
    manager2_init = await _make_manager(owner_me["shop_id"], 3282)
    role = await _create_role(client, owner_init, name="Спільна роль")

    async with db.async_session() as s:
        member1 = await s.scalar(select(Membership).where(Membership.tg_id == 3281))
        member2 = await s.scalar(select(Membership).where(Membership.tg_id == 3282))

    for member in (member1, member2):
        r = await client.patch(
            f"/api/team/members/{member.id}/role",
            headers={HEADER: owner_init},
            json={"role_id": role["id"]},
        )
        assert r.status_code == 200, r.text

    for init in (manager1_init, manager2_init):
        r = await client.get("/api/finance/summary", headers={HEADER: init})
        assert r.status_code == 200

    r = await client.patch(
        f"/api/team/roles/{role['id']}",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text

    for init in (manager1_init, manager2_init):
        r = await client.get("/api/finance/summary", headers={HEADER: init})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_editing_role_does_not_touch_overridden_member_fields(
    client: AsyncClient,
) -> None:
    """Фіча 3c, п.4 ТЗ: редагування ролі змінює ефективні права носіїв КРІМ
    полів з індивідуальним override — той override завжди перемагає, хоч би
    що сталось з роллю."""
    owner_init, owner_me = await _bootstrap(client, 3283)
    await _make_manager(owner_me["shop_id"], 3284)
    role = await _create_role(client, owner_init, name="Спільна роль 2", can_view_finance=True)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3284))

    r = await client.patch(
        f"/api/team/members/{member.id}/role",
        headers={HEADER: owner_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 200, r.text

    # Override: ЦІЙ людині фінанси заборонені, попри те що роль дозволяє.
    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["can_view_finance"] is False
    assert "can_view_finance" in r.json()["overridden"]

    # Роль тепер теж забороняє фінанси — override все одно False (не зміна,
    # бо вже був False), але важливо, що can_edit_products (без override)
    # МІНЯЄТЬСЯ разом з роллю.
    r = await client.patch(
        f"/api/team/roles/{role['id']}",
        headers={HEADER: owner_init},
        json={"can_view_finance": False, "can_edit_products": False},
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    member_out = next(m for m in r.json() if m["tg_id"] == 3284)
    assert member_out["can_view_finance"] is False  # override, лишається False
    assert member_out["can_edit_products"] is False  # не override — пішло за роллю
    assert member_out["overridden"] == ["can_view_finance"]

    # Тепер роль повертає фінанси і редагування товарів назад у True —
    # override все одно тримає can_view_finance у False.
    r = await client.patch(
        f"/api/team/roles/{role['id']}",
        headers={HEADER: owner_init},
        json={"can_view_finance": True, "can_edit_products": True},
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    member_out = next(m for m in r.json() if m["tg_id"] == 3284)
    assert member_out["can_view_finance"] is False  # override все одно перемагає
    assert member_out["can_edit_products"] is True  # роль повернула True — і це теж


@pytest.mark.asyncio
async def test_patch_member_permissions_sets_override(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3285)
    manager_init = await _make_manager(owner_me["shop_id"], 3286)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3286))

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_view_finance"] is False
    assert body["overridden"] == ["can_view_finance"]
    # Решта прав лишились роль-дефолтними (True) — override torкнувся лише
    # цього одного поля.
    assert body["can_edit_products"] is True

    r = await client.get("/api/finance/summary", headers={HEADER: manager_init})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_member_permissions_null_resets_to_role(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3287)
    await _make_manager(owner_me["shop_id"], 3288)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3288))

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["overridden"] == ["can_view_finance"]

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_view_finance"] is True  # роль "Менеджер" дозволяє
    assert body["overridden"] == []


@pytest.mark.asyncio
async def test_patch_member_permissions_on_owner_returns_409(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3289)

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    owner_membership_id = next(m["id"] for m in r.json() if m["tg_id"] == 3289)

    r = await client.patch(
        f"/api/team/members/{owner_membership_id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_changing_role_resets_overrides(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3292)
    manager_init = await _make_manager(owner_me["shop_id"], 3293)
    role = await _create_role(client, owner_init, name="Нова роль", can_view_finance=True)

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3293))

    r = await client.patch(
        f"/api/team/members/{member.id}/permissions",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["overridden"] == ["can_view_finance"]

    r = await client.get("/api/finance/summary", headers={HEADER: manager_init})
    assert r.status_code == 403  # override діє

    r = await client.patch(
        f"/api/team/members/{member.id}/role",
        headers={HEADER: owner_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overridden"] == []  # скинуто одночасно з призначенням ролі
    assert body["can_view_finance"] is True  # нова роль дозволяє, override зник

    r = await client.get("/api/finance/summary", headers={HEADER: manager_init})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_patch_manager_system_role_returns_200(client: AsyncClient) -> None:
    """Розворот рішення (фіча 3c): 'Менеджер' — теж is_system=True, але тепер
    редагується як звичайна кастомна роль. Незмінна лишається тільки
    'Власник'."""
    owner_init, _owner_me = await _bootstrap(client, 3290)

    r = await client.get("/api/team/roles", headers={HEADER: owner_init})
    manager_role_id = next(role["id"] for role in r.json() if role["name"] == "Менеджер")

    r = await client.patch(
        f"/api/team/roles/{manager_role_id}",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_system"] is True  # лишається системною (бейдж), просто не заблокована
    assert body["can_view_finance"] is False


@pytest.mark.asyncio
async def test_patch_owner_role_returns_403(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3291)

    r = await client.get("/api/team/roles", headers={HEADER: owner_init})
    owner_role_id = next(role["id"] for role in r.json() if role["name"] == "Власник")

    r = await client.patch(
        f"/api/team/roles/{owner_role_id}",
        headers={HEADER: owner_init},
        json={"can_view_finance": False},
    )
    assert r.status_code == 403

    r = await client.patch(
        f"/api/team/roles/{owner_role_id}",
        headers={HEADER: owner_init},
        json={"name": "Перейменована"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_member_role_on_owner_returns_409(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3230)
    role = await _create_role(client, owner_init, name="Інша роль")

    r = await client.get("/api/team/members", headers={HEADER: owner_init})
    owner_membership_id = next(m["id"] for m in r.json() if m["tg_id"] == 3230)

    r = await client.patch(
        f"/api/team/members/{owner_membership_id}/role",
        headers={HEADER: owner_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_patch_member_role_wrong_shop_member_returns_404(client: AsyncClient) -> None:
    owner_a_init, _owner_a_me = await _bootstrap(client, 3240)
    _owner_b_init, owner_b_me = await _bootstrap(client, 3241, first_name="Б")
    await _make_manager(owner_b_me["shop_id"], 3242)
    role = await _create_role(client, owner_a_init, name="Роль А")

    async with db.async_session() as s:
        member_b = await s.scalar(select(Membership).where(Membership.tg_id == 3242))

    r = await client.patch(
        f"/api/team/members/{member_b.id}/role",
        headers={HEADER: owner_a_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_member_role_foreign_role_returns_404(client: AsyncClient) -> None:
    owner_a_init, owner_a_me = await _bootstrap(client, 3250)
    owner_b_init, _owner_b_me = await _bootstrap(client, 3251, first_name="Б")
    await _make_manager(owner_a_me["shop_id"], 3252)
    role_b = await _create_role(client, owner_b_init, name="Роль Б")

    async with db.async_session() as s:
        member_a = await s.scalar(select(Membership).where(Membership.tg_id == 3252))

    r = await client.patch(
        f"/api/team/members/{member_a.id}/role",
        headers={HEADER: owner_a_init},
        json={"role_id": role_b["id"]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_member_role_missing_member_returns_404(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3260)
    role = await _create_role(client, owner_init, name="Роль")

    r = await client.patch(
        "/api/team/members/999999/role",
        headers={HEADER: owner_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_manager_cannot_patch_member_role(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3270)
    manager_init = await _make_manager(owner_me["shop_id"], 3271)
    role = await _create_role(client, owner_init, name="Роль")

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3271))

    r = await client.patch(
        f"/api/team/members/{member.id}/role",
        headers={HEADER: manager_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_system_role_returns_409(client: AsyncClient) -> None:
    """DELETE лишається забороненим для ОБОХ системних ролей (на відміну
    від PATCH, де тепер дозволено 'Менеджер' — тільки не 'Власник')."""
    owner_init, _owner_me = await _bootstrap(client, 3300)

    r = await client.get("/api/team/roles", headers={HEADER: owner_init})
    roles_by_name = {role["name"]: role["id"] for role in r.json()}

    for name in ("Менеджер", "Власник"):
        r = await client.delete(
            f"/api/team/roles/{roles_by_name[name]}", headers={HEADER: owner_init}
        )
        assert r.status_code == 409, f"{name}: {r.text}"


@pytest.mark.asyncio
async def test_delete_role_with_holders_returns_409(client: AsyncClient) -> None:
    owner_init, owner_me = await _bootstrap(client, 3310)
    await _make_manager(owner_me["shop_id"], 3311)
    role = await _create_role(client, owner_init, name="Роль з носієм")

    async with db.async_session() as s:
        member = await s.scalar(select(Membership).where(Membership.tg_id == 3311))
    r = await client.patch(
        f"/api/team/members/{member.id}/role",
        headers={HEADER: owner_init},
        json={"role_id": role["id"]},
    )
    assert r.status_code == 200, r.text

    r = await client.delete(f"/api/team/roles/{role['id']}", headers={HEADER: owner_init})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_delete_role_without_holders_ok(client: AsyncClient) -> None:
    owner_init, _owner_me = await _bootstrap(client, 3320)
    role = await _create_role(client, owner_init, name="Порожня роль")

    r = await client.delete(f"/api/team/roles/{role['id']}", headers={HEADER: owner_init})
    assert r.status_code == 204

    r = await client.get("/api/team/roles", headers={HEADER: owner_init})
    assert role["id"] not in {row["id"] for row in r.json()}
