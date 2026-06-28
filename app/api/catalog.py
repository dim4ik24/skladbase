"""
SkladBase — REST API каталогу (шаблони, товари, варіанти, фото).

Усі ендпоінти під `require_member`/`require_writable`: shop_id виключно з
`membership.shop_id` (валідований Telegram initData), ніколи з тіла/параметрів
запиту (CLAUDE.md, інваріант №1).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_session
from app.deps import require_permission, require_permission_writable
from app.models import Membership, Product, ProductPhoto, ProductTemplate, TemplateCode, Variant
from app.services import catalog as catalog_service
from app.services import media as media_service
from app.services import templates as templates_service

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
    shop_id: int | None = None


class TemplateIn(BaseModel):
    name: str
    field_schema: dict


class TemplatePatch(BaseModel):
    name: str | None = None
    field_schema: dict | None = None


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
    photo_url: str | None


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


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    position: int


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
    is_frozen: bool = False
    photos: list[PhotoOut] = []


# --------------------------------------------------------------------------- #
#  Шаблони
# --------------------------------------------------------------------------- #
@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    membership: Membership = require_permission("can_view_inventory"),
    session: AsyncSession = Depends(get_session),
) -> list[ProductTemplate]:
    """Базові (shop_id NULL) + кастомні поточного магазину."""
    templates = (
        await session.scalars(
            select(ProductTemplate)
            .where(
                (ProductTemplate.shop_id.is_(None))
                | (ProductTemplate.shop_id == membership.shop_id)
            )
            .order_by(ProductTemplate.id)
        )
    ).all()
    return list(templates)


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateIn,
    membership: Membership = require_permission("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> ProductTemplate:
    try:
        return await templates_service.create_custom_template(
            session, membership, payload.name, payload.field_schema
        )
    except templates_service.TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def patch_template(
    template_id: int,
    payload: TemplatePatch,
    membership: Membership = require_permission("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> ProductTemplate:
    try:
        return await templates_service.patch_custom_template(
            session, membership, template_id, payload.name, payload.field_schema
        )
    except templates_service.TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    membership: Membership = require_permission("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await templates_service.delete_custom_template(session, membership, template_id)
    except templates_service.TemplateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


# --------------------------------------------------------------------------- #
#  Товари
# --------------------------------------------------------------------------- #
@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductIn,
    membership: Membership = require_permission_writable("can_edit_products"),
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
    membership: Membership = require_permission("can_view_inventory"),
    session: AsyncSession = Depends(get_session),
) -> list[ProductOut]:
    products = (
        await session.scalars(
            select(Product)
            .options(selectinload(Product.variants), selectinload(Product.photos))
            .where(Product.shop_id == membership.shop_id, Product.archived.is_(False))
            .order_by(Product.id)
        )
    ).all()

    frozen = await catalog_service.frozen_product_ids(membership.shop_id, session)

    result: list[ProductOut] = []
    for p in products:
        out = ProductOut.model_validate(p)
        out.is_frozen = p.id in frozen
        out.photos = sorted(
            [PhotoOut.model_validate(ph) for ph in p.photos],
            key=lambda ph: ph.position,
        )
        result.append(out)
    return result


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
    membership: Membership = require_permission_writable("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> Product:
    product = await _get_owned_product(session, membership.shop_id, product_id)

    try:
        await catalog_service.enforce_product_writable(product.id, membership.shop_id, session)
    except catalog_service.CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field_name, value)

    await session.commit()
    await session.refresh(product, attribute_names=["variants", "photos"])
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    membership: Membership = require_permission_writable("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> None:
    product = await _get_owned_product(session, membership.shop_id, product_id)
    product.archived = True
    await session.commit()


# --------------------------------------------------------------------------- #
#  Фото (Стадія 2b)
# --------------------------------------------------------------------------- #
@router.post("/variants/{variant_id}/photo", response_model=VariantOut)
async def upload_variant_photo(
    variant_id: int,
    request: Request,
    file: UploadFile = File(...),
    membership: Membership = require_permission_writable("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> Variant:
    variant = await session.scalar(
        select(Variant).where(Variant.id == variant_id, Variant.shop_id == membership.shop_id)
    )
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Варіант не знайдено")

    try:
        await catalog_service.enforce_product_writable(variant.product_id, membership.shop_id, session)
        await catalog_service.enforce_photos_allowed(membership.shop_id, session)
    except catalog_service.CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    max_bytes = media_service.max_upload_bytes()

    # Content-Length перевіряємо ДО читання тіла — завеликий запит відхиляємо
    # одразу, без буферизації файлу в памʼяті (ROADMAP, відкладено зі Стадії 2b).
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Файл занадто великий: максимум {settings.MAX_PHOTO_UPLOAD_MB} МБ.",
            )

    try:
        # Нема Content-Length (chunked) -> читаємо з обмеженням (cap), щоб не
        # буферизувати необмежений потік цілком.
        data = await media_service.read_capped(file, max_bytes)
        photo_url = await media_service.upload_variant_photo(
            shop_id=membership.shop_id,
            variant_id=variant.id,
            content_type=file.content_type or "",
            data=data,
        )
    except media_service.MediaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    variant.photo_url = photo_url
    await session.commit()
    await session.refresh(variant)
    return variant


# --------------------------------------------------------------------------- #
#  Галерея фото товару (F2)
# --------------------------------------------------------------------------- #
@router.post(
    "/products/{product_id}/photos",
    response_model=PhotoOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_product_photo(
    product_id: int,
    request: Request,
    file: UploadFile = File(...),
    membership: Membership = require_permission_writable("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> ProductPhoto:
    product = await _get_owned_product(session, membership.shop_id, product_id)

    try:
        await catalog_service.enforce_product_writable(product.id, membership.shop_id, session)
        await catalog_service.enforce_photos_allowed(membership.shop_id, session)
    except catalog_service.CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    photo_count = await session.scalar(
        select(func.count(ProductPhoto.id)).where(ProductPhoto.product_id == product_id)
    )
    if (photo_count or 0) >= 10:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Максимум 10 фото на товар"
        )

    max_bytes = media_service.max_upload_bytes()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Файл занадто великий: максимум {settings.MAX_PHOTO_UPLOAD_MB} МБ.",
            )

    try:
        data = await media_service.read_capped(file, max_bytes)
        url = await media_service.upload_photo(
            key_prefix=f"shops/{membership.shop_id}/products/{product_id}",
            content_type=file.content_type or "",
            data=data,
        )
    except media_service.MediaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    max_pos = await session.scalar(
        select(func.max(ProductPhoto.position)).where(ProductPhoto.product_id == product_id)
    )
    next_position = (max_pos + 1) if max_pos is not None else 0

    photo = ProductPhoto(product_id=product_id, url=url, position=next_position)
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return photo


@router.delete(
    "/products/{product_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product_photo(
    product_id: int,
    photo_id: int,
    membership: Membership = require_permission("can_edit_products"),
    session: AsyncSession = Depends(get_session),
) -> None:
    product = await _get_owned_product(session, membership.shop_id, product_id)

    photo = await session.scalar(
        select(ProductPhoto).where(
            ProductPhoto.id == photo_id, ProductPhoto.product_id == product.id
        )
    )
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Фото не знайдено")

    await media_service.delete_photo(photo.url)
    await session.delete(photo)
    await session.commit()
