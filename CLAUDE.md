# CLAUDE.md — SkladBase

Контекст для Claude Code. Тримай ці правила в кожній сесії. Деталі плану — у `ROADMAP.md`.

## Що це
Multi-tenant SaaS обліку товарів для інста-магазинів, поданий як **Telegram Mini App**.
Власник веде товари/залишки у зручному UI; під капотом — наша БД. Ключова цінність:
нульовий поріг входу (вхід через Telegram, без реєстрації), UX у рази простіший за
KeyCRM/SalesDrive/HugeProfit, продаж пакетом із сайтом.

## Стек
Python 3.11 · FastAPI · async SQLAlchemy 2.0 · Alembic · aiogram 3 · APScheduler ·
SQLite(dev)→Postgres(prod) · Cloudflare R2 (фото) · TMA на Cloudflare Workers ·
Oracle Cloud (Ubuntu ARM, systemd). Розробка з Windows/PowerShell.

## Архітектурні інваріанти (НЕ ПОРУШУВАТИ)
1. **Tenant-ізоляція.** `shop_id` береться ТІЛЬКИ з валідованого Telegram `initData`,
   ніколи з тіла/параметрів запиту. Кожен запит до даних магазину містить
   `WHERE shop_id = :current_shop`. Без винятків.
2. **Підписку активуємо ТІЛЬКИ з вебхука провайдера.** Ніколи з відповіді Mini App —
   клієнт може підробити «я оплатив», вебхук з валідним підписом — ні.
3. **Склад змінюється тільки через `services/inventory.py`.** Прямих
   `variant.on_hand -= ...` у хендлерах/сервісах нема. Операції атомарні
   (`SELECT ... FOR UPDATE`), кожна пише `StockMovement`.
4. **Замовлення → резерв, не пряме списання.** Списання (`fulfill`) — лише після
   підтвердження/оплати. `available = on_hand − reserved` завжди ≥ 0.
5. **Idempotency** на всіх ендпоінтах, що створюють замовлення/платежі.
6. **Залишок/резерв/low-stock — на рівні `Variant`,** не `Product`.

## Ролі
`owner` бачить усе (включно з фінансами), `manager` — резерв і замовлення, без фінансів.
Енфорс через `require_owner` / `require_member` залежності.

## Білінг
- **Stars** — нативна підписка (`subscription_period=2592000`, авто-продовження
  прилітає вебхуком `is_recurring=True`). Дефолтний спосіб.
- **WayForPay** — картка з токеном; авто-списання робить НАШ крон (`charge_due_card_subscriptions`).
- **NOWPayments** — крипта/річна, РАЗОВО, `auto_renew=False`, перед кінцем — нагадування.
- Тріал 7 днів стартує при ПЕРШІЙ дії (додав товар), не при відкритті. Після
  закінчення — read-only (дані видно, запис заблоковано), НЕ видалення.
- Стейт-машина в `subscriptions.py`; переходи проходять через guard — не міняй статус напряму.

## Конвенції коду
- SQLAlchemy 2.0 стиль (`Mapped`, `mapped_column`), async скрізь.
- Статуси — enum, не рядки. Гроші — `Decimal`/`Numeric`, не float.
- Перед коммітом: `ruff check . && mypy app && pytest` — усе зелене.
- **Жодних заглушок.** Бракує ключа/рішення — зупинись і запитай, не лишай `# TODO`.
- Acceptance-критерії стадії спочатку як тести, потім реалізація.
- Один коміт = одна стадія ROADMAP.
- Наприкінці кожної стадії: git add -A && git commit -m "Stage N: ..." && git push.

## Існуючі файли (не переписувати без причини)
`models.py` (схема) · `subscriptions.py` (стейт-машина) · `billing.py` (провайдери) ·
`tasks.py` (крони) · `seed.py` (шаблони/тарифи/демо). Нове будуємо навколо них.

## Команди
```
alembic revision --autogenerate -m "msg"   # міграція зі схеми
alembic upgrade head
uvicorn app.main:app --reload
pytest -q
ruff check . && mypy app
```
PowerShell-нюанс: нема `head`/`grep` — використовуй `Get-Content` / `Select-String`.
Після `scp` на Oracle завжди звіряй файл (`grep -c` на сервері), бувають тихі підміни.
