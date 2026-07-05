"""
SkladBase — APScheduler: розклад крон-джоб (Стадія 6).

Бізнес-логіка кожної джоби вже в `app/tasks.py` (не переписуємо). Тут лише:
відкрити async-сесію, зібрати залежності (notifier; для картки —
WayForPayProvider із settings), викликати функцію й обгорнути в try/except —
один збій джоби не повинен валити весь планувальник чи решту розкладу.

Розклад:
  np_tracking                    — 10 хв
  release_expired_reservations   — 1 год
  low_stock_scan                 — 1 год
  charge_due_card_subscriptions  — 6 год
  expire_subscriptions           — 24 год (раз/добу)
  send_renewal_reminders         — 24 год (раз/добу)
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import db
from app.billing.providers import WayForPayProvider
from app.bot.notify import notifier
from app.config import settings
from app.services.novaposhta import track as np_track
from app.tasks import (
    charge_due_card_subscriptions,
    expire_subscriptions,
    low_stock_scan,
    np_tracking,
    release_expired_reservations,
    send_renewal_reminders,
)

logger = logging.getLogger(__name__)


async def _run_np_tracking() -> None:
    try:
        async with db.async_session() as session:
            count = await np_tracking(session, notifier, np_track)
            logger.info("np_tracking: оброблено %s резервів", count)
    except Exception:
        logger.exception("джоба np_tracking завершилась з помилкою")


async def _run_release_expired_reservations() -> None:
    try:
        async with db.async_session() as session:
            count = await release_expired_reservations(session)
            logger.info("release_expired_reservations: знято %s резервів", count)
    except Exception:
        logger.exception("джоба release_expired_reservations завершилась з помилкою")


async def _run_low_stock_scan() -> None:
    try:
        async with db.async_session() as session:
            count = await low_stock_scan(session, notifier)
            logger.info("low_stock_scan: надіслано %s сповіщень", count)
    except Exception:
        logger.exception("джоба low_stock_scan завершилась з помилкою")


async def _run_charge_due_card_subscriptions() -> None:
    try:
        provider = WayForPayProvider(settings.WFP_MERCHANT, settings.WFP_SECRET, settings.WFP_DOMAIN)
        async with db.async_session() as session:
            count = await charge_due_card_subscriptions(session, provider, notifier)
            logger.info("charge_due_card_subscriptions: списано %s підписок", count)
    except Exception:
        logger.exception("джоба charge_due_card_subscriptions завершилась з помилкою")


async def _run_expire_subscriptions() -> None:
    try:
        async with db.async_session() as session:
            count = await expire_subscriptions(session, notifier)
            logger.info("expire_subscriptions: протерміновано %s підписок", count)
    except Exception:
        logger.exception("джоба expire_subscriptions завершилась з помилкою")


async def _run_send_renewal_reminders() -> None:
    try:
        async with db.async_session() as session:
            count = await send_renewal_reminders(session, notifier)
            logger.info("send_renewal_reminders: надіслано %s нагадувань", count)
    except Exception:
        logger.exception("джоба send_renewal_reminders завершилась з помилкою")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_run_np_tracking, "interval", minutes=10, id="np_tracking")
    scheduler.add_job(
        _run_release_expired_reservations,
        "interval",
        hours=1,
        id="release_expired_reservations",
    )
    scheduler.add_job(_run_low_stock_scan, "interval", hours=1, id="low_stock_scan")
    scheduler.add_job(
        _run_charge_due_card_subscriptions,
        "interval",
        hours=6,
        id="charge_due_card_subscriptions",
    )
    scheduler.add_job(_run_expire_subscriptions, "interval", hours=24, id="expire_subscriptions")
    scheduler.add_job(
        _run_send_renewal_reminders, "interval", hours=24, id="send_renewal_reminders"
    )
    return scheduler
