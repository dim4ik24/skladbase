"""
SkladBase — нотифікація власника в Telegram (aiogram).

Мінімальний хук на Стадію 4a: повідомити власника про нове замовлення з
сайту. Повноцінний notifier (low-stock, нагадування про оплату тощо) — у
Стадії 6, поверх APScheduler.

Якщо `BOT_TOKEN` не налаштований — no-op (dev-середовище без реального
бота). У тестах функцію підміняють через `monkeypatch.setattr`, бо звертатись
до Telegram API з тестів не можна.
"""
from __future__ import annotations

from aiogram import Bot

from app.config import settings


async def notifier(tg_id: int, text: str) -> None:
    if not settings.BOT_TOKEN:
        return
    bot = Bot(token=settings.BOT_TOKEN)
    try:
        await bot.send_message(tg_id, text)
    finally:
        await bot.session.close()
