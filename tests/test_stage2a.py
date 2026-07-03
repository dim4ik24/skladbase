"""
Stage 2a acceptance tests (catalog: templates, products, variants, limits).

Criteria (ROADMAP.md, Стадія 2a):
  1. Футболка з 3 варіантами (S/чорна, M/чорна, L/біла) з шаблону «Одяг» -> 201,
     3 Variant з правильними axis_values, available рахується
  2. Дублікат SKU у тому ж магазині -> 409 (не 500)
  3. Магазин A не бачить і не редагує товари магазину B (ізоляція)
  4. Перевищення max_products на платному плані free -> 402 (не 500);
     на trial — ліміт не спрацьовує
  5. GET /api/templates повертає 5 системних шаблонів зі схемою полів
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import db
from app.models import Plan, Product, Subscription, SubStatus
from tests.conftest import make_init_data

HEADER = "X-Telegram-Init-Data"


async def _bootstrap(client: AsyncClient, tg_id: int, name: str = "Тест") -> tuple[str, int]:
    init_data = make_init_data(tg_id, first_name=name)
    r = await client.post("/api/shops", headers={HEADER: init_data}, json={"name": name})
    assert r.status_code == 201, r.text
    r = await client.get("/api/me", headers={HEADER: init_data})
    assert r.status_code == 200
    return init_data, r.json()["shop_id"]


async def _clothing_template_id(client: AsyncClient, init_data: str) -> int:
    r = await client.get("/api/templates", headers={HEADER: init_data})
    assert r.status_code == 200
    templates = {t["code"]: t for t in r.json()}
    return templates["clothing"]["id"]


@pytest.mark.asyncio
async def test_create_clothing_product_with_three_variants(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 1001)
    template_id = await _clothing_template_id(client, init_data)

    payload = {
        "name": "Футболка оверсайз",
        "template_id": template_id,
        "attributes": {"material": "100% бавовна", "brand": "Acme"},
        "variants": [
            {"axis_values": {"size": "S", "color": "чорний"}, "sku": "TS-S-BLK",
             "price": "450", "on_hand": 5},
            {"axis_values": {"size": "M", "color": "чорний"}, "sku": "TS-M-BLK",
             "price": "450", "on_hand": 3},
            {"axis_values": {"size": "L", "color": "білий"}, "sku": "TS-L-WHT",
             "price": "470", "on_hand": 0},
        ],
    }
    r = await client.post("/api/products", json=payload, headers={HEADER: init_data})
    assert r.status_code == 201, r.text
    body = r.json()

    assert len(body["variants"]) == 3
    by_sku = {v["sku"]: v for v in body["variants"]}
    assert by_sku["TS-S-BLK"]["axis_values"] == {"size": "S", "color": "чорний"}
    assert by_sku["TS-M-BLK"]["axis_values"] == {"size": "M", "color": "чорний"}
    assert by_sku["TS-L-WHT"]["axis_values"] == {"size": "L", "color": "білий"}
    assert by_sku["TS-S-BLK"]["available"] == 5
    assert by_sku["TS-M-BLK"]["available"] == 3
    assert by_sku["TS-L-WHT"]["available"] == 0
    assert Decimal(by_sku["TS-L-WHT"]["price"]) == Decimal("470")


@pytest.mark.asyncio
async def test_create_clothing_product_with_product_type_attribute(client: AsyncClient) -> None:
    """Пункт 11 фідбеку: "Тип товару" — необов'язковий enum-атрибут шаблону "Одяг"."""
    init_data, _shop_id = await _bootstrap(client, 1003)
    template_id = await _clothing_template_id(client, init_data)

    payload = {
        "name": "Худі оверсайз",
        "template_id": template_id,
        "attributes": {"product_type": "Худі", "material": "футер"},
        "variants": [
            {"axis_values": {"size": "M", "color": "сірий"}, "sku": "HD-M-GRY",
             "price": "890", "on_hand": 4},
        ],
    }
    r = await client.post("/api/products", json=payload, headers={HEADER: init_data})
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["attributes"]["product_type"] == "Худі"
    assert body["attributes"]["material"] == "футер"


@pytest.mark.asyncio
async def test_duplicate_sku_in_same_shop_returns_409(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 1002)

    payload_one = {
        "name": "Свічка А",
        "variants": [{"axis_values": {}, "sku": "DUP-1", "price": "100", "on_hand": 1}],
    }
    payload_two = {
        "name": "Свічка Б",
        "variants": [{"axis_values": {}, "sku": "DUP-1", "price": "120", "on_hand": 1}],
    }

    r1 = await client.post("/api/products", json=payload_one, headers={HEADER: init_data})
    assert r1.status_code == 201, r1.text

    r2 = await client.post("/api/products", json=payload_two, headers={HEADER: init_data})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_cross_shop_isolation(client: AsyncClient) -> None:
    init_data_a, _shop_a = await _bootstrap(client, 1101, "Шоп А")
    init_data_b, _shop_b = await _bootstrap(client, 1102, "Шоп Б")

    payload = {
        "name": "Товар магазину А",
        "variants": [{"axis_values": {}, "price": "50", "on_hand": 2}],
    }
    r = await client.post("/api/products", json=payload, headers={HEADER: init_data_a})
    assert r.status_code == 201
    product_id = r.json()["id"]

    r_list_b = await client.get("/api/products", headers={HEADER: init_data_b})
    assert r_list_b.status_code == 200
    assert all(p["id"] != product_id for p in r_list_b.json())

    r_patch_b = await client.patch(
        f"/api/products/{product_id}", json={"name": "Захоплено"}, headers={HEADER: init_data_b}
    )
    assert r_patch_b.status_code == 404

    r_delete_b = await client.delete(
        f"/api/products/{product_id}", headers={HEADER: init_data_b}
    )
    assert r_delete_b.status_code == 404


@pytest.mark.asyncio
async def test_max_products_limit_on_paid_plan_but_unlimited_on_trial(
    client: AsyncClient,
) -> None:
    # --- платний (не-тріал) магазин: ліміт free-плану має зрацювати --- #
    init_data_paid, shop_paid = await _bootstrap(client, 1201, "Платний")

    async with db.async_session() as session:
        free_plan = await session.scalar(select(Plan).where(Plan.code == "free"))
        assert free_plan is not None
        max_products = free_plan.limits["max_products"]

        for i in range(max_products):
            session.add(Product(shop_id=shop_paid, name=f"Товар {i}"))

        subscription = await session.scalar(
            select(Subscription).where(Subscription.shop_id == shop_paid)
        )
        assert subscription is not None
        subscription.status = SubStatus.active
        subscription.plan_id = free_plan.id
        await session.commit()

    payload = {"name": "Перевищення", "variants": [{"axis_values": {}, "price": "10"}]}
    r = await client.post("/api/products", json=payload, headers={HEADER: init_data_paid})
    assert r.status_code == 402

    # --- тріальний магазин з тією ж кількістю товарів: ліміт не діє --- #
    init_data_trial, shop_trial = await _bootstrap(client, 1202, "Тріал")

    async with db.async_session() as session:
        for i in range(max_products):
            session.add(Product(shop_id=shop_trial, name=f"Товар {i}"))
        await session.commit()

    r_trial = await client.post(
        "/api/products", json=payload, headers={HEADER: init_data_trial}
    )
    assert r_trial.status_code == 201, r_trial.text


@pytest.mark.asyncio
async def test_list_templates_returns_five_system_templates(client: AsyncClient) -> None:
    init_data, _shop_id = await _bootstrap(client, 1301)
    r = await client.get("/api/templates", headers={HEADER: init_data})
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) == 5
    codes = {t["code"] for t in templates}
    assert codes == {"clothing", "shoes", "cosmetics", "toys", "generic"}
    clothing = next(t for t in templates if t["code"] == "clothing")
    assert "variant_axes" in clothing["field_schema"]
    assert "attributes" in clothing["field_schema"]
