"""
SkladBase — REST API каталогу (шаблони, товари, варіанти).

Усі ендпоінти під `require_member`: shop_id виключно з `membership.shop_id`
(валідований Telegram initData), ніколи з тіла/параметрів запиту
(CLAUDE.md, інваріант №1). Стадія 2a — без фото (буде в 2b).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.deps import require_member, require_writable
from app.models import Membership, Product, ProductTemplate, TemplateCode
from app.services import catalog as catalog_service

router = APIRouter(prefix="/api", tags=["catalog"])


# --------------------------------------------------------------------------- #
#  Схеми
# --------------------------------------------------------------------------- #
class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: TemplateCode
    name: str
    field_schema: dict


class VariantIn(BaseModel):
    price: Decimal
    axis_values: dict[str, str] = Field(default_factory=dict)
    sku: str | None = None
    on_hand: int = 0
    low_stock_threshold: int = 3


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str | None
    axis_values: dict
    price: Decimal
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int


class ProductIn(BaseModel):
    name: str
    variants: list[VariantIn]
    description: str | None = None
    template_id: int | None = None
    attributes: dict = Field(default_factory=dict)


class ProductPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    attributes: dict | None = None
    archived: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    template_id: int | None
    attributes: dict
    is_demo: bool
    archived: bool
    variants: list[VariantOut]


# --------------------------------------------------------------------------- #
#  Шаблони
# --------------------------------------------------------------------------- #
@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> list[ProductTemplate]:
    templates = (
        await session.scalars(
            select(ProductTemplate)
            .where(ProductTemplate.shop_id.is_(None))
            .order_by(ProductTemplate.id)
        )
    ).all()
    return list(templates)


# --------------------------------------------------------------------------- #
#  Товари
# --------------------------------------------------------------------------- #
@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductIn,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Product:
    service_payload = catalog_service.ProductInput(
        name=payload.name,
        description=payload.description,
        template_id=payload.template_id,
        attributes=payload.attributes,
        variants=[
            catalog_service.VariantInput(
                axis_values=v.axis_values,
                price=v.price,
                sku=v.sku,
                on_hand=v.on_hand,
                low_stock_threshold=v.low_stock_threshold,
            )
            for v in payload.variants
        ],
    )
    try:
        return await catalog_service.create_product_with_variants(
            session, membership, service_payload
        )
    except catalog_service.CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    membership: Membership = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> list[Product]:
    products = (
        await session.scalars(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.shop_id == membership.shop_id, Product.archived.is_(False))
            .order_by(Product.id)
        )
    ).all()
    return list(products)


async def _get_owned_product(session: AsyncSession, shop_id: int, product_id: int) -> Product:
    product = await session.scalar(
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.id == product_id, Product.shop_id == shop_id)
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
async def patch_product(
    product_id: int,
    payload: ProductPatch,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> Product:
    product = await _get_owned_product(session, membership.shop_id, product_id)

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field_name, value)

    await session.commit()
    await session.refresh(product, attribute_names=["variants"])
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    membership: Membership = Depends(require_writable),
    session: AsyncSession = Depends(get_session),
) -> None:
    product = await _get_owned_product(session, membership.shop_id, product_id)
    product.archived = True
    await session.commit()
