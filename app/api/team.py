"""
SkladBase — команда: deep-link інвайти + керування учасниками (Стадія 2а) +
кастомні ролі (Стадія 3b) + індивідуальні override поверх ролі (Стадія 3c).

Усе тут — лише для owner (`require_owner`): менеджер не запрошує інших і не
бачить/не редагує список команди чи ролі.

Ефективні права людини = права її ролі (Membership.role_ref) + nullable
override на самій Membership (`effective_permission`, app/deps.py). NULL —
"як у ролі"; true/false — явний виняток для ЦІЄЇ людини, призначається через
`PATCH /members/{id}/permissions`. Зміна ролі (`PATCH /members/{id}/role`)
скидає всі override в NULL — передбачуваність (рішення власника продукту).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_session
from app.deps import effective_permission, require_owner
from app.i18n import get_lang, msg
from app.models import Invite, MemberRole, Membership, Role, utcnow

router = APIRouter(prefix="/api/team", tags=["team"])

INVITE_TTL_HOURS = 48
_TOKEN_BYTES = 32

_PERM_COLS = [
    "can_view_inventory",
    "can_edit_products",
    "can_manage_reservations",
    "can_manage_stock",
    "can_view_finance",
    "can_manage_billing",
]

# Єдина роль, яку не можна редагувати (owner-override все одно ігнорує її
# can_*, редагування лише заплутає) — "Менеджер" (теж is_system) редагується
# як звичайна кастомна роль. DELETE лишається забороненим для ОБОХ системних
# ролей (delete_role нижче — окрема, не пов'язана з цим перевірка).
_OWNER_ROLE_NAME = "Власник"


class InviteOut(BaseModel):
    id: int
    token: str
    url: str
    expires_at: datetime


class InviteListItem(InviteOut):
    created_at: datetime


class MemberOut(BaseModel):
    id: int
    tg_id: int
    display_name: str | None
    role: str
    role_id: int
    role_name: str
    can_view_inventory: bool
    can_edit_products: bool
    can_manage_reservations: bool
    can_manage_stock: bool
    can_view_finance: bool
    can_manage_billing: bool
    overridden: list[str]


class RoleOut(BaseModel):
    id: int
    name: str
    can_view_inventory: bool
    can_edit_products: bool
    can_manage_reservations: bool
    can_manage_stock: bool
    can_view_finance: bool
    can_manage_billing: bool
    is_system: bool
    members_count: int


class RoleCreate(BaseModel):
    name: str
    can_view_inventory: bool = True
    can_edit_products: bool = True
    can_manage_reservations: bool = True
    can_manage_stock: bool = True
    can_view_finance: bool = True
    can_manage_billing: bool = True


class RolePatch(BaseModel):
    name: str | None = None
    can_view_inventory: bool | None = None
    can_edit_products: bool | None = None
    can_manage_reservations: bool | None = None
    can_manage_stock: bool | None = None
    can_view_finance: bool | None = None
    can_manage_billing: bool | None = None


class MemberRolePatch(BaseModel):
    role_id: int


class MemberPermissionsPatch(BaseModel):
    can_view_inventory: bool | None = None
    can_edit_products: bool | None = None
    can_manage_reservations: bool | None = None
    can_manage_stock: bool | None = None
    can_view_finance: bool | None = None
    can_manage_billing: bool | None = None


def _to_member_out(m: Membership) -> MemberOut:
    overridden = [perm for perm in _PERM_COLS if getattr(m, perm) is not None]
    return MemberOut(
        id=m.id, tg_id=m.tg_id, display_name=m.display_name, role=m.role.value,
        role_id=m.role_id, role_name=m.role_ref.name,
        can_view_inventory=effective_permission(m, "can_view_inventory"),
        can_edit_products=effective_permission(m, "can_edit_products"),
        can_manage_reservations=effective_permission(m, "can_manage_reservations"),
        can_manage_stock=effective_permission(m, "can_manage_stock"),
        can_view_finance=effective_permission(m, "can_view_finance"),
        can_manage_billing=effective_permission(m, "can_manage_billing"),
        overridden=overridden,
    )


def _to_role_out(r: Role, members_count: int) -> RoleOut:
    return RoleOut(
        id=r.id, name=r.name,
        can_view_inventory=r.can_view_inventory,
        can_edit_products=r.can_edit_products,
        can_manage_reservations=r.can_manage_reservations,
        can_manage_stock=r.can_manage_stock,
        can_view_finance=r.can_view_finance,
        can_manage_billing=r.can_manage_billing,
        is_system=r.is_system,
        members_count=members_count,
    )


def _invite_url(token: str) -> str:
    return f"https://t.me/{settings.BOT_USERNAME}?startapp=invite_{token}"


@router.post("/invites", status_code=status.HTTP_201_CREATED, response_model=InviteOut)
async def create_invite(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    invite = Invite(
        shop_id=membership.shop_id,
        token=token,
        created_by_tg_id=membership.tg_id,
        expires_at=utcnow() + timedelta(hours=INVITE_TTL_HOURS),
    )
    session.add(invite)
    await session.commit()

    return InviteOut(
        id=invite.id, token=invite.token, url=_invite_url(invite.token),
        expires_at=invite.expires_at,
    )


@router.get("/invites", response_model=list[InviteListItem])
async def list_invites(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> list[InviteListItem]:
    invites = (
        await session.scalars(
            select(Invite)
            .where(
                Invite.shop_id == membership.shop_id,
                Invite.revoked_at.is_(None),
                Invite.expires_at > utcnow(),
            )
            .order_by(Invite.created_at.desc())
        )
    ).all()

    return [
        InviteListItem(
            id=inv.id, token=inv.token, url=_invite_url(inv.token),
            created_at=inv.created_at, expires_at=inv.expires_at,
        )
        for inv in invites
    ]


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: int,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Response:
    invite = await session.get(Invite, invite_id)
    if invite is None or invite.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.invite_not_found", lang))

    invite.revoked_at = utcnow()
    await session.commit()
    return Response(status_code=204)


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> list[MemberOut]:
    members = (
        await session.scalars(
            select(Membership)
            .options(selectinload(Membership.role_ref))
            .where(Membership.shop_id == membership.shop_id)
            .order_by(Membership.created_at.asc())
        )
    ).all()

    return [_to_member_out(m) for m in members]


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> list[RoleOut]:
    roles = (
        await session.scalars(
            select(Role)
            .where(Role.shop_id == membership.shop_id)
            .order_by(Role.created_at.asc())
        )
    ).all()

    count_rows = (
        await session.execute(
            select(Membership.role_id, func.count())
            .where(Membership.shop_id == membership.shop_id)
            .group_by(Membership.role_id)
        )
    ).all()
    counts: dict[int, int] = {row[0]: row[1] for row in count_rows}

    return [_to_role_out(r, counts.get(r.id, 0)) for r in roles]


@router.post("/roles", status_code=status.HTTP_201_CREATED, response_model=RoleOut)
async def create_role(
    payload: RoleCreate,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> RoleOut:
    duplicate = await session.scalar(
        select(Role.id).where(Role.shop_id == membership.shop_id, Role.name == payload.name)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=msg("team.role_name_taken", lang))

    role = Role(shop_id=membership.shop_id, is_system=False, **payload.model_dump())
    session.add(role)
    await session.commit()
    return _to_role_out(role, members_count=0)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: int,
    payload: RolePatch,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> RoleOut:
    role = await session.get(Role, role_id)
    if role is None or role.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.role_not_found", lang))
    if role.name == _OWNER_ROLE_NAME:
        raise HTTPException(status_code=403, detail=msg("team.owner_role_protected", lang))

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] != role.name:
        duplicate = await session.scalar(
            select(Role.id).where(
                Role.shop_id == membership.shop_id, Role.name == changes["name"]
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=msg("team.role_name_taken", lang))

    for field_name, value in changes.items():
        setattr(role, field_name, value)

    await session.commit()

    members_count = await session.scalar(
        select(func.count()).select_from(Membership).where(Membership.role_id == role.id)
    )
    return _to_role_out(role, members_count=members_count or 0)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Response:
    role = await session.get(Role, role_id)
    if role is None or role.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.role_not_found", lang))
    if role.is_system:
        raise HTTPException(status_code=409, detail=msg("team.system_role_protected", lang))

    holders = await session.scalar(
        select(func.count()).select_from(Membership).where(Membership.role_id == role_id)
    )
    if holders:
        raise HTTPException(status_code=409, detail=msg("team.role_has_members", lang))

    await session.delete(role)
    await session.commit()
    return Response(status_code=204)


@router.patch("/members/{membership_id}/role", response_model=MemberOut)
async def update_member_role(
    membership_id: int,
    payload: MemberRolePatch,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> MemberOut:
    target = await session.get(
        Membership, membership_id, options=[selectinload(Membership.role_ref)]
    )
    if target is None or target.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.member_not_found", lang))
    if target.role == MemberRole.owner:
        raise HTTPException(status_code=409, detail=msg("team.owner_role_immutable", lang))

    new_role = await session.get(Role, payload.role_id)
    if new_role is None or new_role.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.role_not_found", lang))

    target.role_ref = new_role
    # Скидання overrides — та сама транзакція, що й призначення ролі (один
    # commit нижче): передбачуваність (рішення власника продукту) означає,
    # що між "нова роль призначена" й "старі override ще діють" немає ані
    # проміжного стану в БД, ані вікна для гонки при паралельному PATCH
    # /permissions на цього ж учасника.
    for perm in _PERM_COLS:
        setattr(target, perm, None)
    await session.commit()
    return _to_member_out(target)


@router.patch("/members/{membership_id}/permissions", response_model=MemberOut)
async def update_member_permissions(
    membership_id: int,
    payload: MemberPermissionsPatch,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> MemberOut:
    target = await session.get(
        Membership, membership_id, options=[selectinload(Membership.role_ref)]
    )
    if target is None or target.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.member_not_found", lang))
    if target.role == MemberRole.owner:
        raise HTTPException(status_code=409, detail=msg("team.owner_permissions_immutable", lang))

    changes = payload.model_dump(exclude_unset=True)
    for field_name, value in changes.items():
        setattr(target, field_name, value)

    await session.commit()
    return _to_member_out(target)


@router.delete("/members/{membership_id}", status_code=204)
async def delete_member(
    membership_id: int,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> Response:
    target = await session.get(Membership, membership_id)
    if target is None or target.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail=msg("team.member_not_found", lang))
    if target.id == membership.id:
        raise HTTPException(status_code=409, detail=msg("team.cannot_remove_self", lang))
    if target.role == MemberRole.owner:
        raise HTTPException(status_code=409, detail=msg("team.cannot_remove_owner", lang))

    await session.delete(target)
    await session.commit()
    return Response(status_code=204)
