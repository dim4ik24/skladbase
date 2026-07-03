from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///./skladbase.db"

    BOT_TOKEN: str = ""
    BOT_USERNAME: str = "sklad_base_bot"  # для deep-link інвайтів (t.me/<BOT_USERNAME>?startapp=...)
    ADMIN_TG_ID: int = 0  # tg_id адміністратора для техпідтримки (app/bot/handlers.py); 0 = не налаштовано
    MINI_APP_URL: str = ""  # HTTPS Cloudflare Workers URL TMA — кнопка "Відкрити" у /start; "" = кнопку не показувати
    INIT_DATA_MAX_AGE_HOURS: int = 24
    ENCRYPTION_KEY: str = ""  # base64, 32 байти — для AES-256-GCM (app/security/crypto.py)
    RUN_SCHEDULER: bool = True  # False у web-процесі прода — крон живе в app/worker.py (один процес)

    # IP проксі (nginx/Cloudflare), яким довіряємо заголовок X-Forwarded-For
    # (app/security/proxy_headers.py). Інакше клієнт сам підставляє довільний
    # X-Forwarded-For і обходить rate limiting за IP. CSV; дефолт — лише
    # loopback (nginx на тому самому хості).
    TRUSTED_PROXY_IPS: str = "127.0.0.1,::1"

    WFP_MERCHANT: str = ""
    WFP_SECRET: str = ""
    WFP_DOMAIN: str = ""

    NOWPAYMENTS_API_KEY: str = ""
    NOWPAYMENTS_IPN_SECRET: str = ""
    # Свідоме спрощення для MVP: фіксований курс із конфігу, не live-курс
    # НБУ/біржі. Достатньо для приблизної ціни крипто-чекауту; не використовувати
    # для точних фінансових розрахунків.
    UAH_USD_RATE: Decimal = Decimal("41.5")

    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY: str = ""
    R2_SECRET_KEY: str = ""
    R2_BUCKET: str = ""
    R2_PUBLIC_URL: str = ""  # публічний домен бакета (custom domain або r2.dev), без кінцевого "/"
    MAX_PHOTO_UPLOAD_MB: int = 5  # ліміт розміру вхідного фото (Стадія 2b)


settings = Settings()
