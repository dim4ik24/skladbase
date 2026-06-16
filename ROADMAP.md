# SkladBase — План розробки

> Multi-tenant SaaS обліку товарів для інста-магазинів у вигляді Telegram Mini App.
> Документ веде розробку по стадіях. Кожна стадія = одна сесія Claude Code з
> готовим deliverable і критеріями приймання. Не переходимо до наступної, поки
> поточна не проходить acceptance.

---

## 0. Що вже зроблено (фундамент)

Базовий доменний шар уже написаний і протестований:

| Файл | Що містить |
|------|-----------|
| `models.py` | Повна схема: tenancy+брендування, ролі, шаблони→товари→варіанти, резерв, рух складу, замовлення, підписки, промокоди |
| `subscriptions.py` | Стейт-машина підписки (`trial→active→canceled/past_due→expired`), `SubscriptionService` |
| `billing.py` | Адаптери Stars / WayForPay / NOWPayments + перевірка підписів вебхуків |
| `tasks.py` | Крони: протермінування, нагадування, авто-списання, зняття резервів, low-stock |
| `seed.py` | Системні шаблони, тарифи, демо-каталог |

Розробка стартує зі **Стадії 0** (каркас навколо цього шару), а не з порожнього репо.

---

## 1. Стек (зафіксовано, не обговорюється під час розробки)

- **Backend:** Python 3.11, FastAPI, async SQLAlchemy 2.0, Alembic, pydantic-settings
- **БД:** SQLite (dev) → PostgreSQL (prod). JSON-поля → JSONB на проді
- **Бот:** aiogram 3
- **Черги/крони:** APScheduler (старт), пізніше — окремий воркер
- **Фото:** Cloudflare R2 (presigned upload), стиснення на вході
- **Frontend (TMA):** Vanilla JS / lightweight, Telegram WebApp SDK, хостинг — Cloudflare Workers/Pages
- **Платежі:** Telegram Stars (нативна підписка) · WayForPay (картка-токен) · NOWPayments (крипта, разово)
- **Інфра:** Oracle Cloud (Ubuntu 22.04 ARM, systemd), Docker для dev
- **CI/CD:** GitHub Actions (ruff + mypy + pytest → build → deploy)

---

## 2. Структура репозиторію

```
skladbase/
├── app/
│   ├── main.py              # FastAPI app, lifespan, роутери
│   ├── config.py            # Settings (pydantic-settings, .env)
│   ├── db.py                # engine, async_sessionmaker, get_session
│   ├── models.py            # ← вже є
│   ├── deps.py              # resolve_membership, require_owner, tenant guard
│   ├── security/
│   │   ├── initdata.py      # HMAC-SHA256 валідація Telegram initData
│   │   └── crypto.py        # AES-256-GCM для API-ключів інтеграцій
│   ├── services/
│   │   ├── inventory.py     # склад: атомарні операції, резерв, рух (Стадія 3)
│   │   ├── catalog.py       # товари/варіанти/шаблони
│   │   ├── orders.py        # замовлення + website-flow
│   │   └── subscriptions.py # ← вже є
│   ├── billing/
│   │   └── providers.py     # ← billing.py
│   ├── api/
│   │   ├── catalog.py  orders.py  billing.py  webhooks.py  public.py
│   ├── bot/                 # aiogram: хендлери, нотифаєр
│   ├── tasks.py             # ← вже є (підключити до APScheduler)
│   └── seed.py              # ← вже є
├── migrations/              # Alembic
├── tests/
├── frontend/                # TMA
├── .github/workflows/ci.yml
├── docker-compose.yml  Dockerfile  .env.example
├── CLAUDE.md  ROADMAP.md
```

---

## 3. Як ведемо роботу з Claude Code

1. **Одна стадія = одна сесія.** На старті сесії: «Робимо Стадію N з ROADMAP. Ось acceptance criteria — спочатку напиши тести під них, потім реалізацію.»
2. **Acceptance-first.** Критерії приймання нижче — це фактично тест-кейси. Спочатку тести (хай падають), потім код, поки не зелено.
3. **Перевірка перед коммітом:** `ruff check . && mypy app && pytest`. Один коміт = одна стадія.
4. **Жодних заглушок.** Якщо чогось бракує (ключ, рішення) — Claude Code зупиняється і питає, а не лишає `# TODO`.
5. **CLAUDE.md — джерело правди** по архітектурних інваріантах. Якщо стадія їх порушує — стоп.

---

## 4. Стадії

### Стадія 0 — Каркас і інфра
**Мета:** репо запускається, схема накатується міграцією, CI зелений.
- FastAPI skeleton, `config.py`, `db.py` (async engine), lifespan
- Alembic: автоген першої міграції з `models.py`
- `docker-compose.yml` (app + postgres), `Dockerfile`, `.env.example`
- pre-commit: ruff + mypy; pytest skeleton; базовий CI workflow
- `GET /health`

**Acceptance:**
- `docker compose up` піднімає сервіс; `GET /health` → 200
- `alembic upgrade head` створює всі таблиці зі схеми
- `ruff`, `mypy`, `pytest` проходять у CI

---

### Стадія 1 — Авторизація і tenancy (initData)
**Мета:** zero-friction вхід через Telegram, жорстка ізоляція tenant.
- `security/initdata.py`: HMAC-SHA256 валідація `initData` (+ перевірка `auth_date` на свіжість)
- `deps.py`: `resolve_membership()` дістає `shop_id` з валідованого initData, **ніколи з тіла запиту**
- Bootstrap: перший вхід → створення `Shop` + `Membership(owner)` + `seed_demo_catalog` + `start_trial`
- `require_owner` / `require_member` guard-залежності (ролі)

**Acceptance:**
- Підроблений/протермінований initData → 401
- Валідний → резолвиться правильний `shop_id`
- `manager` отримує 403 на фінансових ендпоінтах, `owner` — ні
- Новий магазин одразу має демо-товари і тріал на 7 днів

---

### Стадія 2 — Каталог: шаблони, товари, варіанти
**Мета:** додавання товару з полями під тип (одяг/взуття/косметика/іграшки).
- CRUD товарів і варіантів; рендер-контракт `field_schema` (attributes vs variant_axes)
- Генерація варіантів з осей (розмір×колір) при створенні
- Завантаження фото в R2 (presigned) + стиснення/ліміт розміру
- Енфорс лімітів плану (`max_products`, `photos`) — read-only-friendly помилки

**Acceptance:**
- Створення футболки з 3 варіантами з шаблону «Одяг»
- SKU унікальний у межах магазину (`uq_variant_shop_sku`)
- Перевищення `max_products` на free-плані → зрозуміла 402/403, не 500
- Фото >ліміту відхиляється на вході

---

### Стадія 3 — `inventory.py`: склад, резерв, рух, low-stock
**Мета:** єдиний сервіс зміни складу. **Тут живе захист від оверселу.**
- Атомарні операції з `SELECT ... FOR UPDATE` по варіанту
- `reserve()` / `release()` / `fulfill()` (резерв→продаж), `restock()`, `adjust()`
- Кожна операція пише `StockMovement`
- `restock` вище порога → скидає `low_stock_notified_at`
- Інваріант: `reserved ≤ on_hand`, `available = on_hand − reserved ≥ 0`

**Acceptance:**
- Конкурентний тест: 2 паралельні списання останньої одиниці → лише одне успішне, оверселу нема
- `reserve` зменшує `available`, але не `on_hand`
- `restock` вище порога обнуляє прапорець нотифікації
- Спроба зарезервувати більше за `available` → відмова

---

### Стадія 4 — Замовлення і Website API
**Мета:** замовлення з апки і з сайту, синхронізація залишків (підводний камінь #5).
- `POST /orders` з `idempotency_key`; всередині — транзакція + `inventory.reserve`
- Флоу: замовлення → резерв (не списання) → пуш власнику → підтвердження → `fulfill`
- Per-shop **API-ключ** (зберігається зашифрованим, AES-256-GCM)
- Публічний каталог `GET /c/{slug}` + легкий JS-віджет для вставки в сайти
- Вебхук назад на сайт при зміні залишку (out-of-stock)

**Acceptance:**
- Подвійний `POST` з тим самим idempotency-key → одне замовлення
- Оверсел під конкуренцією неможливий (резерв атомарний)
- Запит з чужим/відсутнім API-ключем → 401
- Зміна залишку тригерить вебхук на сайт

---

### Стадія 5 — Білінг: підписки
**Мета:** автоматична оплата кількома способами, тріал, промокоди.
- Підключити `SubscriptionService` + `billing.providers`
- **Stars:** `pre_checkout_query` → `successful_payment`, обробка `is_recurring` (продовження)
- **WayForPay:** перша оплата з токеном, `verify_callback`, збереження `recToken`
- **NOWPayments:** IPN (`verify_ipn`) для річної/крипти
- Промокод-ендпоінт (`redeem_promo`), gating фіч по плану
- Read-only стан після `expired` (запис заблоковано, читання — ні)

**Acceptance:**
- Оплата Stars у sandbox активує підписку; recurring-вебхук продовжує період
- Підроблений підпис WayForPay/NOWPayments → відхилено
- Промокод дає +60 днів і не активується вдруге тим самим магазином
- Після `expired` запис заблоковано, дані видно

---

### Стадія 6 — Крони і сповіщення
**Мета:** усе автоматичне з `tasks.py` працює за розкладом.
- APScheduler: `expire_subscriptions`, `send_renewal_reminders`, `charge_due_card_subscriptions`, `release_expired_reservations`, `low_stock_scan`
- Notifier поверх aiogram (`bot.send_message`)
- Дебаунс low-stock; нагадування за 3 дні (тільки для не-авто провайдерів)

**Acceptance:**
- Тест із зсувом часу тригерить кожен крон правильно
- Low-stock пушиться раз на перетин порога, не на кожен продаж
- Мертвий резерв (expired) повертає `reserved` в `available`

---

### Стадія 7 — Mini App (frontend)
**Мета:** «це моя власна апка» — простий, не перевантажений UX.
- Головний екран: сітка товарів (фото, назва, залишок, ціна), пошук, +/−
- Брендування: лого + accent_color у шапці (з `Shop`)
- Додавання товару з полями шаблону (progressive disclosure: «Додатково»)
- Резерв-UI, бейджі low-stock / out-of-stock
- Paywall-екран; банер демо-режиму + «Очистити приклади»
- Telegram theme params, передача `initData` у кожен запит

**Acceptance:**
- Працює всередині Telegram; read-only стан показано після тріалу
- Брендування магазину рендериться
- Менеджер не бачить фінансових екранів
- Демо-банер зникає після очищення прикладів

---

### Стадія 8 — Безпека і hardening
**Мета:** портфоліо-рівень, нуль витоків між магазинами.
- AES-256-GCM для секретів (API-ключі інтеграцій)
- Енфорс перевірки підписів на ВСІХ вебхуках
- Rate limiting; валідація вводу; структуровані логи; трекінг помилок
- **Аудит ізоляції:** тест-набір «магазин A не може прочитати дані магазину B»

**Acceptance:**
- Isolation-suite зелений (жоден ендпоінт не віддає чужий `shop_id`)
- Усі вебхуки відхиляють невалідний підпис
- Секрети зашифровані at rest (у БД нема plaintext-ключів)

---

### Стадія 9 — CI/CD, деплой, портфоліо
**Мета:** живе демо + кейс для портфоліо.
- GitHub Actions: lint → type → test → build → deploy
- Деплой backend на Oracle (systemd), TMA на Cloudflare Workers
- Seed демо-даних на проді; публічний demo-магазин для пітчу
- README + case study (як для NetGuardian)

**Acceptance:**
- Push у main → CI → автодеплой
- Жива demo-URL відкривається в Telegram
- Кейс-сторінка з реальними скрінами

---

## 5. Definition of Done (для кожної стадії)

- [ ] Acceptance-критерії покриті тестами, тести зелені
- [ ] `ruff` + `mypy` без помилок
- [ ] Жодних `# TODO` / заглушок у мерджнутому коді
- [ ] Архітектурні інваріанти з `CLAUDE.md` не порушені
- [ ] Один коміт із осмисленим повідомленням

---

## 6. Реєстр ризиків (тримати під час усіх стадій)

| Ризик | Де вилазить | Мітигація |
|-------|-------------|-----------|
| **Оверсел** | Стадія 3–4 | `FOR UPDATE`, резерв замість прямого списання, idempotency |
| **Витік між tenant** | Усі стадії | `shop_id` лише з initData; isolation-suite (Стадія 8) |
| **Stars: фіксований період 30д** | Стадія 5 | Інших періодів нема; річну робимо через картку/крипту |
| **Активація з підробленого «оплатив»** | Стадія 5 | Підписку вмикаємо ТІЛЬКИ з вебхука провайдера |
| **Вартість зберігання фото** | Стадія 2 | Ліміти per-plan + стиснення на вході |
| **Churn мікробізнесу** | Продукт | Прив'язка сайтом + read-only (дані не зникають) |
| **Юридичне «дані в нас»** | При масштабуванні | Політика конфіденційності з прямою згадкою зберігання |

---

## 7. Перша сесія

Старт зі **Стадії 0**. Промпт у Claude Code:

> «Робимо Стадію 0 з ROADMAP.md. У репо вже є `models.py`, `subscriptions.py`,
> `billing.py`, `tasks.py`, `seed.py` — НЕ переписуй їх. Збери каркас FastAPI
> навколо них за структурою з розділу 2, налаштуй Alembic (автоген міграції зі
> схеми), docker-compose, ruff/mypy/pytest і CI. Дотримуйся CLAUDE.md.
> Спочатку — acceptance-тести зі Стадії 0, потім реалізація до зеленого.»
