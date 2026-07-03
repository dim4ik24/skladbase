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

from app import db
from app.deps import _check_permission, _check_writable
from app.models import MemberRole, Membership
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
    """Construct an in-memory Membership with all perms True by default."""
    m = Membership()
    m.role = role
    m.shop_id = 1
    for perm in _ALL_PERMS:
        setattr(m, perm, overrides.get(perm, True))
    return m


async def _bootstrap(client: AsyncClient, tg_id: int) -> tuple[str, int]:
    init_data = make_init_data(tg_id)
    r = await client.post("/api/shops", headers={HEADER: init_data}, json={"name": f"Магазин {tg_id}"})
    assert r.status_code == 201, r.text
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
            await _check_writable(nonexistent_shop_id, session)
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
#  Test 6: bootstrapped membership has all 6 permission columns = True
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_bootstrap_membership_has_all_perms_true(client: AsyncClient) -> None:
    _init_data, _shop_id = await _bootstrap(client, tg_id=9003)

    async with db.async_session() as session:
        membership = await session.scalar(
            select(Membership).where(Membership.tg_id == 9003)
        )
        assert membership is not None
        for perm in _ALL_PERMS:
            assert getattr(membership, perm) is True, f"{perm} should be True after bootstrap"
