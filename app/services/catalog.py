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
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import ServiceError
from app.models import (
    Membership,
    Plan,
    Product,
    ProductTemplate,
    Reservation,
    ReservationStatus,
    Subscription,
    SubStatus,
    Variant,
    ensure_aware_utc,
    utcnow,
)


class CatalogError(ServiceError):
    """Помилка каталогу з HTTP статус-кодом для API-шару. Текст рендериться
    на межі API-шару через .detail(lang) — див. app/i18n.py."""


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
            "catalog.plan_limit_products",
            max=max_products,
        )


async def enforce_product_writable(product_id: int, shop_id: int, session: AsyncSession) -> None:
    """402 якщо товар заморожений (не входить у топ-N активних free-плану)."""
    frozen = await frozen_product_ids(shop_id, session)
    if product_id in frozen:
        raise CatalogError(HTTPStatus.PAYMENT_REQUIRED, "catalog.product_frozen")


async def enforce_photos_allowed(shop_id: int, session: AsyncSession) -> None:
    """402 якщо поточний план не дозволяє фото (free: photos=False)."""
    limits = await current_plan_limits(shop_id, session)
    if not limits.get("photos"):
        raise CatalogError(HTTPStatus.PAYMENT_REQUIRED, "catalog.photos_not_allowed")


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
        raise CatalogError(HTTPStatus.BAD_REQUEST, "catalog.unknown_axes", axes=sorted(unknown))
    missing = axis_keys - set(variant.axis_values)
    if missing:
        raise CatalogError(HTTPStatus.BAD_REQUEST, "catalog.missing_axes", axes=sorted(missing))
    for key, allowed in enum_options.items():
        value = variant.axis_values.get(key)
        if value is not None and value not in allowed:
            raise CatalogError(
                HTTPStatus.BAD_REQUEST,
                "catalog.invalid_axis_value",
                value=value,
                key=key,
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
        raise CatalogError(HTTPStatus.NOT_FOUND, "catalog.template_not_found")
    return template


async def create_product_with_variants(
    session: AsyncSession, membership: Membership, payload: ProductInput
) -> Product:
    shop_id = membership.shop_id

    if not payload.variants:
        raise CatalogError(HTTPStatus.BAD_REQUEST, "catalog.variant_required")

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
            raise CatalogError(HTTPStatus.CONFLICT, "catalog.sku_taken") from exc
        raise CatalogError(HTTPStatus.CONFLICT, "catalog.product_create_conflict") from exc

    await session.commit()
    await session.refresh(product, attribute_names=["variants", "photos"])
    return product


# --------------------------------------------------------------------------- #
#  Variant CRUD (feat-variant-crud)                                           #
# --------------------------------------------------------------------------- #

async def _load_variant_for_shop(
    session: AsyncSession, variant_id: int, shop_id: int
) -> Variant:
    variant = await session.scalar(
        select(Variant).where(Variant.id == variant_id, Variant.shop_id == shop_id)
    )
    if variant is None:
        raise CatalogError(HTTPStatus.NOT_FOUND, "catalog.variant_not_found")
    return variant


async def _check_no_axis_duplicate(
    session: AsyncSession,
    product_id: int,
    axis_values: dict[str, Any],
    exclude_id: int | None = None,
) -> None:
    """Raise 409 if any sibling variant has the same axis_values dict."""
    q = select(Variant).where(Variant.product_id == product_id)
    if exclude_id is not None:
        q = q.where(Variant.id != exclude_id)
    rows = (await session.scalars(q)).all()
    for v in rows:
        if v.axis_values == axis_values:
            raise CatalogError(HTTPStatus.CONFLICT, "catalog.variant_axes_conflict")


async def patch_variant(
    session: AsyncSession,
    membership: Membership,
    variant_id: int,
    updates: dict[str, Any],
) -> Variant:
    """Update price/sku/axis_values only. Never touches on_hand or reserved."""
    variant = await _load_variant_for_shop(session, variant_id, membership.shop_id)
    await enforce_product_writable(variant.product_id, membership.shop_id, session)

    if "axis_values" in updates:
        new_axis: dict[str, Any] = updates["axis_values"]
        product = await session.get(Product, variant.product_id)
        assert product is not None
        template = await _resolve_template(session, membership.shop_id, product.template_id)
        _validate_axis_values(template, VariantInput(price=variant.price, axis_values=new_axis))
        await _check_no_axis_duplicate(
            session, variant.product_id, new_axis, exclude_id=variant.id
        )

    for field_name in ("price", "sku", "axis_values"):
        if field_name in updates:
            setattr(variant, field_name, updates[field_name])

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if _is_sku_conflict(exc):
            raise CatalogError(HTTPStatus.CONFLICT, "catalog.sku_taken") from exc
        raise CatalogError(HTTPStatus.CONFLICT, "catalog.variant_update_failed") from exc

    await session.commit()
    await session.refresh(variant)
    return variant


@dataclass
class VariantAddInput:
    price: Decimal
    axis_values: dict[str, str] = field(default_factory=dict)
    sku: str | None = None


async def add_variant_to_product(
    session: AsyncSession,
    membership: Membership,
    product_id: int,
    payload: VariantAddInput,
) -> Variant:
    product = await session.scalar(
        select(Product).where(Product.id == product_id, Product.shop_id == membership.shop_id)
    )
    if product is None:
        raise CatalogError(HTTPStatus.NOT_FOUND, "catalog.product_not_found")

    await enforce_product_writable(product_id, membership.shop_id, session)

    template = await _resolve_template(session, membership.shop_id, product.template_id)
    _validate_axis_values(template, VariantInput(price=payload.price, axis_values=payload.axis_values))
    await _check_no_axis_duplicate(session, product_id, payload.axis_values)

    variant = Variant(
        shop_id=membership.shop_id,
        product_id=product_id,
        sku=payload.sku,
        axis_values=payload.axis_values,
        price=payload.price,
        on_hand=0,
    )
    session.add(variant)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if _is_sku_conflict(exc):
            raise CatalogError(HTTPStatus.CONFLICT, "catalog.sku_taken") from exc
        raise CatalogError(HTTPStatus.CONFLICT, "catalog.variant_add_failed") from exc

    await session.commit()
    await session.refresh(variant)
    return variant


async def delete_variant(
    session: AsyncSession,
    membership: Membership,
    variant_id: int,
) -> str | None:
    """Delete variant. Returns photo_url so caller can best-effort remove from R2."""
    variant = await _load_variant_for_shop(session, variant_id, membership.shop_id)
    await enforce_product_writable(variant.product_id, membership.shop_id, session)

    sibling_count = await session.scalar(
        select(func.count(Variant.id)).where(Variant.product_id == variant.product_id)
    )
    if (sibling_count or 0) <= 1:
        raise CatalogError(HTTPStatus.CONFLICT, "catalog.product_needs_variant")

    active_res = await session.scalar(
        select(func.count(Reservation.id)).where(
            Reservation.variant_id == variant_id,
            Reservation.status == ReservationStatus.active,
        )
    )
    if (active_res or 0) > 0:
        raise CatalogError(HTTPStatus.CONFLICT, "catalog.release_before_delete")

    photo_url = variant.photo_url
    await session.delete(variant)
    await session.commit()
    return photo_url
