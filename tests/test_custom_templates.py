"""
F1 — Кастомні шаблони: acceptance tests.

Сценарії:
  1. Створення кастомного шаблону (owner) → 201 + id.
  2. GET повертає базові + свої, НЕ чужі.
  3. PATCH: додати вісь при наявних товарах → 200.
  4. PATCH: видалити вісь при наявних товарах → 409.
  5. PATCH: змінити type при наявних товарах → 409.
  6. DELETE при наявних товарах → 409.
  7. DELETE без товарів → 204.
  8. PATCH базового (shop_id NULL) → 403.
  9. DELETE базового → 403.
  10. Валідація: поганий type → 422.
  11. Валідація: enum без options → 422.
  12. Валідація: дублікат key → 422.
  13. Manager POST → 403.
"""
from __future__ import annotations

from httpx import AsyncClient

from app import db as db_module
from app.models import MemberRole, Membership
from tests.conftest import make_init_data

# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

_BASIC_SCHEMA: dict = {
    "attributes": [{"key": "material", "label": "Матеріал", "type": "string"}],
    "variant_axes": [
        {"key": "size", "label": "Розмір", "type": "enum", "options": ["S", "M", "L"]},
        {"key": "color", "label": "Колір", "type": "string"},
    ],
}

_VARIANT_PAYLOAD = {"price": "100.00", "axis_values": {}, "sku": None, "on_hand": 0}
# Варіант з осями для _BASIC_SCHEMA (size enum + color string)
_VARIANT_WITH_AXES = {"price": "100.00", "axis_values": {"size": "M", "color": "чорний"}, "sku": None, "on_hand": 0}


def _hdr(tg_id: int) -> dict:
    return {"X-Telegram-Init-Data": make_init_data(tg_id)}


async def _bootstrap(client: AsyncClient, tg_id: int) -> dict:
    r = await client.get("/api/me", headers=_hdr(tg_id))
    assert r.status_code == 200
    return r.json()


async def _create_template(client: AsyncClient, tg_id: int, schema: dict | None = None) -> dict:
    r = await client.post(
        "/api/templates",
        json={"name": "Мій шаблон", "field_schema": schema or _BASIC_SCHEMA},
        headers=_hdr(tg_id),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_product_on_template(client: AsyncClient, tg_id: int, template_id: int) -> dict:
    # _BASIC_SCHEMA має variant_axes [size, color] — передаємо відповідні значення
    r = await client.post(
        "/api/products",
        json={"name": "Тест", "variants": [_VARIANT_WITH_AXES], "template_id": template_id},
        headers=_hdr(tg_id),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _make_manager(shop_id: int, tg_id: int) -> None:
    async with db_module.async_session() as s:
        s.add(Membership(shop_id=shop_id, tg_id=tg_id, role=MemberRole.manager))
        await s.commit()


# --------------------------------------------------------------------------- #
#  Тест 1: створення кастомного шаблону
# --------------------------------------------------------------------------- #
async def test_create_custom_template(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=1001)
    tmpl = await _create_template(client, tg_id=1001)

    assert tmpl["id"] > 0
    assert tmpl["name"] == "Мій шаблон"
    assert tmpl["code"] == "custom"
    assert tmpl["shop_id"] == me["shop_id"]
    assert tmpl["field_schema"] == _BASIC_SCHEMA


# --------------------------------------------------------------------------- #
#  Тест 2: GET повертає базові + свої, НЕ чужі
# --------------------------------------------------------------------------- #
async def test_get_templates_returns_own_not_others(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=2001)
    await _bootstrap(client, tg_id=2002)

    own = await _create_template(client, tg_id=2001)

    # 2001 бачить і глобальні, і свій
    r = await client.get("/api/templates", headers=_hdr(2001))
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert own["id"] in ids

    # 2002 НЕ бачить шаблон 2001
    r2 = await client.get("/api/templates", headers=_hdr(2002))
    assert r2.status_code == 200
    ids2 = [t["id"] for t in r2.json()]
    assert own["id"] not in ids2


# --------------------------------------------------------------------------- #
#  Тест 3: PATCH — додати вісь при наявних товарах → 200
# --------------------------------------------------------------------------- #
async def test_patch_add_axis_with_products_ok(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=3001)
    tmpl = await _create_template(client, tg_id=3001)
    await _create_product_on_template(client, tg_id=3001, template_id=tmpl["id"])

    new_schema = {
        "attributes": _BASIC_SCHEMA["attributes"],
        "variant_axes": [
            *_BASIC_SCHEMA["variant_axes"],
            {"key": "finish", "label": "Фінішинг", "type": "string"},
        ],
    }
    r = await client.patch(
        f"/api/templates/{tmpl['id']}",
        json={"field_schema": new_schema},
        headers=_hdr(3001),
    )
    assert r.status_code == 200, r.text
    axes_keys = [a["key"] for a in r.json()["field_schema"]["variant_axes"]]
    assert "finish" in axes_keys


# --------------------------------------------------------------------------- #
#  Тест 4: PATCH — видалити вісь при наявних товарах → 409
# --------------------------------------------------------------------------- #
async def test_patch_remove_axis_with_products_409(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=4001)
    tmpl = await _create_template(client, tg_id=4001)
    await _create_product_on_template(client, tg_id=4001, template_id=tmpl["id"])

    schema_minus_color = {
        "attributes": _BASIC_SCHEMA["attributes"],
        "variant_axes": [_BASIC_SCHEMA["variant_axes"][0]],  # лишаємо тільки size, прибираємо color
    }
    r = await client.patch(
        f"/api/templates/{tmpl['id']}",
        json={"field_schema": schema_minus_color},
        headers=_hdr(4001),
    )
    assert r.status_code == 409, r.text
    assert "color" in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  Тест 5: PATCH — змінити type при наявних товарах → 409
# --------------------------------------------------------------------------- #
async def test_patch_change_type_with_products_409(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=5001)
    tmpl = await _create_template(client, tg_id=5001)
    await _create_product_on_template(client, tg_id=5001, template_id=tmpl["id"])

    # color був string → робимо enum
    schema_changed_type = {
        "attributes": _BASIC_SCHEMA["attributes"],
        "variant_axes": [
            _BASIC_SCHEMA["variant_axes"][0],  # size — без змін
            {"key": "color", "label": "Колір", "type": "enum", "options": ["Чорний", "Білий"]},
        ],
    }
    r = await client.patch(
        f"/api/templates/{tmpl['id']}",
        json={"field_schema": schema_changed_type},
        headers=_hdr(5001),
    )
    assert r.status_code == 409, r.text
    assert "color" in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  Тест 6: DELETE при наявних товарах → 409
# --------------------------------------------------------------------------- #
async def test_delete_with_products_409(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=6001)
    tmpl = await _create_template(client, tg_id=6001)
    await _create_product_on_template(client, tg_id=6001, template_id=tmpl["id"])

    r = await client.delete(f"/api/templates/{tmpl['id']}", headers=_hdr(6001))
    assert r.status_code == 409, r.text
    assert "товари" in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  Тест 7: DELETE без товарів → 204
# --------------------------------------------------------------------------- #
async def test_delete_empty_template_ok(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=7001)
    tmpl = await _create_template(client, tg_id=7001)

    r = await client.delete(f"/api/templates/{tmpl['id']}", headers=_hdr(7001))
    assert r.status_code == 204, r.text

    # шаблон більше не видно у GET
    r2 = await client.get("/api/templates", headers=_hdr(7001))
    ids = [t["id"] for t in r2.json()]
    assert tmpl["id"] not in ids


# --------------------------------------------------------------------------- #
#  Тест 8: PATCH базового (shop_id NULL) → 403
# --------------------------------------------------------------------------- #
async def test_patch_global_template_403(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=8001)

    # знайти перший глобальний шаблон
    r = await client.get("/api/templates", headers=_hdr(8001))
    globals_ = [t for t in r.json() if t["shop_id"] is None]
    assert globals_, "Немає глобальних шаблонів (потрібен seed)"
    global_id = globals_[0]["id"]

    r2 = await client.patch(
        f"/api/templates/{global_id}",
        json={"name": "Спроба"},
        headers=_hdr(8001),
    )
    assert r2.status_code == 403, r2.text


# --------------------------------------------------------------------------- #
#  Тест 9: DELETE базового → 403
# --------------------------------------------------------------------------- #
async def test_delete_global_template_403(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=9001)

    r = await client.get("/api/templates", headers=_hdr(9001))
    globals_ = [t for t in r.json() if t["shop_id"] is None]
    assert globals_, "Немає глобальних шаблонів (потрібен seed)"
    global_id = globals_[0]["id"]

    r2 = await client.delete(f"/api/templates/{global_id}", headers=_hdr(9001))
    assert r2.status_code == 403, r2.text


# --------------------------------------------------------------------------- #
#  Тести 10–12: валідація field_schema
# --------------------------------------------------------------------------- #
async def test_validate_bad_type_422(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=10001)
    bad_schema = {
        "attributes": [],
        "variant_axes": [{"key": "size", "label": "Розмір", "type": "number"}],
    }
    r = await client.post(
        "/api/templates",
        json={"name": "Поганий", "field_schema": bad_schema},
        headers=_hdr(10001),
    )
    assert r.status_code == 422, r.text
    assert "number" in r.json()["detail"] or "enum" in r.json()["detail"]


async def test_validate_enum_no_options_422(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=11001)
    bad_schema = {
        "attributes": [],
        "variant_axes": [{"key": "size", "label": "Розмір", "type": "enum", "options": []}],
    }
    r = await client.post(
        "/api/templates",
        json={"name": "Поганий", "field_schema": bad_schema},
        headers=_hdr(11001),
    )
    assert r.status_code == 422, r.text
    assert "options" in r.json()["detail"] or "enum" in r.json()["detail"]


async def test_validate_duplicate_key_422(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=12001)
    bad_schema = {
        "attributes": [{"key": "color", "label": "Колір атр", "type": "string"}],
        "variant_axes": [{"key": "color", "label": "Колір вісь", "type": "string"}],
    }
    r = await client.post(
        "/api/templates",
        json={"name": "Поганий", "field_schema": bad_schema},
        headers=_hdr(12001),
    )
    assert r.status_code == 422, r.text
    assert "color" in r.json()["detail"]


# --------------------------------------------------------------------------- #
#  Тест 13: manager не може створити → 403
# --------------------------------------------------------------------------- #
async def test_manager_cannot_create_template_403(client: AsyncClient) -> None:
    me = await _bootstrap(client, tg_id=13001)
    await _make_manager(shop_id=me["shop_id"], tg_id=13002)

    r = await client.post(
        "/api/templates",
        json={"name": "Менеджерський", "field_schema": _BASIC_SCHEMA},
        headers=_hdr(13002),
    )
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
#  Тест 14: tenant-ізоляція PATCH/DELETE чужого шаблону → 404
# --------------------------------------------------------------------------- #
async def test_patch_other_shop_template_404(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=14001)
    await _bootstrap(client, tg_id=14002)

    tmpl = await _create_template(client, tg_id=14001)

    # 14002 намагається редагувати шаблон 14001
    r = await client.patch(
        f"/api/templates/{tmpl['id']}",
        json={"name": "Чужий"},
        headers=_hdr(14002),
    )
    assert r.status_code == 404, r.text


async def test_delete_other_shop_template_404(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=15001)
    await _bootstrap(client, tg_id=15002)

    tmpl = await _create_template(client, tg_id=15001)

    r = await client.delete(f"/api/templates/{tmpl['id']}", headers=_hdr(15002))
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
#  Тест 16: PATCH лише name (без field_schema) → 200
# --------------------------------------------------------------------------- #
async def test_patch_name_only_ok(client: AsyncClient) -> None:
    await _bootstrap(client, tg_id=16001)
    tmpl = await _create_template(client, tg_id=16001)

    r = await client.patch(
        f"/api/templates/{tmpl['id']}",
        json={"name": "Нова назва"},
        headers=_hdr(16001),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Нова назва"
    assert r.json()["field_schema"] == _BASIC_SCHEMA


# --------------------------------------------------------------------------- #
#  Тест 17: GET повертає глобальні шаблони (bootstrap вже seed-ує їх)
# --------------------------------------------------------------------------- #
async def test_get_templates_includes_globals(client: AsyncClient) -> None:
    # bootstrap викликає seed_system_templates → глобальні вже є
    await _bootstrap(client, tg_id=17001)

    r = await client.get("/api/templates", headers=_hdr(17001))
    assert r.status_code == 200
    globals_ = [t for t in r.json() if t["shop_id"] is None]
    assert len(globals_) >= 1
