"""
FastAPI-залежності tenancy/ролей.

`resolve_membership` — єдине місце, де shop_id виводиться з tg_id, здобутого
з валідованого Telegram initData (заголовок `X-Telegram-Init-Data`). Жоден
ендпоінт не має брати shop_id з тіла/параметрів запиту (CLAUDE.md, інваріант №1).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import MemberRole, Membership
from app.security.initdata import InitDataError, validate_init_data
from app.services.bootstrap import bootstrap_shop

__all__ = [
    "get_session",
    "require_member",
    "require_owner",
    "resolve_membership",
]


async def resolve_membership(
    x_telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
    session: AsyncSession = Depends(get_session),
) -> Membership:
    try:
        init_data = validate_init_data(
            x_telegram_init_data,
            settings.BOT_TOKEN,
            max_age=timedelta(hours=settings.INIT_DATA_MAX_AGE_HOURS),
        )
    except InitDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    membership = await session.scalar(
        select(Membership).where(Membership.tg_id == init_data.user.id)
    )
    if membership is None:
        membership = await bootstrap_shop(session, init_data.user)

    return membership


async def require_member(
    membership: Membership = Depends(resolve_membership),
) -> Membership:
    return membership


async def require_owner(
    membership: Membership = Depends(resolve_membership),
) -> Membership:
    if membership.role != MemberRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner-only")
    return membership
