"""
FastAPI-залежності tenancy/ролей.

`resolve_membership` — єдине місце, де shop_id виводиться з tg_id, здобутого
з валідованого Telegram initData (заголовок `X-Telegram-Init-Data`). Жоден
ендпоінт не має брати shop_id з тіла/параметрів запиту (CLAUDE.md, інваріант №1).

`require_api_key` — окремий шлях авторизації для server-to-server запитів із
сайту (заголовок `X-API-Key`), НЕ initData: це не дія користувача в Telegram.
"""
from __future__ import annotations

import hmac
from datetime import timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import MemberRole, Membership, Shop, Subscription
from app.security.crypto import CryptoError, decrypt
from app.security.initdata import InitDataError, validate_init_data
from app.services.bootstrap import bootstrap_shop

__all__ = [
    "get_session",
    "require_api_key",
    "require_member",
    "require_owner",
    "require_writable",
    "resolve_membership",
]

_API_KEY_PREFIX_LEN = 8


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


async def require_writable(
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Membership:
    """Гард на запис: протермінована підписка -> read-only (CLAUDE.md).
    GET-ендпоінти цей гард не накладають — дані лишаються видимими завжди."""
    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == membership.shop_id)
    )
    if subscription is None or not subscription.is_writable:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="підписка не активна — режим лише читання",
        )
    return membership


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> Shop:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-API-Key відсутній")

    prefix = x_api_key[:_API_KEY_PREFIX_LEN]
    shop = await session.scalar(select(Shop).where(Shop.api_key_prefix == prefix))
    if shop is None or not shop.api_key_encrypted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="невалідний API-ключ")

    try:
        expected = decrypt(shop.api_key_encrypted)
    except CryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="невалідний API-ключ"
        ) from exc

    if not hmac.compare_digest(expected, x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="невалідний API-ключ")

    return shop
