"""Мут/бан у техпідтримці бота — SupportBan (app/models.py).

Винесено окремо від app/bot/handlers.py (яка вже документує FSM/reply-мапінг
техпідтримки), щоб бот-хендлери лишались тонкими: DB-логіка тут, хендлери
лише викликають і формують відповідь адміну/юзеру.
"""
from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportBan, ensure_aware_utc, utcnow

MUTE_DURATION = timedelta(hours=1)


async def get_ban(session: AsyncSession, tg_id: int) -> SupportBan | None:
    return await session.scalar(select(SupportBan).where(SupportBan.tg_id == tg_id))


async def _get_or_create(session: AsyncSession, tg_id: int) -> SupportBan:
    ban = await get_ban(session, tg_id)
    if ban is None:
        ban = SupportBan(tg_id=tg_id)
        session.add(ban)
    return ban


async def mute_user(session: AsyncSession, tg_id: int, duration: timedelta = MUTE_DURATION) -> None:
    ban = await _get_or_create(session, tg_id)
    ban.muted_until = utcnow() + duration
    await session.commit()


async def ban_user(session: AsyncSession, tg_id: int) -> None:
    ban = await _get_or_create(session, tg_id)
    ban.banned = True
    await session.commit()


async def unban_user(session: AsyncSession, tg_id: int) -> None:
    ban = await get_ban(session, tg_id)
    if ban is None:
        return
    ban.banned = False
    ban.muted_until = None
    await session.commit()


def remaining_mute_minutes(ban: SupportBan | None) -> int | None:
    """Скільки хвилин лишилось муту, або None якщо не замучений/мут скінчився."""
    if ban is None or ban.muted_until is None:
        return None
    remaining = ensure_aware_utc(ban.muted_until) - utcnow()
    if remaining.total_seconds() <= 0:
        return None
    return math.ceil(remaining.total_seconds() / 60)
