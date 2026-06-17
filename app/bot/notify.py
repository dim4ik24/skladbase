"""
SkladBase — нотифікація власника в Telegram (aiogram).

Реальний канал для крон-джоб (Стадія 6: low-stock, протермінування, нагадування
про оплату, провал авто-списання) і для notify-хука нових замовлень (Стадія 4a).

Якщо `BOT_TOKEN` не налаштований — no-op (dev-середовище без реального бота).
Помилка відправки (юзер заблокував бота, чат видалено, мережевий збій тощо)
лише логується — одне недоставлене повідомлення не повинне валити крон-джобу
чи запит. У тестах функцію підміняють через `monkeypatch.setattr` на рівні
модуля, що її імпортує (наприклад `app.api.orders.notifier`), бо звертатись
до Telegram API з тестів не можна.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import AiogramError

from app.config import settings

logger = logging.getLogger(__name__)


async def notifier(tg_id: int, text: str) -> None:
    if not settings.BOT_TOKEN:
        return
    bot = Bot(token=settings.BOT_TOKEN)
    try:
        await bot.send_message(tg_id, text)
    except AiogramError:
        logger.warning("не вдалося надіслати повідомлення tg_id=%s", tg_id, exc_info=True)
    finally:
        await bot.session.close()
