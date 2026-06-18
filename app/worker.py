"""
SkladBase — окремий процес планувальника (Стадія 9a).

Web-воркери (uvicorn, `app/main.py`) НЕ піднімають AsyncIOScheduler —
інакше кожна репліка web-процесу стрільнула б тими ж кронами N разів.
Планувальник живе тут, в одному окремому процесі: `python -m app.worker`
(прод: systemd-юніт `deploy/skladbase-scheduler.service`).

Не залежить від `settings.RUN_SCHEDULER` — той прапорець керує лише
lifespan веб-процесу (False у проді: web не піднімає крони). Тут
планувальник стартує завжди, бо сам процес і існує лише для цього.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app import db
from app.scheduler import create_scheduler

logger = logging.getLogger(__name__)


async def _main() -> None:
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("scheduler_started")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # Windows dev: немає add_signal_handler, лише Ctrl+C (KeyboardInterrupt)

    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=False)
        await db.engine.dispose()
        logger.info("scheduler_stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
