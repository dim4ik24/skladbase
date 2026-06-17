"""
SkladBase — публічний каталог магазину (Стадія 4b).

БЕЗ авторизації — це вітрина для сайту/покупця (`/c/{slug}` у README,
тут — JSON під ним). Read-only і нічого службового назовні: ані
on_hand/reserved/low_stock_threshold, ані SKU — лише те, що бачить покупець
(назва товару, ціна, axis_values, in_stock). Не світити рівні складу.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Product, Shop

router = APIRouter(prefix="/api/public", tags=["public"])


class PublicVariantOut(BaseModel):
    axis_values: dict
    price: Decimal
    in_stock: bool


class PublicProductOut(BaseModel):
    name: str
    variants: list[PublicVariantOut]


class PublicShopOut(BaseModel):
    name: str
    logo_url: str | None
    accent_color: str
    products: list[PublicProductOut]


@router.get("/{slug}", response_model=PublicShopOut)
async def get_public_catalog(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> PublicShopOut:
    shop = await session.scalar(select(Shop).where(Shop.slug == slug))
    if shop is None or not shop.public_catalog_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Каталог не знайдено")

    products = (
        await session.scalars(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.shop_id == shop.id, Product.archived.is_(False))
            .order_by(Product.id)
        )
    ).all()

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
            )
            for product in products
        ],
    )
