"""
FastAPI-залежності tenancy/ролей.

`resolve_membership` — єдине місце, де shop_id виводиться з tg_id, здобутого
з валідованого Telegram initData (заголовок `X-Telegram-Init-Data`). Жоден
ендпоінт не має брати shop_id з тіла/параметрів запиту (CLAUDE.md, інваріант №1).

Multi-shop (Стадія 3а): одна людина може мати Membership у кількох магазинах.
Опційний заголовок `X-Shop-Id` — ЛИШЕ ВИБІР серед СВОЇХ membership (фільтр у
парі з tg_id, тобто перевіряється членство, а не голий id), сам по собі не
довіряється: чужий/невідомий shop_id -> 403, а не "магія" з чужими даними.
Без заголовка — перше (найменше id) membership цього tg_id, детерміновано;
так фронт до 3b, що заголовок не шле, поводиться так само, як і зараз.

Онбординг (shop lifecycle): якщо для tg_id взагалі нема Membership і нема
валідного invite-токена в start_param — 404 "немає магазину" (`no_shop`),
магазин НЕ створюється автоматично. Явне створення — `POST /api/shops`
(app/api/shop.py, `resolve_telegram_user` нижче), який може викликати
БУДЬ-ХТО з валідним initData незалежно від наявності Membership (multi-shop:
можна створити ще один магазин). Це НЕ той самий кейс, що dead `X-Shop-Id`
(вище) — там 403 "Немає доступу", membership'и в юзера ще є, просто не до
ЦЬОГО shop_id.

`require_api_key` — окремий шлях авторизації для server-to-server запитів із
сайту (заголовок `X-API-Key`), НЕ initData: це не дія користувача в Telegram.
"""
from __future__ import annotations

import hmac
from datetime import timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import MemberRole, Membership, Shop, Subscription
from app.security.crypto import CryptoError, decrypt
from app.security.initdata import InitDataError, TelegramUser, validate_init_data
from app.services.bootstrap import bootstrap_shop, parse_invite_token

__all__ = [
    "get_session",
    "require_api_key",
    "require_member",
    "require_owner",
    "require_permission",
    "require_permission_writable",
    "require_writable",
    "resolve_membership",
    "resolve_telegram_user",
]

_API_KEY_PREFIX_LEN = 8


async def resolve_telegram_user(
    x_telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> TelegramUser:
    """Валідує Telegram initData БЕЗ вимоги існуючого Membership — для
    `POST /api/shops`, де юзер ще (перший магазин) або вже (multi-shop,
    ще один магазин) не прив'язаний до shop_id, який тут резолвити нема з чого."""
    try:
        init_data = validate_init_data(
            x_telegram_init_data,
            settings.BOT_TOKEN,
            max_age=timedelta(hours=settings.INIT_DATA_MAX_AGE_HOURS),
        )
    except InitDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return init_data.user


async def resolve_membership(
    request: Request,
    x_telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
    x_shop_id: int | None = Header(default=None, alias="X-Shop-Id"),
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

    if x_shop_id is not None:
        # Заголовок — лише фільтр СЕРЕД membership цього tg_id, не самостійне
        # джерело shop_id: чуже/неіснуюче членство -> 403, ніякого bootstrap.
        membership = await session.scalar(
            select(Membership).where(
                Membership.tg_id == init_data.user.id, Membership.shop_id == x_shop_id
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Немає доступу до цього магазину"
            )
        request.state.invite_status = None
        return membership

    membership = await session.scalar(
        select(Membership)
        .where(Membership.tg_id == init_data.user.id)
        .order_by(Membership.id)
        .limit(1)
    )
    invite_status: str | None = None
    if membership is None:
        membership, invite_status = await bootstrap_shop(
            session, init_data.user, init_data.start_param
        )
        if membership is None:
            # Нема Membership і нема валідного invite-токена — магазин НЕ
            # створюється автоматично (див. docstring вище). 404, не 403:
            # це "у тебе взагалі нема тенанта", а не "нема доступу до X".
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="немає магазину")
    elif parse_invite_token(init_data.start_param) is not None:
        # Existing юзер + invite-токен: bootstrap_shop сам вирішить
        # already_in_shop / joined (нове membership!) / invite_invalid.
        membership, invite_status = await bootstrap_shop(
            session, init_data.user, init_data.start_param
        )

    request.state.invite_status = invite_status
    assert membership is not None  # elif-гілка: existing-юзер, bootstrap_shop завжди повертає Membership
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


def _check_permission(membership: Membership, perm: str) -> None:
    """Pure sync check — exposed for direct testing without HTTP overhead.

    owner role always passes (column value irrelevant — owner override).
    """
    if membership.role == MemberRole.owner:
        return
    if not getattr(membership, perm, False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"permission denied: {perm}",
        )


async def _check_writable(shop_id: int, session: AsyncSession) -> None:
    """Pure async writable check — exposed for direct testing."""
    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == shop_id)
    )
    if subscription is None or not subscription.is_writable:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="підписка не активна — режим лише читання",
        )


def require_permission(perm: str) -> Any:
    """Dependency factory: resolves membership then checks granular permission (403)."""
    async def _dep(
        membership: Membership = Depends(resolve_membership),
    ) -> Membership:
        _check_permission(membership, perm)
        return membership
    return Depends(_dep)


def require_permission_writable(perm: str) -> Any:
    """Dependency factory: permission check (403) AND writable check (402), independent gates."""
    async def _dep(
        membership: Membership = Depends(resolve_membership),
        session: AsyncSession = Depends(get_session),
    ) -> Membership:
        _check_permission(membership, perm)          # 403 fires first
        await _check_writable(membership.shop_id, session)  # 402 independent
        return membership
    return Depends(_dep)


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> Shop:
    """`api_key_prefix` НЕ унікальний (8 символів — теоретично можлива колізія
    між магазинами, ROADMAP, відкладено зі Стадії 4a). Тож тут перебираємо
    УСІХ кандидатів з цим префіксом і constant-time звіряємо кожен з повним
    ключем, замість `scalar()` (який впав би з `MultipleResultsFound` при
    колізії) чи довіри першому знайденому (який міг би віддати ЧУЖИЙ shop)."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-API-Key відсутній")

    prefix = x_api_key[:_API_KEY_PREFIX_LEN]
    candidates = (
        await session.scalars(select(Shop).where(Shop.api_key_prefix == prefix))
    ).all()

    for shop in candidates:
        if not shop.api_key_encrypted:
            continue
        try:
            expected = decrypt(shop.api_key_encrypted)
        except CryptoError:
            continue
        if hmac.compare_digest(expected, x_api_key):
            return shop

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="невалідний API-ключ")
