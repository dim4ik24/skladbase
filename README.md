# SkladBase

Multi-tenant SaaS обліку товарів для інста-магазинів, поданий як **Telegram
Mini App**. Власник веде товари й залишки у простому UI всередині Telegram;
під капотом — окрема БД на кожен магазин і захист від оверселу на рівні
сервісного шару.

Нульовий поріг входу: вхід через Telegram (без реєстрації/пароля), UX у рази
простіший за KeyCRM/SalesDrive/HugeProfit, продаж пакетом разом із сайтом
(публічний каталог + JS-віджет).

## Стек

| Шар | Технологія |
|---|---|
| Backend | Python 3.11+, FastAPI, async SQLAlchemy 2.0, Alembic |
| БД | SQLite (dev) → PostgreSQL + asyncpg (прод) |
| Бот | aiogram 3 |
| Крони | APScheduler, окремий процес (`app/worker.py`) |
| Фото | Cloudflare R2 (presigned upload), стиснення на вході |
| Frontend (TMA) | React + TypeScript, Vite, Telegram WebApp SDK |
| Платежі | Telegram Stars · WayForPay (картка-токен) · NOWPayments (крипта) |
| Інфра | Oracle Cloud (Ubuntu ARM, systemd) + nginx, Docker для dev |
| CI | GitHub Actions: ruff + mypy + pytest (backend), tsc + vitest + build (frontend) |

## Запуск локально

Бекенд:

```bash
cp .env.example .env        # заповнити BOT_TOKEN мінімум
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
pytest -q
ruff check . && mypy app
```

За замовчуванням `.env` піднімає SQLite (`sqlite+aiosqlite:///./skladbase.db`)
— без Postgres/Docker. Для прод-конфігурації з Postgres дивись
`deploy/.env.production.example`.

Планувальник крон-джоб (`release_expired_reservations`, `low_stock_scan`,
`charge_due_card_subscriptions`, `expire_subscriptions`,
`send_renewal_reminders`) — окремий процес, НЕ частина веб-воркера:

```bash
python -m app.worker
```

Frontend (TMA):

```bash
cd frontend/app
npm install
cp .env.example .env.local   # VITE_DEV_INIT_DATA з python ../../scripts/dev_initdata.py
npm run dev
npm run test
npm run build
```

`vite build` кладе результат у `frontend/app/dist` — FastAPI роздає його
напряму як статику на `/` (single-origin, без CORS у проді).

Docker (Postgres за замовчуванням):

```bash
docker compose up
```

## Архітектурні інваріанти

(повна версія — `CLAUDE.md`)

1. **Tenant-ізоляція.** `shop_id` береться ТІЛЬКИ з валідованого Telegram
   `initData`, ніколи з тіла/параметрів запиту. Кожен запит до даних
   магазину фільтрується по `shop_id`.
2. **Підписку активуємо ТІЛЬКИ з вебхука провайдера** — ніколи з відповіді
   Mini App (клієнт може підробити «я оплатив», підписаний вебхук — ні).
3. **Склад змінюється тільки через `app/services/inventory.py`** —
   атомарні операції (`SELECT ... FOR UPDATE`), кожна пише `StockMovement`.
4. **Замовлення → резерв, не пряме списання.** Списання (`fulfill`) лише
   після підтвердження/оплати; `available = on_hand − reserved` завжди ≥ 0.
5. **Idempotency** на всіх ендпоінтах, що створюють замовлення/платежі.
6. **Залишок/резерв/low-stock — на рівні `Variant`**, не `Product`.

## Прод-розгортання

Шаблони (без самого запуску деплою) — у `deploy/`:

- `skladbase-web.service`, `skladbase-scheduler.service` — systemd-юніти;
  веб і планувальник — окремі процеси (`RUN_SCHEDULER=False` у веб-юніті,
  крони піднімає лише `skladbase-scheduler.service` через `app/worker.py`).
- `nginx.conf` — reverse proxy на uvicorn + HTTPS + статика TMA напряму з
  nginx; передає `X-Forwarded-For`, який застосунок довіряє лише від
  налаштованих проксі (`app/security/proxy_headers.py`, `TRUSTED_PROXY_IPS`).
- `.env.production.example` — усі прод-змінні без значень.

## Портфоліо: кейс

**Проблема.** Власники інста-магазинів ведуть облік у нотатках/екселі —
губиться синхронізація залишків між Telegram-продажами і сайтом, легко
продати те, чого вже немає (оверсел), і немає простого способу зайти в
систему без реєстрації для дуже нетехнічної аудиторії.

**Рішення.** Telegram Mini App як єдина точка входу (нуль реєстрації, дані —
сам Telegram-акаунт), з мультитенантним бекендом, де ізоляція даних між
магазинами і захист від оверселу — архітектурні інваріанти, а не best-effort.

**Що реалізовано:**

- **Мультитенант з нуля.** Кожен запит резолвить `shop_id` виключно з
  HMAC-підписаного Telegram `initData` (`app/security/initdata.py`,
  `app/deps.py`) — тіло/параметри запиту для цього не довіряються. Покрито
  isolation-suite (`tests/test_isolation.py`): жоден ендпоінт не віддає чужий
  `shop_id`.
- **Захист від оверселу.** Увесь склад іде через один сервіс
  (`app/services/inventory.py`) з атомарними `SELECT ... FOR UPDATE`-
  операціями; резерв і списання розділені, конкурентні списання останньої
  одиниці тестуються явно.
- **Ідемпотентний білінг, 3 провайдери.** Telegram Stars (нативна підписка з
  авто-продовженням через `is_recurring`), WayForPay (картка з токеном,
  авто-списання власним кроном), NOWPayments (крипта, разово). Стейт-машина
  підписки (`trial → active → past_due/canceled → expired`) проходить лише
  через guard-методи; усі вебхуки перевіряють підпис провайдера, інакше
  активація підписки можлива через підробку клієнтом «я оплатив».
- **Резерви замовлень.** `POST /orders` з `idempotency_key` — повторний
  запит з тим самим ключем не створює друге замовлення; замовлення спершу
  резервує склад, списання — лише після підтвердження.
- **Крони в окремому процесі.** APScheduler-джоби (протермінування
  підписок, нагадування, авто-списання картки, зняття протермінованих
  резервів, сканування low-stock) живуть в `app/worker.py`, не в кожній
  репліці веб-процесу.
- **TMA.** React/TypeScript Mini App: каталог із пошуком і резервом,
  брендування магазину з Telegram theme params, read-only стан після
  закінчення тріалу (дані видно, запис заблоковано), демо-банер з
  очищенням прикладів, розмежування ролей `owner`/`manager`.

test autodeploy 2026-06-28
autodeploy test 2 2026-06-28
