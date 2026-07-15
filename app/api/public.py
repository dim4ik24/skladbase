"""
SkladBase — публічний каталог магазину (Стадія 4b).

БЕЗ авторизації — це вітрина для сайту/покупця (`/c/{slug}` у README,
тут — JSON під ним). Read-only і нічого службового назовні: ані
on_hand/reserved/low_stock_threshold, ані SKU — лише те, що бачить покупець
(назва товару, ціна, axis_values, in_stock). Не світити рівні складу.

Галерея товару (F2): показуємо лише якщо план магазину дозволяє фото
(photos: true). На free — порожній список (фото і так не могли завантажитись).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.i18n import get_lang, msg
from app.models import Product, Shop
from app.security.rate_limit import InMemoryRateLimiter, rate_limited
from app.services.catalog import current_plan_limits, frozen_product_ids

router = APIRouter(prefix="/api/public", tags=["public"])

# Без авторизації, доступний усім — найімовірніша ціль скрейпінгу/DoS серед
# наших ендпоінтів (Стадія 8).
_public_catalog_limiter = InMemoryRateLimiter(
    "public_catalog", max_requests=30, window_seconds=60
)


class PublicVariantOut(BaseModel):
    axis_values: dict
    price: Decimal
    in_stock: bool


class PublicPhotoOut(BaseModel):
    url: str
    position: int


class PublicProductOut(BaseModel):
    name: str
    variants: list[PublicVariantOut]
    photos: list[PublicPhotoOut] = []


class PublicShopOut(BaseModel):
    name: str
    logo_url: str | None
    accent_color: str
    products: list[PublicProductOut]


@router.get(
    "/{slug}",
    response_model=PublicShopOut,
    dependencies=[Depends(rate_limited(_public_catalog_limiter))],
)
async def get_public_catalog(
    slug: str,
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(get_lang),
) -> PublicShopOut:
    shop = await session.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None or not shop.public_catalog_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=msg("public.catalog_not_found", lang)
        )

    products = (
        await session.scalars(
            select(Product)
            .options(selectinload(Product.variants), selectinload(Product.photos))
            .where(Product.shop_id == shop.id, Product.archived.is_(False))
            .order_by(Product.id)
        )
    ).all()

    frozen = await frozen_product_ids(shop.id, session)
    limits = await current_plan_limits(shop.id, session)
    photos_enabled = bool(limits.get("photos"))

    visible_products = [p for p in products if p.id not in frozen]

    return PublicShopOut(
        name=shop.name,
        logo_url=shop.logo_url,
        accent_color=shop.accent_color,
        products=[
            PublicProductOut(
                name=product.name,
                variants=[
                    PublicVariantOut(
                        axis_values=variant.axis_values,
                        price=variant.price,
                        in_stock=variant.available > 0,
                    )
                    for variant in product.variants
                ],
                photos=sorted(
                    [PublicPhotoOut(url=ph.url, position=ph.position) for ph in product.photos],
                    key=lambda ph: ph.position,
                ) if photos_enabled else [],
            )
            for product in visible_products
        ],
    )
