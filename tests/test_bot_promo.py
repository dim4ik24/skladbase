"""
Промокоди — адмін-команди бота (app/bot/handlers.py): /promo_create,
/promo_list, /promo_off. Розширення наявного PromoCode/redeem_promo
(стадія 5a) новим типом PromoType.plan_grant.

Той самий підхід, що й test_bot_support.py: хендлери викликаються напряму
(Message/CommandObject замокані), справжня ізольована in-memory БД з
conftest._isolated_db (autouse) — не мокаємо сесію, лише Telegram-шар.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from sqlalchemy import select

from app import db
from app.bot import handlers
from app.config import settings
from app.models import Plan, PromoCode, PromoType, SubPeriod


def _make_message(*, tg_id: int | None = None) -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = tg_id if tg_id is not None else settings.ADMIN_TG_ID
    message.answer = AsyncMock()
    return message


def _cmd(args: str | None) -> CommandObject:
    return CommandObject(command="promo_create", args=args)


async def _ensure_plan(code: str = "pro") -> Plan:
    async with db.async_session() as session:
        existing = await session.scalar(select(Plan).where(Plan.code == code))
        if existing is not None:
            return existing
        plan = Plan(
            code=code, name=code.capitalize(), period=SubPeriod.month,
            price_uah=Decimal("500"), price_stars=300, limits={},
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


async def _get_promo(code: str) -> PromoCode | None:
    async with db.async_session() as session:
        return await session.scalar(select(PromoCode).where(PromoCode.code == code))


@pytest.fixture(autouse=True)
def _set_admin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ADMIN_TG_ID", 999999)


# --------------------------------------------------------------------------- #
#  /promo_create
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_promo_create_trial_success() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("WELCOME60 trial 60 5"), session)

    message.answer.assert_awaited_once()
    text = message.answer.call_args.args[0]
    assert "Створено" in text
    assert "тріал" in text

    promo = await _get_promo("WELCOME60")
    assert promo is not None
    assert promo.type == PromoType.free_period
    assert promo.value == 60
    assert promo.max_uses == 5
    assert promo.plan_id is None
    assert promo.expires_at is None


@pytest.mark.asyncio
async def test_promo_create_plan_grant_success_with_expires() -> None:
    plan = await _ensure_plan("pro")
    message = _make_message()

    async with db.async_session() as session:
        await handlers.admin_promo_create(
            message, _cmd("VIP2026 plan:pro 30 1 expires 2026-12-31"), session
        )

    text = message.answer.call_args.args[0]
    assert "Створено" in text
    assert "pro" in text or "Pro" in text

    promo = await _get_promo("VIP2026")
    assert promo is not None
    assert promo.type == PromoType.plan_grant
    assert promo.plan_id == plan.id
    assert promo.value == 30
    assert promo.max_uses == 1
    assert promo.expires_at is not None
    assert promo.expires_at.year == 2026 and promo.expires_at.month == 12 and promo.expires_at.day == 31


@pytest.mark.asyncio
async def test_promo_create_lowercases_to_uppercase_code() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("lowcode trial 10 1"), session)

    assert await _get_promo("LOWCODE") is not None
    assert await _get_promo("lowcode") is None


@pytest.mark.asyncio
async def test_promo_create_unknown_plan_shows_error_and_creates_nothing() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("NOPE plan:doesnotexist 30 1"), session)

    text = message.answer.call_args.args[0]
    assert "не знайдено" in text
    assert await _get_promo("NOPE") is None


@pytest.mark.asyncio
async def test_promo_create_invalid_kind_shows_usage() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("BADCODE freebie 30 1"), session)

    text = message.answer.call_args.args[0]
    assert "Формат:" in text
    assert await _get_promo("BADCODE") is None


@pytest.mark.asyncio
async def test_promo_create_non_positive_days_shows_error() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("ZERODAYS trial 0 5"), session)

    text = message.answer.call_args.args[0]
    assert "додатними числами" in text
    assert await _get_promo("ZERODAYS") is None


@pytest.mark.asyncio
async def test_promo_create_non_numeric_args_shows_error() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("BADNUM trial abc 5"), session)

    text = message.answer.call_args.args[0]
    assert "додатними числами" in text


@pytest.mark.asyncio
async def test_promo_create_wrong_arg_count_shows_usage() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd("ONLYCODE trial"), session)

    text = message.answer.call_args.args[0]
    assert "Формат:" in text


@pytest.mark.asyncio
async def test_promo_create_no_args_shows_usage() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message, _cmd(None), session)

    text = message.answer.call_args.args[0]
    assert "Формат:" in text


@pytest.mark.asyncio
async def test_promo_create_bad_expires_date_shows_error() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(
            message, _cmd("BADDATE trial 30 1 expires 31-12-2026"), session
        )

    text = message.answer.call_args.args[0]
    assert "розпізнав дату" in text
    assert await _get_promo("BADDATE") is None


@pytest.mark.asyncio
async def test_promo_create_duplicate_code_shows_error() -> None:
    message1 = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message1, _cmd("DUPCODE trial 10 1"), session)

    message2 = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_create(message2, _cmd("DUPCODE trial 20 2"), session)

    text = message2.answer.call_args.args[0]
    assert "вже існує" in text

    promo = await _get_promo("DUPCODE")
    assert promo is not None
    assert promo.value == 10  # перший запис не перезаписано


# --------------------------------------------------------------------------- #
#  /promo_list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_promo_list_empty() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_list(message, session)

    text = message.answer.call_args.args[0]
    assert "немає" in text


@pytest.mark.asyncio
async def test_promo_list_shows_active_codes_with_usage() -> None:
    plan = await _ensure_plan("pro")
    async with db.async_session() as session:
        session.add(PromoCode(code="TRIALCODE", type=PromoType.free_period, value=14, max_uses=3))
        session.add(
            PromoCode(
                code="PLANCODE", type=PromoType.plan_grant, value=30, plan_id=plan.id, max_uses=1,
                used_count=1,
            )
        )
        session.add(
            PromoCode(code="OFFCODE", type=PromoType.free_period, value=5, max_uses=1, is_active=False)
        )
        await session.commit()

    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_list(message, session)

    text = message.answer.call_args.args[0]
    assert "TRIALCODE" in text
    assert "PLANCODE" in text
    assert "1/1" in text  # used_count/max_uses для PLANCODE
    assert "OFFCODE" not in text  # is_active=False не показуємо


# --------------------------------------------------------------------------- #
#  /promo_off
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_promo_off_disables_code() -> None:
    async with db.async_session() as session:
        session.add(PromoCode(code="TURNOFF", type=PromoType.free_period, value=10, max_uses=5))
        await session.commit()

    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_off(
            message, CommandObject(command="promo_off", args="turnoff"), session
        )

    text = message.answer.call_args.args[0]
    assert "вимкнено" in text

    promo = await _get_promo("TURNOFF")
    assert promo is not None
    assert promo.is_active is False


@pytest.mark.asyncio
async def test_promo_off_unknown_code_shows_error() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_off(
            message, CommandObject(command="promo_off", args="NOSUCH"), session
        )

    text = message.answer.call_args.args[0]
    assert "не знайдено" in text


@pytest.mark.asyncio
async def test_promo_off_no_args_shows_usage() -> None:
    message = _make_message()
    async with db.async_session() as session:
        await handlers.admin_promo_off(message, CommandObject(command="promo_off", args=None), session)

    text = message.answer.call_args.args[0]
    assert "Формат:" in text
