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
    ensure_aware_utc,
    utcnow,
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


def _is_sku_conflict(exc: IntegrityError) -> bool:
    """`Variant` має лише один іменований unique-constraint —
    `uq_variant_shop_sku` (`shop_id`+`sku`). Postgres віддає назву обмеження
    у тексті помилки напряму; SQLite — лише назви колонок. Перевіряємо обидва
    варіанти, щоб НЕ підписувати довільний `IntegrityError` (інша гонка,
    FK-порушення тощо) як "SKU вже використовується" (ROADMAP, відкладено
    зі Стадії 2a) — оманливий текст гірший за загальний."""
    message = str(getattr(exc, "orig", exc)).lower()
    if "uq_variant_shop_sku" in message:
        return True
    return "variants.shop_id" in message and "variants.sku" in message


async def _count_active_products(session: AsyncSession, shop_id: int) -> int:
    count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.shop_id == shop_id, Product.archived.is_(False)
        )
    )
    return count or 0


# --------------------------------------------------------------------------- #
#  Plan limits (FREE_PLAN_SPEC)                                               #
# --------------------------------------------------------------------------- #

_FREE_LIMITS_FALLBACK: dict = {"max_products": 20, "photos": False, "integrations": False}


async def _free_plan_limits(session: AsyncSession) -> dict:
    free = await session.scalar(select(Plan).where(Plan.code == "free"))
    return dict(free.limits) if free is not None else _FREE_LIMITS_FALLBACK


async def current_plan_limits(shop_id: int, session: AsyncSession) -> dict:
    """Ліміти діючого плану магазину.

    Active trial  → необмежено (повний доступ для конверсії).
    Active/canceled/past_due з plan_id → ліміти цього плану.
    Решта (expired trial, expired sub, no sub) → ліміти free-плану.
    """
    subscription = await session.scalar(
        select(Subscription).where(Subscription.shop_id == shop_id)
    )

    if subscription is not None:
        if subscription.status == SubStatus.trial:
            if (
                subscription.trial_ends_at
                and ensure_aware_utc(subscription.trial_ends_at) > utcnow()
            ):
                # Активний тріал — повний доступ.
                return {"max_products": None, "photos": True, "integrations": True}
            # Тріал завершився → free.
        elif subscription.status in (SubStatus.active, SubStatus.canceled, SubStatus.past_due):
            if subscription.plan_id:
                plan = await session.get(Plan, subscription.plan_id)
                if plan is not None:
                    return dict(plan.limits)

    return await _free_plan_limits(session)


async def frozen_product_ids(shop_id: int, session: AsyncSession) -> set[int]:
    """Id заморожених товарів магазину (похідне, без поля в БД).

    Заморожені = всі non-archived, що НЕ входять у топ-N за (created_at DESC, id DESC).
    N = max_products з поточного плану; None → безліміт → порожній set.
    Стабільний tiebreaker (id) гарантує однаковий набір при рівних created_at.
    """
    limits = await current_plan_limits(shop_id, session)
    max_products = limits.get("max_products")
    if max_products is None:
        return set()

    all_ids: list[int] = list(
        await session.scalars(
            select(Product.id)
            .where(Product.shop_id == shop_id, Product.archived.is_(False))
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
    )

    if len(all_ids) <= max_products:
        return set()

    return set(all_ids[max_products:])


async def enforce_can_create_product(shop_id: int, session: AsyncSession) -> None:
    """402 якщо кількість активних товарів ≥ max_products плану."""
    limits = await current_plan_limits(shop_id, session)
    max_products = limits.get("max_products")
    if max_products is None:
        return

    current = await _count_active_products(session, shop_id)
    if current >= max_products:
        raise CatalogError(
            HTTPStatus.PAYMENT_REQUIRED,
            f"Ліміт плану: {max_products} товарів. Оформіть тариф для розширення.",
        )


async def enforce_product_writable(product_id: int, shop_id: int, session: AsyncSession) -> None:
    """402 якщо товар заморожений (не входить у топ-N активних free-плану)."""
    frozen = await frozen_product_ids(shop_id, session)
    if product_id in frozen:
        raise CatalogError(
            HTTPStatus.PAYMENT_REQUIRED,
            "Цей товар заморожено. Оформіть тариф, щоб редагувати.",
        )


async def enforce_photos_allowed(shop_id: int, session: AsyncSession) -> None:
    """402 якщо поточний план не дозволяє фото (free: photos=False)."""
    limits = await current_plan_limits(shop_id, session)
    if not limits.get("photos"):
        raise CatalogError(
            HTTPStatus.PAYMENT_REQUIRED,
            "Фото доступні на тарифі Basic+. Оформіть тариф.",
        )


# Збережено для сумісності з api/catalog.py до рефакторингу імпортів.
enforce_photo_upload_allowed = enforce_photos_allowed


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

    await enforce_can_create_product(shop_id, session)

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
        if _is_sku_conflict(exc):
            raise CatalogError(
                HTTPStatus.CONFLICT, "SKU вже використовується в цьому магазині"
            ) from exc
        raise CatalogError(
            HTTPStatus.CONFLICT, "Не вдалося створити товар через конфлікт даних"
        ) from exc

    await session.commit()
    await session.refresh(product, attribute_names=["variants"])
    return product
