"""
Stage 1a — Granular permissions foundation: acceptance tests.

Scenarios:
  1. owner + any perm → always passes (_check_permission, even if column were False).
  2. manager + perm=True → passes.
  3. manager + perm=False → raises HTTPException(403).
  4. require_permission_writable: manager perm=True + expired subscription → 402.
  5. require_permission_writable: manager perm=False + active subscription → 403.
  6. Bootstrap creates membership with all 6 permission columns = True.

Tests 1-3 are sync, isolated (no DB, no HTTP).
Tests 4-5 use the real conftest DB via async_session.
Test 6 uses bootstrap via HTTP client.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import db
from app.deps import _check_permission, _check_writable, effective_permission
from app.models import MemberRole, Membership, Role
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


def _make_membership(role: MemberRole, **overrides: bool) -> Membership:
    """Construct an in-memory Membership + Role with all perms True by
    default — жодного DB round-trip, лише Python-об'єкти (role_ref
    відноситься в пам'яті через relationship, без сесії/lazy-load)."""
    role_ref = Role()
    for perm in _ALL_PERMS:
        setattr(role_ref, perm, overrides.get(perm, True))
    m = Membership()
    m.role = role
    m.shop_id = 1
    m.role_ref = role_ref
    return m


async def _bootstrap(client: AsyncClient, tg_id: int) -> tuple[str, int]:
    init_data = make_init_data(tg_id)
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


# --------------------------------------------------------------------------- #
#  Test 1: owner override — always passes regardless of column value
# --------------------------------------------------------------------------- #

def test_owner_override_passes_even_if_column_false() -> None:
    m = _make_membership(MemberRole.owner, can_view_finance=False)
    # Must not raise — owner override ignores column value
    _check_permission(m, "can_view_finance")


def test_owner_override_all_perms() -> None:
    for perm in _ALL_PERMS:
        m = _make_membership(MemberRole.owner, **{perm: False})
        _check_permission(m, perm)  # must not raise for any perm


# --------------------------------------------------------------------------- #
#  Test 2: manager + perm=True → passes
# --------------------------------------------------------------------------- #

def test_manager_with_perm_true_passes() -> None:
    m = _make_membership(MemberRole.manager, can_view_finance=True)
    _check_permission(m, "can_view_finance")


# --------------------------------------------------------------------------- #
#  Test 3: manager + perm=False → 403
# --------------------------------------------------------------------------- #

def test_manager_with_perm_false_raises_403() -> None:
    m = _make_membership(MemberRole.manager, can_view_finance=False)
    with pytest.raises(HTTPException) as exc_info:
        _check_permission(m, "can_view_finance")
    assert exc_info.value.status_code == 403


def test_manager_each_perm_false_raises_403() -> None:
    for perm in _ALL_PERMS:
        m = _make_membership(MemberRole.manager, **{perm: False})
        with pytest.raises(HTTPException) as exc_info:
            _check_permission(m, perm)
        assert exc_info.value.status_code == 403


# --------------------------------------------------------------------------- #
#  Test 4: perm=True + no subscription → 402 (not 403)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_perm_true_missing_sub_raises_402(client: AsyncClient) -> None:
    # Use a shop_id that was never created → scalar returns None → 402.
    # NOTE: FREE_PLAN_SPEC §8 makes all SubStatus values writable (is_writable=True),
    # so the only way to trigger 402 from _check_writable is subscription=None.
    nonexistent_shop_id = 999_999

    m = _make_membership(MemberRole.manager, can_view_finance=True)
    m.shop_id = nonexistent_shop_id

    async with db.async_session() as session:
        _check_permission(m, "can_view_finance")  # must not raise (perm=True)
        with pytest.raises(HTTPException) as exc_info:
            await _check_writable(nonexistent_shop_id, session, "uk")
        assert exc_info.value.status_code == 402


# --------------------------------------------------------------------------- #
#  Test 5: perm=False + active subscription → 403 (not 402)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_perm_false_active_sub_raises_403(client: AsyncClient) -> None:
    _init_data, shop_id = await _bootstrap(client, tg_id=9002)

    # Subscription is active trial by default — no changes needed
    m = _make_membership(MemberRole.manager, can_view_finance=False)
    m.shop_id = shop_id

    with pytest.raises(HTTPException) as exc_info:
        _check_permission(m, "can_view_finance")
    assert exc_info.value.status_code == 403
    # 403 fires before we'd even reach writable check


# --------------------------------------------------------------------------- #
#  Test 6: bootstrapped owner's role_ref (Власник) has all 6 perms = True
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_bootstrap_membership_has_all_perms_true(client: AsyncClient) -> None:
    _init_data, _shop_id = await _bootstrap(client, tg_id=9003)

    async with db.async_session() as session:
        membership = await session.scalar(
            select(Membership).options(selectinload(Membership.role_ref))
            .where(Membership.tg_id == 9003)
        )
        assert membership is not None
        assert membership.role_ref.name == "Власник"
        assert membership.role_ref.is_system is True
        for perm in _ALL_PERMS:
            assert getattr(membership.role_ref, perm) is True, (
                f"{perm} should be True after bootstrap"
            )


# --------------------------------------------------------------------------- #
#  Test 7: effective_permission — роль + nullable override поверх (фіча 3c)
# --------------------------------------------------------------------------- #

def test_effective_permission_override_false_beats_role_true() -> None:
    m = _make_membership(MemberRole.manager, can_view_finance=True)
    m.can_view_finance = False  # явний override, перемагає роль
    assert effective_permission(m, "can_view_finance") is False


def test_effective_permission_override_true_beats_role_false() -> None:
    m = _make_membership(MemberRole.manager, can_view_finance=False)
    m.can_view_finance = True
    assert effective_permission(m, "can_view_finance") is True


def test_effective_permission_null_override_falls_back_to_role() -> None:
    m = _make_membership(MemberRole.manager, can_view_finance=True)
    m.can_view_finance = None  # немає override — "як у ролі"
    assert effective_permission(m, "can_view_finance") is True

    m2 = _make_membership(MemberRole.manager, can_view_finance=False)
    m2.can_view_finance = None
    assert effective_permission(m2, "can_view_finance") is False


def test_effective_permission_unset_override_defaults_to_role() -> None:
    """_make_membership не чіпає can_*-поля Membership взагалі (лишень
    role_ref) — так само, як щойно завантажений з БД рядок без override."""
    m = _make_membership(MemberRole.manager, can_view_finance=True)
    assert effective_permission(m, "can_view_finance") is True


def test_check_permission_respects_override_over_role() -> None:
    """_check_permission (403-гейт) читає через effective_permission, не
    напряму role_ref — override має так само перемагати роль тут."""
    m = _make_membership(MemberRole.manager, can_view_finance=True)
    m.can_view_finance = False
    with pytest.raises(HTTPException) as exc_info:
        _check_permission(m, "can_view_finance")
    assert exc_info.value.status_code == 403

    m2 = _make_membership(MemberRole.manager, can_view_finance=False)
    m2.can_view_finance = True
    _check_permission(m2, "can_view_finance")  # override=True — must not raise
