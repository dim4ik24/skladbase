"""
SkladBase — сід даних.

  seed_system_templates() — шаблони полів (одяг/взуття/косметика/іграшки). Раз на БД.
  seed_plans()            — тарифи free/basic/pro. Раз на БД.
  seed_demo_catalog(shop) — засіяти демо-товари новому магазину (фіча 1):
                            щоб при першому відкритті був НЕ порожній екран.
                            Усі товари позначені is_demo=True -> можна потім
                            масово прибрати кнопкою «Очистити приклади».
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.models import (
    Plan,
    Product,
    ProductTemplate,
    Shop,
    SubPeriod,
    TemplateCode,
    Variant,
)

# --------------------------------------------------------------------------- #
#  Шаблони полів (фіча 6)                                                      #
# --------------------------------------------------------------------------- #
SYSTEM_TEMPLATES = {
    TemplateCode.clothing: {
        "name": "Одяг",
        "field_schema": {
            "attributes": [
                {"key": "material", "label": "Матеріал", "type": "string"},
                {"key": "brand", "label": "Бренд", "type": "string"},
            ],
            "variant_axes": [
                {"key": "size", "label": "Розмір", "type": "enum",
                 "options": ["XS", "S", "M", "L", "XL", "XXL"]},
                {"key": "color", "label": "Колір", "type": "string"},
            ],
        },
    },
    TemplateCode.shoes: {
        "name": "Взуття",
        "field_schema": {
            "attributes": [{"key": "brand", "label": "Бренд", "type": "string"}],
            "variant_axes": [
                {"key": "size", "label": "Розмір (EU)", "type": "enum",
                 "options": [str(s) for s in range(35, 47)]},
                {"key": "color", "label": "Колір", "type": "string"},
            ],
        },
    },
    TemplateCode.cosmetics: {
        "name": "Косметика",
        "field_schema": {
            "attributes": [
                {"key": "volume", "label": "Обʼєм", "type": "string"},
                {"key": "brand", "label": "Бренд", "type": "string"},
            ],
            "variant_axes": [
                {"key": "shade", "label": "Відтінок", "type": "string"},
            ],
            "extras": {"track_expiry": True},   # вмикає поле expires_on + алерт
        },
    },
    TemplateCode.toys: {
        "name": "Фігурки / іграшки",
        "field_schema": {
            "attributes": [
                {"key": "brand", "label": "Бренд", "type": "string"},
                {"key": "scale", "label": "Масштаб", "type": "string"},
                {"key": "package", "label": "Стан упаковки", "type": "string"},
            ],
            "variant_axes": [],   # зазвичай 1 одиниця = 1 варіант
        },
    },
    TemplateCode.generic: {
        "name": "Інше",
        "field_schema": {"attributes": [], "variant_axes": []},
    },
}


async def seed_system_templates(session: AsyncSession) -> None:
    for code, data in SYSTEM_TEMPLATES.items():
        exists = await session.scalar(
            select(ProductTemplate).where(
                ProductTemplate.shop_id.is_(None), ProductTemplate.code == code
            )
        )
        if not exists:
            session.add(ProductTemplate(
                shop_id=None, code=code, name=data["name"], field_schema=data["field_schema"]
            ))
    await session.commit()


# --------------------------------------------------------------------------- #
#  Тарифи                                                                      #
# --------------------------------------------------------------------------- #
async def seed_plans(session: AsyncSession) -> None:
    plans = [
        Plan(code="free", name="Free", period=SubPeriod.month,
             price_uah=Decimal("0"), price_stars=0,
             limits={"max_products": 20, "photos": False, "integrations": False}),
        Plan(code="basic", name="Basic", period=SubPeriod.month,
             price_uah=Decimal("150"), price_stars=100,
             limits={"max_products": 200, "photos": True, "integrations": False}),
        Plan(code="pro", name="Pro", period=SubPeriod.month,
             price_uah=Decimal("350"), price_stars=230,
             limits={"max_products": None, "photos": True, "integrations": True}),
    ]
    for p in plans:
        exists = await session.scalar(select(Plan).where(Plan.code == p.code))
        if not exists:
            session.add(p)
    await session.commit()


# --------------------------------------------------------------------------- #
#  Демо-каталог нового магазину (фіча 1)                                       #
# --------------------------------------------------------------------------- #
async def seed_demo_catalog(session: AsyncSession, shop: Shop) -> None:
    """Викликати при створенні магазину. Товари -> is_demo=True."""
    tpl_clothing = await session.scalar(
        select(ProductTemplate).where(
            ProductTemplate.shop_id.is_(None), ProductTemplate.code == TemplateCode.clothing
        )
    )

    # 1) Футболка з варіантами (показує силу системи варіантів)
    tshirt = Product(
        shop_id=shop.id, template_id=tpl_clothing.id if tpl_clothing else None,
        name="Базова футболка (приклад)", is_demo=True,
        attributes={"material": "100% бавовна", "brand": "Demo"},
    )
    session.add(tshirt)
    await session.flush()
    session.add_all([
        Variant(shop_id=shop.id, product_id=tshirt.id, sku="DEMO-TS-S-BLK",
                axis_values={"size": "S", "color": "чорний"}, price=Decimal("450"),
                on_hand=8, reserved=1, low_stock_threshold=3),
        Variant(shop_id=shop.id, product_id=tshirt.id, sku="DEMO-TS-M-BLK",
                axis_values={"size": "M", "color": "чорний"}, price=Decimal("450"),
                on_hand=3, reserved=0, low_stock_threshold=3),  # на межі -> покаже low-stock
        Variant(shop_id=shop.id, product_id=tshirt.id, sku="DEMO-TS-L-WHT",
                axis_values={"size": "L", "color": "білий"}, price=Decimal("450"),
                on_hand=0, reserved=0),  # показує "нема в наявності"
    ])

    # 2) Простий товар без варіантів
    candle = Product(
        shop_id=shop.id, name="Соєва свічка (приклад)", is_demo=True,
        attributes={"brand": "Demo"},
    )
    session.add(candle)
    await session.flush()
    session.add(Variant(
        shop_id=shop.id, product_id=candle.id, sku="DEMO-CANDLE",
        axis_values={}, price=Decimal("220"), on_hand=15, reserved=0,
    ))

    await session.commit()


async def clear_demo_catalog(session: AsyncSession, shop: Shop) -> int:
    """Кнопка «Очистити приклади» — прибрати все is_demo, коли магазин почав свій облік."""
    demos = (await session.scalars(
        select(Product).where(Product.shop_id == shop.id, Product.is_demo.is_(True))
    )).all()
    for p in demos:
        await session.delete(p)   # cascade прибере варіанти
    await session.commit()
    return len(demos)


# --------------------------------------------------------------------------- #
#  Прод-entrypoint: `python -m app.seed`                                       #
# --------------------------------------------------------------------------- #
async def main() -> None:
    """Сід системних шаблонів і тарифів на новій (прод) БД. Безпечно
    запускати повторно — обидві функції перевіряють існування перед
    insert, дублікатів не буде."""
    async with db.async_session() as session:
        await seed_system_templates(session)
        await seed_plans(session)


if __name__ == "__main__":
    asyncio.run(main())
