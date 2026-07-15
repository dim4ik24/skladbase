"""
SkladBase — бекенд-i18n для тексту, що летить з API/бота (i18n Стадія 4).

Фронт (TMA) уже тримовний (uk/en/ru, react-i18next) — лишились рядки, що
народжуються НА БЕКЕНДІ: `HTTPException.detail` (422/409/404...) і
повідомлення бота. Механізм навмисно простий (без babel/gettext):

    MESSAGES: dict[key] -> {"uk": ..., "en": ..., "ru": ...}
    msg(key, lang, **fmt) -> MESSAGES[key][lang].format(**fmt)

Мова запиту з Mini App — заголовок `X-App-Language` (фронт шле поточну
i18n.language, див. api.ts), дефолт `uk`; мова в боті — `User.language_code`
з Telegram (aiogram), той самий дефолт. `get_lang()` — FastAPI-залежність,
що читає заголовок і кладе результат у `request.state.lang` (для коду, що
має `request`, але не хоче повторно оголошувати залежність).

Термінологія узгоджена з frontend/app/src/i18n/locales/*.json — де ключ
описує той самий концепт (напр. ТТН/waybill, залишок/stock, резерв/
reservation), формулювання звірене з фронтовим словником.

НЕ перекладається (свідомо, не забутий рядок):
  - Тексти, що приходять від САМОГО API Нової Пошти (`data["errors"]` /
    `errorCodes` у app/services/novaposhta.py, і все, що потрапляє під
    обгортку `f"НП: {exc}"` в np_shipping.py/np_documents.py) — це чужий
    текст, ми не знаємо його мову і не повинні прикидатись, що переклали.
  - Технічні internal-invariant повідомлення, що не мають дійти до
    користувача при нормальній роботі (SubscriptionService._transition,
    RuntimeError у bootstrap.py, CryptoError, RefError, ValueError при
    реєстрації rate-лімітера) — не є частиною UI-поверхні: або застряють
    у except-блоці, що їх ковтає (CryptoError, RefError у вебхуках), або
    зраджують баг/misconfig, не дію користувача.
  - InitDataError (app/security/initdata.py) — межа Telegram-auth протоколу
    (підпис/структура/свіжість initData); нормальний юзер її не бачить,
    зʼявляється лише при тамперингу чи зламаній сесії.
  - Адмінські команди бота (/promo_create і відповіді на них) — адмін один,
    і він україномовний.
"""
from __future__ import annotations

from typing import Any, Final

from fastapi import Header, Request

SUPPORTED_LANGS: Final = ("uk", "en", "ru")
DEFAULT_LANG: Final = "uk"


def _normalize_lang(raw: str | None) -> str:
    return raw if raw in SUPPORTED_LANGS else DEFAULT_LANG


# --------------------------------------------------------------------------- #
#  FastAPI: мова запиту з X-App-Language
# --------------------------------------------------------------------------- #
def get_lang(
    request: Request,
    x_app_language: str | None = Header(default=None, alias="X-App-Language"),
) -> str:
    """Залежність для роутів: `lang: str = Depends(get_lang)`. Заодно кладе
    результат у `request.state.lang` — інші залежності в тому самому запиті
    (напр. `resolve_membership`), що вже мають `request`, можуть прочитати
    його напряму без повторного `Depends(get_lang)`."""
    lang = _normalize_lang(x_app_language)
    request.state.lang = lang
    return lang


def lang_from_request(request: Request) -> str:
    """Для коду, що не хоче оголошувати `Depends(get_lang)` (напр. функції,
    які й так приймають `request` з іншої причини) — читає те, що поклав
    `get_lang`, з дефолтом uk, якщо він з якоїсь причини не викликався."""
    return _normalize_lang(getattr(request.state, "lang", None))


# --------------------------------------------------------------------------- #
#  Бот: мова з Telegram `language_code` (BCP-47, напр. "en-US", "uk")
# --------------------------------------------------------------------------- #
def lang_from_telegram_code(code: str | None) -> str:
    """`language_code` з aiogram `User` (live-повідомлення) або збереженого
    `Shop.owner_language_code` (для cron-пушів без live Update, зафіксованого
    при bootstrap_shop). Той самий startswith-мапінг, що й фронтове
    `languageFromTelegram()` (frontend/app/src/i18n/index.ts) — консистентність
    між тим, яку мову юзер бачить у Mini App, і якою бот йому пише."""
    if code:
        if code.startswith("en"):
            return "en"
        if code.startswith("ru"):
            return "ru"
    return DEFAULT_LANG


# --------------------------------------------------------------------------- #
#  Рендер
# --------------------------------------------------------------------------- #
def msg(key: str, lang: str | None = None, /, **fmt: Any) -> str:
    """MESSAGES[key][lang].format(**fmt), з фолбеком lang -> uk -> сирий key
    (щоб забутий ключ у словнику падав помітно, а не мовчки). `key`/`lang` —
    positional-only: шаблони самі мають fmt-змінні `{key}`/`{lang}` зрідка
    (див. ServiceError.__init__ docstring — той самий колізійний сценарій)."""
    lang = _normalize_lang(lang)
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return template.format(**fmt)


class ServiceError(Exception):
    """Базовий клас для сервісних помилок з HTTP статус-кодом і відкладеним
    рендером тексту. Сервісний шар (app/services/*.py) НЕ знає мову запиту —
    він лише передає `key` (+ `**fmt` для інтерполяції) або `raw` (готовий
    рядок, що ОБХОДИТЬ переклад — passthrough, напр. текст від НП API).
    API-шар (app/api/*.py), де мова вже відома через `Depends(get_lang)`,
    рендерить фінальний detail викликом `.detail(lang)`.

    Рівно один з key/raw має бути заданий.

    `key` — positional-only (`/`): багато шаблонів самі мають fmt-змінну
    `{key}` (напр. template.key_required — назва поля схеми) — без `/` вона
    зіткнулася б із цим-таки параметром при виклику `SomeError(422, "...",
    key=field_key)` (`got multiple values for argument 'key'`)."""

    def __init__(
        self,
        status_code: int,
        key: str | None = None,
        /,
        *,
        raw: str | None = None,
        **fmt: Any,
    ) -> None:
        if (key is None) == (raw is None):
            raise TypeError("ServiceError: pass exactly one of key or raw")
        self.status_code = status_code
        self.key = key
        self.raw = raw
        self.fmt = fmt
        if raw is not None:
            super().__init__(raw)
        else:
            assert key is not None
            super().__init__(msg(key, DEFAULT_LANG, **fmt))

    def detail(self, lang: str | None = None) -> str:
        if self.raw is not None:
            return self.raw
        assert self.key is not None
        return msg(self.key, lang, **self.fmt)


# --------------------------------------------------------------------------- #
#  Словник повідомлень
# --------------------------------------------------------------------------- #
MESSAGES: Final[dict[str, dict[str, str]]] = {
    # --- catalog (app/services/catalog.py, app/api/catalog.py) ---------- #
    "catalog.plan_limit_products": {
        "uk": "Ліміт плану: {max} товарів. Оформіть тариф для розширення.",
        "en": "Plan limit: {max} products. Upgrade to add more.",
        "ru": "Лимит тарифа: {max} товаров. Оформите тариф для расширения.",
    },
    "catalog.product_frozen": {
        "uk": "Цей товар заморожено. Оформіть тариф, щоб редагувати.",
        "en": "This product is frozen. Upgrade to edit it.",
        "ru": "Этот товар заморожен. Оформите тариф, чтобы редактировать.",
    },
    "catalog.photos_not_allowed": {
        "uk": "Фото доступні на тарифі Basic+. Оформіть тариф.",
        "en": "Photos are available on the Basic+ plan. Upgrade to unlock them.",
        "ru": "Фото доступны на тарифе Basic+. Оформите тариф.",
    },
    "catalog.unknown_axes": {
        "uk": "Невідомі осі варіанта: {axes}",
        "en": "Unknown variant axes: {axes}",
        "ru": "Неизвестные оси варианта: {axes}",
    },
    "catalog.missing_axes": {
        "uk": "Не вказані осі варіанта: {axes}",
        "en": "Missing variant axes: {axes}",
        "ru": "Не указаны оси варианта: {axes}",
    },
    "catalog.invalid_axis_value": {
        "uk": "Недопустиме значення '{value}' для осі '{key}'",
        "en": "Invalid value '{value}' for axis '{key}'",
        "ru": "Недопустимое значение '{value}' для оси '{key}'",
    },
    "catalog.template_not_found": {
        "uk": "Шаблон не знайдено",
        "en": "Template not found",
        "ru": "Шаблон не найден",
    },
    "catalog.variant_required": {
        "uk": "Потрібен хоча б один варіант",
        "en": "At least one variant is required",
        "ru": "Нужен хотя бы один вариант",
    },
    "catalog.sku_taken": {
        "uk": "SKU вже використовується в цьому магазині",
        "en": "This SKU is already used in this shop",
        "ru": "Этот SKU уже используется в этом магазине",
    },
    "catalog.product_create_conflict": {
        "uk": "Не вдалося створити товар через конфлікт даних",
        "en": "Couldn't create the product due to a data conflict",
        "ru": "Не удалось создать товар из-за конфликта данных",
    },
    "catalog.variant_not_found": {
        "uk": "Варіант не знайдено",
        "en": "Variant not found",
        "ru": "Вариант не найден",
    },
    "catalog.variant_axes_conflict": {
        "uk": "Варіант з такими осями вже існує",
        "en": "A variant with these axes already exists",
        "ru": "Вариант с такими осями уже существует",
    },
    "catalog.variant_update_failed": {
        "uk": "Не вдалося оновити варіант",
        "en": "Couldn't update the variant",
        "ru": "Не удалось обновить вариант",
    },
    "catalog.product_not_found": {
        "uk": "Товар не знайдено",
        "en": "Product not found",
        "ru": "Товар не найден",
    },
    "catalog.variant_add_failed": {
        "uk": "Не вдалося додати варіант",
        "en": "Couldn't add the variant",
        "ru": "Не удалось добавить вариант",
    },
    "catalog.product_needs_variant": {
        "uk": "Товар має лишити хоча б один варіант",
        "en": "The product must keep at least one variant",
        "ru": "У товара должен остаться хотя бы один вариант",
    },
    "catalog.release_before_delete": {
        "uk": "Зніміть резерви перед видаленням варіанта",
        "en": "Release reservations before deleting the variant",
        "ru": "Снимите резервы перед удалением варианта",
    },
    "catalog.photo_not_found": {
        "uk": "Фото не знайдено",
        "en": "Photo not found",
        "ru": "Фото не найдено",
    },
    "catalog.photo_limit": {
        "uk": "Максимум 10 фото на товар",
        "en": "Maximum 10 photos per product",
        "ru": "Максимум 10 фото на товар",
    },
    # --- inventory (app/services/inventory.py) --------------------------- #
    "inventory.ttn_format": {
        "uk": "ТТН Нової Пошти — 14 цифр, починається з 20 або 59",
        "en": "Nova Poshta waybill number — 14 digits, starts with 20 or 59",
        "ru": "Номер накладной Нова Пошта — 14 цифр, начинается с 20 или 59",
    },
    "inventory.reservation_not_found": {
        "uk": "Резерв не знайдено",
        "en": "Reservation not found",
        "ru": "Резерв не найден",
    },
    "inventory.qty_positive": {
        "uk": "qty має бути додатнім",
        "en": "qty must be positive",
        "ru": "qty должно быть положительным",
    },
    "inventory.insufficient_stock": {
        "uk": "Недостатньо залишку: доступно {available}, потрібно {qty}",
        "en": "Not enough stock: {available} available, {qty} needed",
        "ru": "Недостаточно остатка: доступно {available}, нужно {qty}",
    },
    "inventory.unknown_reason": {
        "uk": "Невідома причина: {reason}",
        "en": "Unknown reason: {reason}",
        "ru": "Неизвестная причина: {reason}",
    },
    "inventory.comment_required": {
        "uk": "Для причини 'other' коментар обов'язковий",
        "en": "A comment is required for reason 'other'",
        "ru": "Для причины 'other' комментарий обязателен",
    },
    "inventory.reservation_not_active": {
        "uk": "Резерв не активний",
        "en": "Reservation is not active",
        "ru": "Резерв не активен",
    },
    "inventory.insufficient_stock_fulfill": {
        "uk": "Недостатньо залишку для списання резерву",
        "en": "Not enough stock to fulfill the reservation",
        "ru": "Недостаточно остатка для списания резерва",
    },
    "inventory.reservation_not_shipped": {
        "uk": "Резерв не відправлено",
        "en": "Reservation hasn't been shipped",
        "ru": "Резерв не отправлен",
    },
    "inventory.insufficient_available": {
        "uk": "Недостатньо доступного залишку: доступно {available}, потрібно {qty}",
        "en": "Not enough available stock: {available} available, {qty} needed",
        "ru": "Недостаточно доступного остатка: доступно {available}, нужно {qty}",
    },
    "inventory.insufficient_available_writeoff": {
        "uk": "Недостатньо доступного залишку: доступно {available}, потрібно списати {qty}",
        "en": "Not enough available stock: {available} available, need to write off {qty}",
        "ru": "Недостаточно доступного остатка: доступно {available}, нужно списать {qty}",
    },
    # --- media (app/services/media.py) ------------------------------------ #
    "media.unsupported_type": {
        "uk": "Непідтримуваний тип файлу: '{content_type}'. Дозволено: jpeg, png, webp.",
        "en": "Unsupported file type: '{content_type}'. Allowed: jpeg, png, webp.",
        "ru": "Неподдерживаемый тип файла: '{content_type}'. Разрешено: jpeg, png, webp.",
    },
    "media.file_too_large": {
        "uk": "Файл занадто великий: максимум {max_mb} МБ.",
        "en": "File is too large: maximum {max_mb} MB.",
        "ru": "Файл слишком большой: максимум {max_mb} МБ.",
    },
    "media.invalid_image": {
        "uk": "Файл не є валідним зображенням",
        "en": "The file is not a valid image",
        "ru": "Файл не является допустимым изображением",
    },
    # --- Nova Poshta wrappers (наші тексти, НЕ відповіді НП API) --------- #
    "np.key_invalid": {
        "uk": "Ключ не пройшов перевірку",
        "en": "The key failed validation",
        "ru": "Ключ не прошёл проверку",
    },
    "np.key_required": {
        "uk": "Підключіть ключ Нової Пошти в налаштуваннях",
        "en": "Connect your Nova Poshta key in Settings",
        "ru": "Подключите ключ Нова Пошта в настройках",
    },
    "np.sender_details_required": {
        "uk": "Заповніть дані відправника в налаштуваннях",
        "en": "Fill in sender details in Settings",
        "ru": "Заполните данные отправителя в Настройках",
    },
    # --- team (app/api/team.py) ------------------------------------------ #
    "team.invite_not_found": {
        "uk": "інвайт не знайдено",
        "en": "invite not found",
        "ru": "приглашение не найдено",
    },
    "team.role_name_taken": {
        "uk": "роль з такою назвою вже існує",
        "en": "a role with this name already exists",
        "ru": "роль с таким названием уже существует",
    },
    "team.role_not_found": {
        "uk": "роль не знайдено",
        "en": "role not found",
        "ru": "роль не найдена",
    },
    "team.owner_role_protected": {
        "uk": "Роль власника завжди має всі права",
        "en": "The owner role always has full access",
        "ru": "Роль владельца всегда имеет все права",
    },
    "team.system_role_protected": {
        "uk": "Системну роль не можна видалити",
        "en": "System roles can't be deleted",
        "ru": "Системную роль нельзя удалить",
    },
    "team.role_has_members": {
        "uk": "Спершу переведіть учасників на іншу роль",
        "en": "Move members to another role first",
        "ru": "Сначала переведите участников на другую роль",
    },
    "team.member_not_found": {
        "uk": "учасника не знайдено",
        "en": "member not found",
        "ru": "участник не найден",
    },
    "team.owner_role_immutable": {
        "uk": "роль owner'а незмінна",
        "en": "the owner's role can't be changed",
        "ru": "роль владельца нельзя изменить",
    },
    "team.owner_permissions_immutable": {
        "uk": "права owner'а незмінні",
        "en": "the owner's permissions can't be changed",
        "ru": "права владельца нельзя изменить",
    },
    "team.cannot_remove_self": {
        "uk": "не можна видалити самого себе",
        "en": "you can't remove yourself",
        "ru": "нельзя удалить самого себя",
    },
    "team.cannot_remove_owner": {
        "uk": "не можна видалити owner'а",
        "en": "the owner can't be removed",
        "ru": "владельца нельзя удалить",
    },
    # --- billing / promo (app/api/billing.py, app/services/subscriptions.py) #
    "billing.subscription_not_found": {
        "uk": "Підписку не знайдено",
        "en": "Subscription not found",
        "ru": "Подписка не найдена",
    },
    "billing.plan_not_found": {
        "uk": "План не знайдено",
        "en": "Plan not found",
        "ru": "План не найден",
    },
    "billing.free_plan_no_payment": {
        "uk": "Безкоштовний план не потребує оплати",
        "en": "The free plan doesn't require payment",
        "ru": "Бесплатный план не требует оплаты",
    },
    "billing.shop_not_found": {
        "uk": "Магазин не знайдено",
        "en": "Shop not found",
        "ru": "Магазин не найден",
    },
    "billing.promo_not_found": {
        "uk": "Код не знайдено",
        "en": "Code not found",
        "ru": "Код не найден",
    },
    "billing.promo_already_used": {
        "uk": "Ви вже використали цей код",
        "en": "You've already used this code",
        "ru": "Вы уже использовали этот код",
    },
    "billing.promo_exhausted": {
        "uk": "Код вичерпано або прострочено",
        "en": "The code has expired or run out",
        "ru": "Код исчерпан или просрочен",
    },
    "billing.promo_plan_not_found": {
        "uk": "План промокоду не знайдено",
        "en": "The promo code's plan wasn't found",
        "ru": "План промокода не найден",
    },
    # --- orders (app/services/orders.py) ---------------------------------- #
    "orders.order_not_found": {
        "uk": "Замовлення не знайдено",
        "en": "Order not found",
        "ru": "Заказ не найден",
    },
    "orders.item_required": {
        "uk": "Потрібен хоча б один товар у замовленні",
        "en": "At least one item is required in the order",
        "ru": "Нужен хотя бы один товар в заказе",
    },
    "orders.variant_not_found": {
        "uk": "Варіант {variant_id} не знайдено",
        "en": "Variant {variant_id} not found",
        "ru": "Вариант {variant_id} не найден",
    },
    "orders.not_pending": {
        "uk": "Замовлення вже не очікує підтвердження",
        "en": "The order is no longer pending confirmation",
        "ru": "Заказ уже не ожидает подтверждения",
    },
    "orders.cannot_cancel": {
        "uk": "Замовлення не можна скасувати в цьому статусі",
        "en": "The order can't be canceled in this status",
        "ru": "Заказ нельзя отменить в этом статусе",
    },
    # --- templates (app/services/templates.py) ---------------------------- #
    "template.schema_must_be_object": {
        "uk": "field_schema має бути об'єктом",
        "en": "field_schema must be an object",
        "ru": "field_schema должен быть объектом",
    },
    "template.attributes_must_be_list": {
        "uk": "attributes має бути списком",
        "en": "attributes must be a list",
        "ru": "attributes должен быть списком",
    },
    "template.axes_must_be_list": {
        "uk": "variant_axes має бути списком",
        "en": "variant_axes must be a list",
        "ru": "variant_axes должен быть списком",
    },
    "template.field_must_be_object": {
        "uk": "кожне поле має бути об'єктом",
        "en": "each field must be an object",
        "ru": "каждое поле должно быть объектом",
    },
    "template.key_required": {
        "uk": "key має бути непорожнім рядком, отримано: {key!r}",
        "en": "key must be a non-empty string, got: {key!r}",
        "ru": "key должен быть непустой строкой, получено: {key!r}",
    },
    "template.key_format": {
        "uk": "key '{key}' має починатися з літери і містити лише [a-zA-Z0-9_]",
        "en": "key '{key}' must start with a letter and contain only [a-zA-Z0-9_]",
        "ru": "key '{key}' должен начинаться с буквы и содержать только [a-zA-Z0-9_]",
    },
    "template.key_duplicate": {
        "uk": "Дублікат key '{key}' у field_schema",
        "en": "Duplicate key '{key}' in field_schema",
        "ru": "Дубликат key '{key}' в field_schema",
    },
    "template.label_required": {
        "uk": "label для key '{key}' має бути непорожнім рядком",
        "en": "label for key '{key}' must be a non-empty string",
        "ru": "label для key '{key}' должен быть непустой строкой",
    },
    "template.type_invalid": {
        "uk": "type для key '{key}' має бути 'enum' або 'string', отримано: {ftype!r}",
        "en": "type for key '{key}' must be 'enum' or 'string', got: {ftype!r}",
        "ru": "type для key '{key}' должен быть 'enum' или 'string', получено: {ftype!r}",
    },
    "template.options_required": {
        "uk": "type=enum вимагає непорожнього options[] для key '{key}'",
        "en": "type=enum requires a non-empty options[] for key '{key}'",
        "ru": "type=enum требует непустого options[] для key '{key}'",
    },
    "template.options_must_be_strings": {
        "uk": "options для key '{key}' мають бути непорожніми рядками",
        "en": "options for key '{key}' must be non-empty strings",
        "ru": "options для key '{key}' должны быть непустыми строками",
    },
    "template.options_must_be_unique": {
        "uk": "options для key '{key}' мають бути унікальними",
        "en": "options for key '{key}' must be unique",
        "ru": "options для key '{key}' должны быть уникальными",
    },
    "template.base_immutable": {
        "uk": "Базовий шаблон не можна змінити",
        "en": "The base template can't be changed",
        "ru": "Базовый шаблон нельзя изменить",
    },
    "template.field_in_use": {
        "uk": "Не можна видалити поле '{key}': на шаблоні є товари",
        "en": "Can't remove field '{key}': the template has products",
        "ru": "Нельзя удалить поле '{key}': на шаблоне есть товары",
    },
    "template.field_type_locked": {
        "uk": "Не можна змінити тип поля '{key}': на шаблоні є товари",
        "en": "Can't change the type of field '{key}': the template has products",
        "ru": "Нельзя изменить тип поля '{key}': на шаблоне есть товары",
    },
    "template.delete_blocked": {
        "uk": "Не можна видалити шаблон: спершу перенесіть або видаліть товари",
        "en": "Can't delete the template: move or delete its products first",
        "ru": "Нельзя удалить шаблон: сначала перенесите или удалите товары",
    },
    # --- finance (app/api/finance.py) ------------------------------------- #
    "finance.invalid_date_format": {
        "uk": "date має бути у форматі YYYY-MM-DD",
        "en": "date must be in YYYY-MM-DD format",
        "ru": "date должно быть в формате YYYY-MM-DD",
    },
    # --- public catalog widget (app/api/public.py) ------------------------ #
    "public.catalog_not_found": {
        "uk": "Каталог не знайдено",
        "en": "Catalog not found",
        "ru": "Каталог не найден",
    },
    # --- auth / tenancy (app/deps.py) -------------------------------------- #
    "auth.no_shop_access": {
        "uk": "Немає доступу до цього магазину",
        "en": "No access to this shop",
        "ru": "Нет доступа к этому магазину",
    },
    "auth.too_many_new_shops": {
        "uk": "Занадто багато нових магазинів з цієї IP, спробуйте пізніше",
        "en": "Too many new shops from this IP, try again later",
        "ru": "Слишком много новых магазинов с этого IP, попробуйте позже",
    },
    "auth.subscription_readonly": {
        "uk": "підписка не активна — режим лише читання",
        "en": "subscription is not active — read-only mode",
        "ru": "подписка не активна — режим только чтения",
    },
    "auth.api_key_missing": {
        "uk": "X-API-Key відсутній",
        "en": "X-API-Key is missing",
        "ru": "X-API-Key отсутствует",
    },
    "auth.api_key_invalid": {
        "uk": "невалідний API-ключ",
        "en": "invalid API key",
        "ru": "недействительный API-ключ",
    },
    # --- rate limiting (app/security/rate_limit.py) ------------------------ #
    "rate_limit.too_many_requests": {
        "uk": "Занадто багато запитів, спробуйте пізніше",
        "en": "Too many requests, try again later",
        "ru": "Слишком много запросов, попробуйте позже",
    },
    # --- bot: /start + support-флоу (app/bot/handlers.py), мова юзера з     #
    # live message.from_user.language_code. Адмінська сторона (/promo_*,    #
    # відповіді admin_close/admin_mute/admin_ban/admin_unban САМОМУ адміну) #
    # — НЕ тут, лишається укр (app/i18n.py, шапка модуля).                   #
    "bot.welcome": {
        "uk": "Ласкаво просимо в SkladBase! Натисніть кнопку нижче, щоб відкрити застосунок.",
        "en": "Welcome to SkladBase! Tap the button below to open the app.",
        "ru": "Добро пожаловать в SkladBase! Нажмите кнопку ниже, чтобы открыть приложение.",
    },
    "bot.open_button": {
        "uk": "Відкрити SkladBase",
        "en": "Open SkladBase",
        "ru": "Открыть SkladBase",
    },
    "bot.support_muted": {
        "uk": "Підтримка буде доступна через {remaining} хв",
        "en": "Support will be available in {remaining} min",
        "ru": "Поддержка будет доступна через {remaining} мин",
    },
    "bot.support_intro": {
        "uk": "Ви на зв'язку з підтримкою. Опишіть проблему — я передам адміністратору.\nДля виходу — /cancel",
        "en": "You're connected to support. Describe your issue — I'll pass it to the admin.\nTo exit — /cancel",
        "ru": "Вы на связи с поддержкой. Опишите проблему — я передам администратору.\nДля выхода — /cancel",
    },
    "bot.support_exited": {
        "uk": "Ви вийшли з режиму підтримки.",
        "en": "You've left support mode.",
        "ru": "Вы вышли из режима поддержки.",
    },
    "bot.support_closed_by_admin": {
        "uk": "Адміністратор закінчив чат підтримки. Дякуємо за звернення!",
        "en": "The admin has closed the support chat. Thanks for reaching out!",
        "ru": "Администратор закончил чат поддержки. Спасибо за обращение!",
    },
    "bot.support_paused_notice": {
        "uk": "⏸ Підтримка тимчасово недоступна (1 година)",
        "en": "⏸ Support is temporarily unavailable (1 hour)",
        "ru": "⏸ Поддержка временно недоступна (1 час)",
    },
    "bot.support_unavailable": {
        "uk": "Підтримка тимчасово недоступна.",
        "en": "Support is temporarily unavailable.",
        "ru": "Поддержка временно недоступна.",
    },
    "bot.support_rate_limited": {
        "uk": "Зачекайте хвилину перед наступним повідомленням.",
        "en": "Please wait a minute before sending another message.",
        "ru": "Подождите минуту перед следующим сообщением.",
    },
    "bot.support_delivered": {
        "uk": "Передано ✅",
        "en": "Delivered ✅",
        "ru": "Передано ✅",
    },
    "bot.support_reply_prefix": {
        "uk": "💬 Відповідь підтримки:\n{text}",
        "en": "💬 Support reply:\n{text}",
        "ru": "💬 Ответ поддержки:\n{text}",
    },
    # --- bot: cron-пуші власнику (app/tasks.py, app/api/orders.py), мова з  #
    # Shop.owner_language_code (немає live Update у крон-задачі, значення   #
    # зняте при bootstrap_shop — app/i18n.py: lang_from_telegram_code).      #
    "bot.subscription_paused": {
        "uk": "⏳ Підписку призупинено. Дані збережено — оформи підписку, щоб редагувати.",
        "en": "⏳ Subscription paused. Your data is safe — subscribe to keep editing.",
        "ru": "⏳ Подписка приостановлена. Данные сохранены — оформи подписку, чтобы редактировать.",
    },
    "bot.renewal_reminder": {
        "uk": "🔔 Підписка закінчується через {days} дн. Продовжити можна в меню.",
        "en": "🔔 Subscription ends in {days} days. You can renew from the menu.",
        "ru": "🔔 Подписка заканчивается через {days} дн. Продлить можно в меню.",
    },
    "bot.card_charge_failed": {
        "uk": "⚠️ Не вдалось списати оплату з картки. Онови картку протягом 3 днів.",
        "en": "⚠️ Couldn't charge your card. Update your card within 3 days.",
        "ru": "⚠️ Не удалось списать оплату с карты. Обнови карту в течение 3 дней.",
    },
    "bot.parcel_picked_up": {
        "uk": "📦 Посилку {ttn} отримано — {name}, +{amount} ₴",
        "en": "📦 Parcel {ttn} picked up — {name}, +{amount} UAH",
        "ru": "📦 Посылку {ttn} получили — {name}, +{amount} ₴",
    },
    "bot.parcel_returned": {
        "uk": "↩️ Посилку {ttn} не забрали — {name} повернуто на склад",
        "en": "↩️ Parcel {ttn} wasn't picked up — {name} returned to stock",
        "ru": "↩️ Посылку {ttn} не забрали — {name} возвращён на склад",
    },
    "bot.low_stock": {
        "uk": "📦 «{name}» закінчується — залишилось {avail} {units}.",
        "en": "📦 “{name}” is running low — {avail} {units} left.",
        "ru": "📦 «{name}» заканчивается — осталось {avail} {units}.",
    },
    "bot.new_website_order": {
        "uk": "Нове замовлення з сайту #{order_id}",
        "en": "New order from your website #{order_id}",
        "ru": "Новый заказ с сайта #{order_id}",
    },
}
