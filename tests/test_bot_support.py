"""
Техпідтримка через бота — юніт-тести хендлерів (app/bot/handlers.py).

Більшість тестів мокають Message/FSMContext/Bot напряму й кличуть
хендлери як звичайні async-функції — без dp.feed_update і без мережі.
Так простіше й швидше, ЛИШЕ ОДИН тест (test_admin_reply_wins_even_when_...)
свідомо йде іншим шляхом: пряме виклик функції-хендлера ОБХОДИТЬ реальний
aiogram dispatch/filter-matching, а живий баг ("reply адміна не доходив
юзеру") жив саме там — у порядку, в якому aiogram перебирає зареєстровані
хендлери. Такий клас багів прямий виклик handlers.admin_reply(...) в
принципі не міг би зловити, тож для НЬОГО ганяємо справжній Update через
dp.feed_update з реальним (але без мережі — Bot.send_message замокано)
Bot, як test_stage5a.py.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from app.bot import handlers
from app.config import settings
from tests.conftest import TEST_BOT_TOKEN


def _make_user(tg_id: int, first_name: str = "Тест", username: str | None = None) -> MagicMock:
    user = MagicMock()
    user.id = tg_id
    user.first_name = first_name
    user.username = username
    return user


def _make_message(
    *,
    tg_id: int = 1001,
    text: str | None = "Привіт, у мене проблема",
    caption: str | None = None,
    reply_to_message: MagicMock | None = None,
    first_name: str = "Тест",
    username: str | None = "test_user",
    message_id: int = 500,
) -> MagicMock:
    message = MagicMock()
    message.from_user = _make_user(tg_id, first_name, username)
    message.text = text
    message.caption = caption
    message.reply_to_message = reply_to_message
    message.message_id = message_id
    message.chat = MagicMock()
    message.chat.id = tg_id
    message.answer = AsyncMock()
    return message


@pytest.fixture(autouse=True)
def _reset_support_state(monkeypatch: pytest.MonkeyPatch):
    handlers.support_map.clear()
    monkeypatch.setattr(settings, "ADMIN_TG_ID", 999999)
    yield
    handlers.support_map.clear()


@pytest.mark.asyncio
async def test_cmd_start_greets_with_open_button_when_mini_app_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MINI_APP_URL", "https://app.example.test")
    message = _make_message()

    await handlers.cmd_start(message)

    message.answer.assert_awaited_once()
    _, kwargs = message.answer.call_args
    markup = kwargs["reply_markup"]
    button = markup.inline_keyboard[0][0]
    assert button.web_app.url == "https://app.example.test"


@pytest.mark.asyncio
async def test_cmd_start_greets_without_button_when_mini_app_url_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MINI_APP_URL", "")
    message = _make_message()

    await handlers.cmd_start(message)

    message.answer.assert_awaited_once()
    _, kwargs = message.answer.call_args
    assert kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_cmd_start_does_not_touch_fsm_state_or_create_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/start нічого не створює (shop lifecycle — POST /api/shops, не бот)."""
    monkeypatch.setattr(settings, "MINI_APP_URL", "")
    message = _make_message()

    await handlers.cmd_start(message)

    text = message.answer.call_args.args[0]
    assert "магазин" not in text.lower()


@pytest.mark.asyncio
async def test_cmd_support_sets_active_state_and_greets() -> None:
    message = _make_message()
    state = AsyncMock()

    await handlers.cmd_support(message, state)

    state.set_state.assert_awaited_once_with(handlers.SupportStates.active)
    message.answer.assert_awaited_once()
    assert "підтримкою" in message.answer.call_args.args[0]
    assert "/cancel" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_cancel_clears_state() -> None:
    message = _make_message()
    state = AsyncMock()
    bot = AsyncMock()

    await handlers.cmd_cancel(message, state, bot)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once_with("Ви вийшли з режиму підтримки.")


@pytest.mark.asyncio
async def test_cmd_cancel_notifies_admin() -> None:
    message = _make_message(tg_id=2010, first_name="Ольга", username="olya")
    state = AsyncMock()
    bot = AsyncMock()

    await handlers.cmd_cancel(message, state, bot)

    bot.send_message.assert_awaited_once()
    admin_id_arg, text = bot.send_message.call_args.args
    assert admin_id_arg == settings.ADMIN_TG_ID
    assert "закінчив чат" in text
    assert "Ольга" in text
    assert "@olya" in text
    assert "id=2010" in text


@pytest.mark.asyncio
async def test_cmd_cancel_skips_admin_notification_when_admin_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADMIN_TG_ID", 0)
    message = _make_message()
    state = AsyncMock()
    bot = AsyncMock()

    await handlers.cmd_cancel(message, state, bot)

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_support_message_forwards_to_admin_with_id_in_context_line() -> None:
    message = _make_message(
        tg_id=2002, text="Не працює кнопка", first_name="Ольга", username="olya", message_id=600
    )
    state = AsyncMock()
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=701))
    bot.copy_message = AsyncMock(return_value=MagicMock(message_id=702))

    await handlers.support_message(message, state, bot)

    bot.send_message.assert_awaited_once()
    admin_id_arg, context_text = bot.send_message.call_args.args
    assert admin_id_arg == settings.ADMIN_TG_ID
    assert "id=2002" in context_text
    assert "Ольга" in context_text
    assert "@olya" in context_text

    bot.copy_message.assert_awaited_once_with(
        chat_id=settings.ADMIN_TG_ID, from_chat_id=2002, message_id=600
    )

    assert handlers.support_map[701] == handlers.SupportTarget(2002, "Ольга")
    assert handlers.support_map[702] == handlers.SupportTarget(2002, "Ольга")
    message.answer.assert_awaited_once_with("Передано ✅")


@pytest.mark.asyncio
async def test_support_message_without_username_falls_back() -> None:
    message = _make_message(tg_id=2003, username=None)
    state = AsyncMock()
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=711))
    bot.copy_message = AsyncMock(return_value=MagicMock(message_id=712))

    await handlers.support_message(message, state, bot)

    context_text = bot.send_message.call_args.args[1]
    assert "без username" in context_text


@pytest.mark.asyncio
async def test_admin_reply_sends_answer_to_mapped_user() -> None:
    handlers.support_map[701] = handlers.SupportTarget(2002, "Тест")
    reply_to = MagicMock(message_id=701)
    admin_message = _make_message(
        tg_id=settings.ADMIN_TG_ID,
        text="Спробуйте оновити застосунок",
        reply_to_message=reply_to,
    )
    bot = AsyncMock()

    await handlers.admin_reply(admin_message, bot)

    bot.send_message.assert_awaited_once_with(
        2002, "💬 Відповідь підтримки:\nСпробуйте оновити застосунок"
    )


@pytest.mark.asyncio
async def test_admin_reply_ignores_unmapped_reply() -> None:
    reply_to = MagicMock(message_id=999999)  # не в мапі
    admin_message = _make_message(tg_id=settings.ADMIN_TG_ID, reply_to_message=reply_to)
    bot = AsyncMock()

    await handlers.admin_reply(admin_message, bot)

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_admin_close_closes_chat_clears_user_state_and_confirms_to_admin() -> None:
    storage = MemoryStorage()
    bot_id = 555
    user_tg_id = 2020
    user_key = StorageKey(bot_id=bot_id, chat_id=user_tg_id, user_id=user_tg_id)
    user_state = FSMContext(storage=storage, key=user_key)
    await user_state.set_state(handlers.SupportStates.active)

    handlers.support_map[701] = handlers.SupportTarget(user_tg_id, "Ольга")
    reply_to = MagicMock(message_id=701)
    admin_message = _make_message(
        tg_id=settings.ADMIN_TG_ID, text="/close", reply_to_message=reply_to
    )
    bot = AsyncMock()
    bot.id = bot_id

    await handlers.admin_close(admin_message, bot, storage)

    bot.send_message.assert_awaited_once_with(
        user_tg_id, "Адміністратор закінчив чат підтримки. Дякуємо за звернення!"
    )
    assert await user_state.get_state() is None
    admin_message.answer.assert_awaited_once_with("Чат із Ольга закрито.")


@pytest.mark.asyncio
async def test_admin_close_without_reply_shows_hint() -> None:
    storage = MemoryStorage()
    admin_message = _make_message(
        tg_id=settings.ADMIN_TG_ID, text="/close", reply_to_message=None
    )
    bot = AsyncMock()

    await handlers.admin_close(admin_message, bot, storage)

    admin_message.answer.assert_awaited_once()
    hint = admin_message.answer.call_args.args[0]
    assert "reply" in hint.lower()
    assert "звернення" in hint.lower()
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_admin_close_unmapped_reply_shows_hint() -> None:
    storage = MemoryStorage()
    reply_to = MagicMock(message_id=999999)  # не в мапі
    admin_message = _make_message(
        tg_id=settings.ADMIN_TG_ID, text="/close", reply_to_message=reply_to
    )
    bot = AsyncMock()

    await handlers.admin_close(admin_message, bot, storage)

    admin_message.answer.assert_awaited_once()
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_admin_reply_wins_even_when_admin_is_in_active_support_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Регресія: живий тест показав, що reply адміна не завжди доходив
    юзеру, коли адмін сам колись тестував /support на собі й не вийшов
    через /cancel (його ВЛАСНИЙ FSM-стан лишався active). Прямий виклик
    handlers.admin_reply(...) НЕ міг би зловити цей клас багів — тут
    справжній Update іде через dp.feed_update, і саме порядок реєстрації
    хендлерів (admin_reply РАНІШЕ за support_message) вирішує, хто
    забирає апдейт."""
    from app.bot.dispatcher import dp

    admin_tg_id = settings.ADMIN_TG_ID
    user_tg_id = 8001
    handlers.support_map.clear()
    handlers.support_map[555] = handlers.SupportTarget(user_tg_id, "Юзер")

    sent: list[tuple[int, str]] = []

    async def fake_send_message(self, chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return MagicMock(message_id=999)

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    bot = Bot(token=TEST_BOT_TOKEN)

    admin_state = FSMContext(
        storage=dp.storage,
        key=StorageKey(bot_id=bot.id, chat_id=admin_tg_id, user_id=admin_tg_id),
    )
    await admin_state.set_state(handlers.SupportStates.active)

    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 600,
                "date": int(time.time()),
                "chat": {"id": admin_tg_id, "type": "private"},
                "from": {"id": admin_tg_id, "is_bot": False, "first_name": "Адмін"},
                "text": "Спробуйте перезапустити застосунок",
                "reply_to_message": {
                    "message_id": 555,
                    "date": int(time.time()),
                    "chat": {"id": admin_tg_id, "type": "private"},
                    "from": {"id": bot.id, "is_bot": True, "first_name": "Bot"},
                    "text": "🆘 Підтримка від Юзер (id=8001)",
                },
            },
        }
    )

    try:
        await dp.feed_update(bot, update)
    finally:
        await admin_state.clear()
        handlers.support_map.clear()

    assert (
        user_tg_id,
        "💬 Відповідь підтримки:\nСпробуйте перезапустити застосунок",
    ) in sent


def test_is_admin_reply_filter_rejects_non_admin_reply() -> None:
    """Ключова гарантія: reply від ЗВИЧАЙНОГО юзера (не адміна) не повинен
    матчити admin_reply — інакше support_message ніколи не отримає update
    (aiogram консьюмить update тим хендлером, чий фільтр збігся першим)."""
    reply_to = MagicMock(message_id=701)
    user_message = _make_message(tg_id=2002, reply_to_message=reply_to)

    assert handlers._is_admin_reply(user_message) is False


def test_is_admin_reply_filter_accepts_admin_reply() -> None:
    reply_to = MagicMock(message_id=701)
    admin_message = _make_message(tg_id=settings.ADMIN_TG_ID, reply_to_message=reply_to)

    assert handlers._is_admin_reply(admin_message) is True


def test_is_admin_reply_filter_rejects_non_reply_message() -> None:
    admin_message = _make_message(tg_id=settings.ADMIN_TG_ID, reply_to_message=None)

    assert handlers._is_admin_reply(admin_message) is False


@pytest.mark.asyncio
async def test_rate_limit_blocks_second_message_within_60s() -> None:
    state = AsyncMock()
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=801))
    bot.copy_message = AsyncMock(return_value=MagicMock(message_id=802))

    message1 = _make_message(tg_id=3003, message_id=900)
    await handlers.support_message(message1, state, bot)
    assert message1.answer.await_args.args[0] == "Передано ✅"

    message2 = _make_message(tg_id=3003, message_id=901)
    await handlers.support_message(message2, state, bot)
    assert (
        message2.answer.await_args.args[0]
        == "Зачекайте хвилину перед наступним повідомленням."
    )
    # другий виклик не мав дійти до пересилання
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_support_message_without_admin_configured_tells_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADMIN_TG_ID", 0)
    message = _make_message(tg_id=4004)
    state = AsyncMock()
    bot = AsyncMock()

    await handlers.support_message(message, state, bot)

    message.answer.assert_awaited_once_with("Підтримка тимчасово недоступна.")
    bot.send_message.assert_not_called()
