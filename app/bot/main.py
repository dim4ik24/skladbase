"""
SkladBase — окремий процес long-polling бота (Стадія "техпідтримка").

Веб-процес (`app/main.py`) фідить Telegram-апдейти лише через вебхук
(`app/api/telegram.py`, платежі) — support-хендлери (`app/bot/handlers.py`)
теж висять на тому самому `dp` (`app/bot/dispatcher.py`), але апдейти для
них ніхто не постачає: вебхук ставиться на конкретний тип трафіку/URL,
а не "все підряд". Тож потрібен окремий процес, що сам тягне апдейти в
Telegram (polling) — той самий `dp`, друге джерело подій.

Прод: systemd-юніт `deploy/skladbase-bot.service`
(`python -m app.bot.main`), та сама структура запуску/зупинки, що
`app/worker.py` (asyncio.Event + сигнали, не вбудований run_polling()
з aiogram — для однакового патерну graceful shutdown в обох процесах).
"""
from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot

from app import db
from app.bot.dispatcher import dp
from app.config import settings

logger = logging.getLogger(__name__)


async def _main() -> None:
    if not settings.BOT_TOKEN:
        logger.warning("BOT_TOKEN не налаштований — polling не стартує (dev без реального бота)")
        return

    bot = Bot(token=settings.BOT_TOKEN)

    # Страховка: якщо на цьому боті колись ставився webhook (навіть лише
    # платіжний, app/api/telegram.py) — він конфліктує з polling
    # (TelegramConflictError, Telegram дозволяє лише один спосіб доставки
    # апдейтів одночасно). drop_pending_updates=False: не губимо те, що
    # накопичилось, поки жоден спосіб доставки не був активний.
    await bot.delete_webhook(drop_pending_updates=False)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # Windows dev: немає add_signal_handler, лише Ctrl+C

    # handle_signals=False: сигнали обробляємо самі (вище), як у app/worker.py,
    # а не вбудованим механізмом aiogram — однаковий патерн в обох процесах.
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    logger.info("bot_polling_started")

    try:
        await stop.wait()
    finally:
        await dp.stop_polling()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await db.engine.dispose()
        logger.info("bot_polling_stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
