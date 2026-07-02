"""
SkladBase — команда: deep-link інвайти + керування учасниками (Стадія 2а).

Усе тут — лише для owner (`require_owner`): менеджер не запрошує інших і не
бачить/не редагує список команди.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.deps import require_owner
from app.models import Invite, MemberRole, Membership, utcnow

router = APIRouter(prefix="/api/team", tags=["team"])

INVITE_TTL_HOURS = 48
_TOKEN_BYTES = 32


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
    can_view_inventory: bool
    can_edit_products: bool
    can_manage_reservations: bool
    can_manage_stock: bool
    can_view_finance: bool
    can_manage_billing: bool


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
) -> Response:
    invite = await session.get(Invite, invite_id)
    if invite is None or invite.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail="інвайт не знайдено")

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
            .where(Membership.shop_id == membership.shop_id)
            .order_by(Membership.created_at.asc())
        )
    ).all()

    return [
        MemberOut(
            id=m.id, tg_id=m.tg_id, display_name=m.display_name, role=m.role.value,
            can_view_inventory=m.can_view_inventory,
            can_edit_products=m.can_edit_products,
            can_manage_reservations=m.can_manage_reservations,
            can_manage_stock=m.can_manage_stock,
            can_view_finance=m.can_view_finance,
            can_manage_billing=m.can_manage_billing,
        )
        for m in members
    ]


@router.delete("/members/{membership_id}", status_code=204)
async def delete_member(
    membership_id: int,
    membership: Membership = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> Response:
    target = await session.get(Membership, membership_id)
    if target is None or target.shop_id != membership.shop_id:
        raise HTTPException(status_code=404, detail="учасника не знайдено")
    if target.id == membership.id:
        raise HTTPException(status_code=409, detail="не можна видалити самого себе")
    if target.role == MemberRole.owner:
        raise HTTPException(status_code=409, detail="не можна видалити owner'а")

    await session.delete(target)
    await session.commit()
    return Response(status_code=204)
