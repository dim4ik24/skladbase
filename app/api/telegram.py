"""
SkladBase — вхідний вебхук Telegram (Стадія 5a).

Парсить вхідний JSON у `aiogram.types.Update` і фідить у Dispatcher
(`app/bot/dispatcher.py`) — там і живе вся бізнес-логіка (Stars-платежі).
Реальне підключення бота (`setWebhook` на проді / polling у dev) — Стадія 9;
зараз важливо, щоб хендлери коректно спрацьовували й тестувались.
"""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import Update
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dispatcher import dp
from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/webhook", tags=["telegram"])


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    raw = await request.json()
    update = Update.model_validate(raw)

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        await dp.feed_update(bot, update, session=session)
    finally:
        await bot.session.close()

    return {"ok": True}
