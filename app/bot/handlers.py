"""
SkladBase — техпідтримка через бота (FSM-режим).

Юзер пише /support -> усе, що він пише далі, пересилається адміну
(`settings.ADMIN_TG_ID`) з контекстним рядком (ім'я, username, tg_id).
Адмін відповідає REPLY'єм на переслане -> бот повертає відповідь юзеру.

Мапінг "яке повідомлення в чаті адміна -> чий це юзер" — in-memory dict за
message_id, НЕ `forward_from` (юзери з прихованим форвардом (privacy) його
ховають — ненадійно) і НЕ парсинг тексту (крихко). Адміну йде ДВА
повідомлення на кожне юзерське (контекст-рядок окремо + copy_message
вмісту) — обидва message_id мапляться на той самий tg_id, тож reply на
БУДЬ-ЯКЕ з двох спрацює. Втрата мапінгу при рестарті web-процесу — той
самий прийнятний трейдофф, що й FSM-стан (MemoryStorage): юзер просто
пише /support знову.

`from_user.id == settings.ADMIN_TG_ID` перевіряється у ФІЛЬТРІ хендлера
(`_is_admin_reply`), не всередині його тіла. Причина: якщо фільтр —
лише "це reply" (а перевірку автора зробити вже в тілі), aiogram once і
назавжди віддає update саме сюди, щойно фільтр збігся, — і звичайний
юзер-НЕ-адмін, що в active-стані відповість reply'єм на своє ж
повідомлення (описуючи проблему), потрапить у ЦЕЙ хендлер, тіло зробить
ранній `return`, і повідомлення НІКОЛИ не дійде до `support_message` —
загубиться замість пересилання адміну. Автора треба відсіювати ще на
рівні фільтра, щоб aiogram сам пробував наступний хендлер.

`_is_admin_reply` — звичайна функція, не magic-filter: `F.from_user.id ==
settings.ADMIN_TG_ID` обчислив би праву частину ОДИН РАЗ при імпорті
модуля (заморозив би значення) — monkeypatch у тестах на нього б не
подіяв. Функція читає settings.ADMIN_TG_ID наживо на кожен виклик.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.config import settings
from app.security.rate_limit import InMemoryRateLimiter

logger = logging.getLogger(__name__)

router = Router(name="support")

support_limiter = InMemoryRateLimiter("support_message", max_requests=1, window_seconds=60)

# message_id (у чаті адміна) -> tg_id юзера, якому переслати відповідь.
support_map: dict[int, int] = {}


class SupportStates(StatesGroup):
    active = State()


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext) -> None:
    await state.set_state(SupportStates.active)
    await message.answer(
        "Ви на зв'язку з підтримкою. Опишіть проблему — я передам адміністратору.\n"
        "Для виходу — /cancel"
    )


@router.message(Command("cancel"), StateFilter(SupportStates.active))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ви вийшли з режиму підтримки.")


def _is_admin_reply(message: Message) -> bool:
    """Див. докстрінг модуля — чому це фільтр, а не перевірка в тілі хендлера."""
    return message.reply_to_message is not None and (
        message.from_user is not None and message.from_user.id == settings.ADMIN_TG_ID
    )


@router.message(_is_admin_reply)
async def admin_reply(message: Message, bot: Bot) -> None:
    reply_to = message.reply_to_message
    assert reply_to is not None  # гарантовано фільтром _is_admin_reply

    user_tg_id = support_map.get(reply_to.message_id)
    if user_tg_id is None:
        return

    text = message.text or message.caption
    if not text:
        return

    try:
        await bot.send_message(user_tg_id, f"💬 Відповідь підтримки:\n{text}")
    except Exception:
        logger.warning(
            "не вдалося надіслати відповідь підтримки tg_id=%s", user_tg_id, exc_info=True
        )


@router.message(StateFilter(SupportStates.active))
async def support_message(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.from_user is None:
        return
    user = message.from_user

    if not settings.ADMIN_TG_ID:
        await message.answer("Підтримка тимчасово недоступна.")
        return

    if not support_limiter.hit(str(user.id)):
        await message.answer("Зачекайте хвилину перед наступним повідомленням.")
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

    support_map[context_msg.message_id] = user.id
    support_map[copied.message_id] = user.id

    await message.answer("Передано ✅")
