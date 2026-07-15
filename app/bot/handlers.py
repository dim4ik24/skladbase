"""
SkladBase — /start (привітання) + техпідтримка через бота (FSM-режим).

`/start` НІЧОГО не створює: магазин заводиться явно через POST /api/shops
(shop lifecycle) з екрана онбордингу в Mini App, не через бота. Тут лише
привітання + кнопка "Відкрити" (web_app, якщо MINI_APP_URL налаштований).
Deep-link інвайти (`?startapp=invite_<token>`) теж не обробляються тут —
їх читає сам Mini App із `initDataUnsafe.start_param`, бот про них не знає.

Юзер пише /support -> усе, що він пише далі, пересилається адміну
(`settings.ADMIN_TG_ID`) з контекстним рядком (ім'я, username, tg_id).
Адмін відповідає REPLY'єм на переслане -> бот повертає відповідь юзеру.
Чат закривається з БУДЬ-ЯКОГО боку: юзер /cancel -> адмін повідомлений;
адмін reply+/close на переслане -> юзер повідомлений і його FSM-стан
знімається (щоб зайве повідомлення юзера після закриття не пересилалось
адміну знову як нове звернення).

Мапінг "яке повідомлення в чаті адміна -> чий це юзер" — in-memory dict за
message_id, НЕ `forward_from` (юзери з прихованим форвардом (privacy) його
ховають — ненадійно) і НЕ парсинг тексту (крихко). Адміну йде ДВА
повідомлення на кожне юзерське (контекст-рядок окремо + copy_message
вмісту) — обидва message_id мапляться на той самий SupportTarget, тож
reply на БУДЬ-ЯКЕ з двох спрацює (і для відповіді, і для /close). Втрата
мапінгу при рестарті web-процесу — той самий прийнятний трейдофф, що й
FSM-стан (MemoryStorage): юзер просто пише /support знову.

Пріоритет хендлерів (aiogram: перший, чиї фільтри ВСІ пройшли, забирає
апдейт собі, далі не пробує — `TelegramEventObserver.trigger`, перевірено
в джерелі aiogram): admin_close і admin_reply зареєстровані РАНІШЕ за
support_message. Це не просто "має бути так" — конкретний живий баг був
у зворотному сценарії: якщо адмін сам колись тестував /support на собі
й не вийшов через /cancel, його FSM-стан лишається `active`; без
пріоритету його reply на СПРАВЖНЄ звернення юзера впав би в
support_message (бо і той матчиться за станом) замість admin_reply, і
відповідь юзеру НІКОЛИ не пішла б. support_message додатково явно
виключає "це reply від адміна" (`not _is_admin_reply`) — навіть якщо
колись хтось переставить порядок хендлерів, ця гілка не оживе випадково.

Мут/бан (admin_mute/admin_ban/admin_unban, SupportBan у app/models.py) —
той самий reply-на-переслане розбір через support_map, що й admin_close.
З ТІЄЇ Ж причини, що й admin_close, вони зареєстровані РАНІШЕ за
admin_reply: admin_reply — catch-all для БУДЬ-ЯКОГО reply адміна без
Command-фільтра, тож якби /mute/ban/unban були нижче, admin_reply
перехопив би їх першим і надіслав би юзеру текст "/mute" як звичайну
відповідь підтримки. /mute ставить SupportBan.muted_until = now+1год і
повідомляє юзера; /ban мовчки виставляє banned=True (юзер нічого не
отримує); /unban знімає обидва прапорці. Перевірка бану/муту сидить на
вході (cmd_support) і на кожному наступному повідомленні (support_message):
banned -> тихий ігнор без відповіді, muted -> "буде доступна через N хв".

`_is_admin`/`_is_admin_reply` — звичайні функції, не magic-filter:
`F.from_user.id == settings.ADMIN_TG_ID` обчислив би праву частину ОДИН
РАЗ при імпорті модуля (заморозив би значення) — monkeypatch у тестах на
нього б не подіяв. Функції читають settings.ADMIN_TG_ID наживо на кожен
виклик.

`storage: BaseStorage` у admin_close — інжектиться aiogram-ом через
`dp["storage"] = dp.storage` (app/bot/dispatcher.py), а не імпортом `dp`
напряму сюди: dispatcher.py й так імпортує `router` звідси, прямий імпорт
`dp` у зворотному напрямку створив би circular import.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from typing import NamedTuple

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import lang_from_telegram_code, msg
from app.models import Plan, PromoCode, PromoType
from app.security.rate_limit import InMemoryRateLimiter
from app.services.support_moderation import (
    ban_user,
    get_ban,
    mute_user,
    remaining_mute_minutes,
    unban_user,
)

logger = logging.getLogger(__name__)

router = Router(name="support")

support_limiter = InMemoryRateLimiter("support_message", max_requests=1, window_seconds=60)


class SupportTarget(NamedTuple):
    tg_id: int
    name: str
    lang: str = "uk"


# message_id (у чаті адміна) -> хто юзер, якому переслати відповідь/закрити чат.
support_map: dict[int, SupportTarget] = {}


class SupportStates(StatesGroup):
    active = State()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    lang = lang_from_telegram_code(message.from_user.language_code if message.from_user else None)
    keyboard = None
    if settings.MINI_APP_URL:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=msg("bot.open_button", lang), web_app=WebAppInfo(url=settings.MINI_APP_URL)
                    )
                ]
            ]
        )
    await message.answer(msg("bot.welcome", lang), reply_markup=keyboard)


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    lang = lang_from_telegram_code(message.from_user.language_code)

    ban = await get_ban(session, message.from_user.id)
    if ban is not None and ban.banned:
        return  # тихо ігноруємо — юзер не має знати, що забанений

    remaining = remaining_mute_minutes(ban)
    if remaining is not None:
        await message.answer(msg("bot.support_muted", lang, remaining=remaining))
        return

    await state.set_state(SupportStates.active)
    await message.answer(msg("bot.support_intro", lang))


@router.message(Command("cancel"), StateFilter(SupportStates.active))
async def cmd_cancel(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    lang = lang_from_telegram_code(message.from_user.language_code if message.from_user else None)
    await message.answer(msg("bot.support_exited", lang))

    if message.from_user is None or not settings.ADMIN_TG_ID:
        return
    user = message.from_user
    username = f"@{user.username}" if user.username else "без username"
    try:
        await bot.send_message(
            settings.ADMIN_TG_ID,
            f"❌ Користувач {user.first_name} ({username}, id={user.id}) закінчив чат",
        )
    except Exception:
        logger.warning("не вдалося повідомити адміна про /cancel tg_id=%s", user.id, exc_info=True)


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == settings.ADMIN_TG_ID


def _is_admin_reply(message: Message) -> bool:
    """Див. докстрінг модуля — чому це фільтр, а не перевірка в тілі хендлера."""
    return message.reply_to_message is not None and _is_admin(message)


@router.message(Command("close"), _is_admin)
async def admin_close(message: Message, bot: Bot, storage: BaseStorage) -> None:
    reply_to = message.reply_to_message
    target = support_map.get(reply_to.message_id) if reply_to is not None else None
    if target is None:
        await message.answer("Зробіть reply на звернення, яке хочете закрити.")
        return

    try:
        await bot.send_message(target.tg_id, msg("bot.support_closed_by_admin", target.lang))
    except Exception:
        logger.warning(
            "не вдалося повідомити юзера tg_id=%s про закриття чату", target.tg_id, exc_info=True
        )

    user_state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=bot.id, chat_id=target.tg_id, user_id=target.tg_id),
    )
    await user_state.clear()

    await message.answer(f"Чат із {target.name} закрито.")


def _resolve_reply_target(message: Message) -> SupportTarget | None:
    reply_to = message.reply_to_message
    return support_map.get(reply_to.message_id) if reply_to is not None else None


@router.message(Command("mute"), _is_admin)
async def admin_mute(message: Message, bot: Bot, session: AsyncSession) -> None:
    target = _resolve_reply_target(message)
    if target is None:
        await message.answer("Зробіть reply на звернення, яке хочете замутити.")
        return

    await mute_user(session, target.tg_id)
    try:
        await bot.send_message(target.tg_id, msg("bot.support_paused_notice", target.lang))
    except Exception:
        logger.warning("не вдалося повідомити юзера tg_id=%s про мут", target.tg_id, exc_info=True)

    await message.answer(f"{target.name} замучено в підтримці на 1 годину.")


@router.message(Command("ban"), _is_admin)
async def admin_ban(message: Message, session: AsyncSession) -> None:
    target = _resolve_reply_target(message)
    if target is None:
        await message.answer("Зробіть reply на звернення, яке хочете забанити.")
        return

    await ban_user(session, target.tg_id)
    # Тихий бан — юзер нічого не отримує, лише адмін бачить підтвердження.
    await message.answer(f"{target.name} забанено в підтримці.")


@router.message(Command("unban"), _is_admin)
async def admin_unban(message: Message, session: AsyncSession) -> None:
    target = _resolve_reply_target(message)
    if target is None:
        await message.answer("Зробіть reply на звернення, яке хочете розбанити.")
        return

    await unban_user(session, target.tg_id)
    await message.answer(f"{target.name} розбанено в підтримці.")


# --------------------------------------------------------------------------- #
#  Промокоди (фіча "промокоди") — адмін роздає доступ магазинам, що привели
#  користувачів. Розширення наявного PromoCode/redeem_promo (стадія 5a):
#  /promo_create будує рядок і одразу підтверджує зведенням (без FSM —
#  зайве для однорядкової команди), /promo_list показує активні,
#  /promo_off вимикає (is_active=False, а не видаляє — used_count і
#  історія Redemption лишаються для звітності).
# --------------------------------------------------------------------------- #
_PROMO_CREATE_USAGE = (
    "Формат: /promo_create <CODE> <trial|plan:КОД_ПЛАНУ> <днів> <макс_використань> "
    "[expires РРРР-ММ-ДД]\n"
    "Приклади:\n"
    "/promo_create WELCOME60 trial 60 5\n"
    "/promo_create VIP2026 plan:pro 30 1 expires 2026-12-31"
)


def _parse_expires(parts: list[str]) -> tuple[list[str], datetime | None]:
    """Знімає необов'язковий хвіст 'expires РРРР-ММ-ДД' з кінця аргументів.
    Повертає (решта аргументів, expires_at | None)."""
    if len(parts) >= 2 and parts[-2].lower() == "expires":
        try:
            day = datetime.strptime(parts[-1], "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Не розпізнав дату '{parts[-1]}' — формат РРРР-ММ-ДД") from None
        return parts[:-2], datetime.combine(day, time.max, tzinfo=UTC)
    return parts, None


@router.message(Command("promo_create"), _is_admin)
async def admin_promo_create(
    message: Message, command: CommandObject, session: AsyncSession
) -> None:
    raw = (command.args or "").split()
    try:
        raw, expires_at = _parse_expires(raw)
    except ValueError as exc:
        await message.answer(f"{exc}\n\n{_PROMO_CREATE_USAGE}")
        return

    if len(raw) != 4:
        await message.answer(_PROMO_CREATE_USAGE)
        return

    code_raw, kind_raw, days_raw, max_uses_raw = raw
    code = code_raw.strip().upper()

    plan: Plan | None = None
    if kind_raw == "trial":
        promo_type = PromoType.free_period
    elif kind_raw.startswith("plan:"):
        promo_type = PromoType.plan_grant
        plan_code = kind_raw.removeprefix("plan:")
        plan = await session.scalar(
            select(Plan).where(Plan.code == plan_code, Plan.is_active.is_(True))
        )
        if plan is None:
            await message.answer(f"План '{plan_code}' не знайдено серед активних тарифів.")
            return
    else:
        await message.answer(
            f"Другий аргумент має бути 'trial' або 'plan:КОД'.\n\n{_PROMO_CREATE_USAGE}"
        )
        return

    try:
        days = int(days_raw)
        max_uses = int(max_uses_raw)
        if days <= 0 or max_uses <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            f"Днів і макс. використань мають бути додатними числами.\n\n{_PROMO_CREATE_USAGE}"
        )
        return

    existing = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if existing is not None:
        await message.answer(f"Код {code} вже існує.")
        return

    promo = PromoCode(
        code=code,
        type=promo_type,
        value=days,
        plan_id=plan.id if plan else None,
        max_uses=max_uses,
        expires_at=expires_at,
    )
    session.add(promo)
    await session.commit()

    if promo_type == PromoType.free_period:
        kind_label = "тріал"
    else:
        assert plan is not None
        kind_label = f"план «{plan.name}»"
    expires_label = expires_at.strftime("%Y-%m-%d") if expires_at else "без обмеження"
    await message.answer(
        "✅ Створено промокод\n"
        f"Код: {code}\n"
        f"Тип: {kind_label}\n"
        f"Днів: {days}\n"
        f"Макс. використань: {max_uses}\n"
        f"Дійсний до: {expires_label}"
    )


@router.message(Command("promo_list"), _is_admin)
async def admin_promo_list(message: Message, session: AsyncSession) -> None:
    promos = (
        await session.scalars(
            select(PromoCode)
            .where(PromoCode.is_active.is_(True))
            .order_by(PromoCode.created_at.desc())
        )
    ).all()
    if not promos:
        await message.answer("Активних промокодів немає.")
        return

    plans_by_id = {p.id: p.name for p in (await session.scalars(select(Plan))).all()}

    lines = ["Активні промокоди:"]
    for promo in promos:
        if promo.type == PromoType.free_period:
            detail = f"тріал, {promo.value} дн."
        elif promo.type == PromoType.plan_grant:
            plan_name = plans_by_id.get(promo.plan_id, "?") if promo.plan_id else "?"
            detail = f"план «{plan_name}», {promo.value} дн."
        else:
            detail = f"знижка {promo.value}%"
        expires = promo.expires_at.strftime("%Y-%m-%d") if promo.expires_at else "без обмеження"
        lines.append(f"{promo.code} — {detail}, {promo.used_count}/{promo.max_uses}, до {expires}")

    await message.answer("\n".join(lines))


@router.message(Command("promo_off"), _is_admin)
async def admin_promo_off(
    message: Message, command: CommandObject, session: AsyncSession
) -> None:
    code = (command.args or "").strip().upper()
    if not code:
        await message.answer("Формат: /promo_off <CODE>")
        return

    promo = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if promo is None:
        await message.answer(f"Код {code} не знайдено.")
        return

    promo.is_active = False
    await session.commit()
    await message.answer(f"Код {code} вимкнено.")


@router.message(_is_admin_reply)
async def admin_reply(message: Message, bot: Bot) -> None:
    reply_to = message.reply_to_message
    assert reply_to is not None  # гарантовано фільтром _is_admin_reply

    target = support_map.get(reply_to.message_id)
    if target is None:
        return

    text = message.text or message.caption
    if not text:
        return

    try:
        await bot.send_message(target.tg_id, msg("bot.support_reply_prefix", target.lang, text=text))
    except Exception:
        logger.warning(
            "не вдалося надіслати відповідь підтримки tg_id=%s", target.tg_id, exc_info=True
        )


@router.message(StateFilter(SupportStates.active), lambda m: not _is_admin_reply(m))
async def support_message(message: Message, state: FSMContext, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = message.from_user
    lang = lang_from_telegram_code(user.language_code)

    ban = await get_ban(session, user.id)
    if ban is not None and ban.banned:
        return  # тихо ігноруємо — юзер не має знати, що забанений

    remaining = remaining_mute_minutes(ban)
    if remaining is not None:
        await message.answer(msg("bot.support_muted", lang, remaining=remaining))
        return

    if not settings.ADMIN_TG_ID:
        await message.answer(msg("bot.support_unavailable", lang))
        return

    if not support_limiter.hit(str(user.id)):
        await message.answer(msg("bot.support_rate_limited", lang))
        return

    username = f"@{user.username}" if user.username else "без username"
    context_line = f"🆘 Підтримка від {user.first_name} ({username}, id={user.id})"

    try:
        context_msg = await bot.send_message(settings.ADMIN_TG_ID, context_line)
        copied = await bot.copy_message(
            chat_id=settings.ADMIN_TG_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception:
        logger.warning("не вдалося переслати повідомлення підтримки адміну", exc_info=True)
        return

    target = SupportTarget(tg_id=user.id, name=user.first_name, lang=lang)
    support_map[context_msg.message_id] = target
    support_map[copied.message_id] = target

    await message.answer(msg("bot.support_delivered", lang))
