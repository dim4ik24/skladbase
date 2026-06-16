"""
SkladBase — сервіс каталогу: товари, варіанти, генерація з осей шаблону.

Усі операції tenant-scoped: shop_id береться лише з `Membership`
(`resolve_membership`), ніколи з тіла запиту. Зміни складу (on_hand/reserved)
сюди не лізуть — це виключна територія `services/inventory.py`
(CLAUDE.md, інваріант №3); тут лише початкові значення нового варіанта.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from http import HTTPStatus

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Membership,
    Plan,
    Product,
    ProductTemplate,
    Subscription,
    SubStatus,
    Variant,
)


class CatalogError(Exception):
    """Помилка каталогу з HTTP статус-кодом для API-шару."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class VariantInput:
    price: Decimal
    axis_values: dict[str, str] = field(default_factory=dict)
    sku: str | None = None
    on_hand: int = 0
    low_stock_threshold: int = 3


@dataclass
class ProductInput:
    name: str
    variants: list[VariantInput]
    description: str | None = None
    template_id: int | None = None
    attributes: dict | None = None


async def _count_active_products(session: AsyncSession, shop_id: int) -> int:
    count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.shop_id == shop_id, Product.archived.is_(False)
        )
    )
    return count or 0


async def _enforce_product_limit(session: AsyncSession, shop_id: int) -> None:
    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == shop_id)
    )
    if subscription is None or subscription.status == SubStatus.trial:
        return  # тріал -> повний доступ, свідомо для конверсії (CLAUDE.md)

    if subscription.plan_id is None:
        return

    plan = await session.get(Plan, subscription.plan_id)
    if plan is None:
        return

    max_products = plan.limits.get("max_products")
    if max_products is None:
        return  # необмежено (pro)

    current = await _count_active_products(session, shop_id)
    if current >= max_products:
        raise CatalogError(
            HTTPStatus.PAYMENT_REQUIRED,
            f"Ліміт товарів плану досягнуто ({max_products})",
        )


def _validate_axis_values(template: ProductTemplate | None, variant: VariantInput) -> None:
    axes = (template.field_schema.get("variant_axes") if template else None) or []
    axis_keys = {axis["key"] for axis in axes}
    enum_options = {
        axis["key"]: set(axis["options"])
        for axis in axes
        if axis.get("type") == "enum" and "options" in axis
    }

    unknown = set(variant.axis_values) - axis_keys
    if unknown:
        raise CatalogError(
            HTTPStatus.BAD_REQUEST, f"Невідомі осі варіанта: {sorted(unknown)}"
        )
    missing = axis_keys - set(variant.axis_values)
    if missing:
        raise CatalogError(
            HTTPStatus.BAD_REQUEST, f"Не вказані осі варіанта: {sorted(missing)}"
        )
    for key, allowed in enum_options.items():
        value = variant.axis_values.get(key)
        if value is not None and value not in allowed:
            raise CatalogError(
                HTTPStatus.BAD_REQUEST,
                f"Недопустиме значення '{value}' для осі '{key}'",
            )


async def _resolve_template(
    session: AsyncSession, shop_id: int, template_id: int | None
) -> ProductTemplate | None:
    if template_id is None:
        return None
    template = await session.scalar(
        select(ProductTemplate).where(
            ProductTemplate.id == template_id,
            (ProductTemplate.shop_id == shop_id) | (ProductTemplate.shop_id.is_(None)),
        )
    )
    if template is None:
        raise CatalogError(HTTPStatus.NOT_FOUND, "Шаблон не знайдено")
    return template


async def create_product_with_variants(
    session: AsyncSession, membership: Membership, payload: ProductInput
) -> Product:
    shop_id = membership.shop_id

    if not payload.variants:
        raise CatalogError(HTTPStatus.BAD_REQUEST, "Потрібен хоча б один варіант")

    template = await _resolve_template(session, shop_id, payload.template_id)
    for variant_input in payload.variants:
        _validate_axis_values(template, variant_input)

    await _enforce_product_limit(session, shop_id)

    product = Product(
        shop_id=shop_id,
        template_id=template.id if template else None,
        name=payload.name,
        description=payload.description,
        attributes=payload.attributes or {},
    )
    session.add(product)
    await session.flush()

    for variant_input in payload.variants:
        session.add(
            Variant(
                shop_id=shop_id,
                product_id=product.id,
                sku=variant_input.sku,
                axis_values=variant_input.axis_values,
                price=variant_input.price,
                on_hand=variant_input.on_hand,
                low_stock_threshold=variant_input.low_stock_threshold,
            )
        )

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise CatalogError(
            HTTPStatus.CONFLICT, "SKU вже використовується в цьому магазині"
        ) from exc

    await session.commit()
    await session.refresh(product, attribute_names=["variants"])
    return product
