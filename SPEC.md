# SPEC.md

Специфікація ендпоінтів, доданих поза нумерованими стадіями ROADMAP.md
(точкові фічі над уже збудованим фундаментом).

## `GET /api/analytics/summary`

Owner-only зведення продажів і виручки магазину. Тільки читання — жодних
змін залишку/інвентаря, жодного виклику `inventory.py`. Деталі джерела
даних і обмеження наближення виручки — у DECISIONS.md.

### Авторизація

`X-Telegram-Init-Data` → `require_owner` (CLAUDE.md, інваріант №1: `shop_id`
виключно з валідованого initData, ніколи з параметрів запиту).

- `owner` → 200
- `manager` → 403
- немає підписки/read-only режим — **не блокує**: це GET, не мутація;
  доступний завжди, як і `GET /api/reservations`.

### Запит

```
GET /api/analytics/summary?period={today|7d|30d|all}
```

`period` — необов'язковий, за замовчуванням `7d`. Невалідне значення → 422
(FastAPI/Pydantic `Literal` валідація).

### Відповідь `200`

```json
{
  "period": "7d",
  "units_sold": 42,
  "revenue": "4200.00",
  "sales_count": 17,
  "top_products": [
    { "product_id": 1, "name": "Футболка", "units_sold": 12, "revenue": "1200.00" }
  ]
}
```

- `units_sold` — сума `qty` усіх продажних рухів складу у вікні.
- `revenue` — `Decimal`, серіалізується як рядок (як і `Variant.price`,
  `Plan.price_uah` в інших ендпоінтах цього проєкту).
- `sales_count` — кількість продажних рухів складу у вікні (не замовлень,
  див. DECISIONS.md).
- `top_products` — топ-5 товарів за `units_sold`, за спаданням. Порожній
  масив, якщо продажів немає.

Усі агрегації — лише в межах `shop_id` поточного власника.

### Фронт

`frontend/app/src/api.ts`: `getAnalyticsSummary(period?: AnalyticsPeriod)`.
Лише типізований виклик — UI не підключений (дизайн на паузі); готовий для
підключення в метрику «Продано»/owner-панель пізніше.
