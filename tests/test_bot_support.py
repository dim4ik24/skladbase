"""
Техпідтримка через бота — юніт-тести хендлерів (app/bot/handlers.py).

Мокаються Message/FSMContext/Bot напряму, хендлери викликаються як звичайні
async-функції — без dp.feed_update і без мережі. На відміну від
test_stage5a.py (платіжні хендлери не роблять жодних вихідних викликів
Telegram API, тож фідити через реальний dp з реальним Bot безпечно) — тут
хендлери активно кличуть message.answer/bot.send_message/bot.copy_message,
фідити через dp довелось би мокати aiohttp-сесію бота, а це складніше й
крихкіше за прямий виклик функцій.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot import handlers
from app.config import settings


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

    await handlers.cmd_cancel(message, state)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once_with("Ви вийшли з режиму підтримки.")


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

    assert handlers.support_map[701] == 2002
    assert handlers.support_map[702] == 2002
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
    handlers.support_map[701] = 2002
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
