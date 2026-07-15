"""
SkladBase — сервіс кастомних шаблонів товару (F1).

Всі операції tenant-scoped: shop_id береться з Membership,
ніколи з тіла запиту (CLAUDE.md, інваріант №1).
"""
from __future__ import annotations

import re
from http import HTTPStatus

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import ServiceError
from app.models import Membership, Product, ProductTemplate, TemplateCode


class TemplateError(ServiceError):
    """Помилка сервісу шаблонів із HTTP статус-кодом для API-шару. Текст
    рендериться на межі API-шару через .detail(lang) — див. app/i18n.py."""


_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_VALID_TYPES = {"enum", "string"}


def validate_field_schema(schema: dict) -> None:
    """Валідація field_schema шаблону.

    Правила:
    - структура: {"attributes": [...], "variant_axes": [...]}.
    - кожне поле: key (непорожній, [a-zA-Z][a-zA-Z0-9_]*), label (непорожній),
      type ∈ {"enum","string"}.
    - type=="enum" → options[] непорожній список унікальних непорожніх рядків.
    - key унікальний ГЛОБАЛЬНО в межах шаблону (attributes + variant_axes разом).
    - невалідно → TemplateError(422, <деталь>).
    """
    if not isinstance(schema, dict):
        raise TemplateError(HTTPStatus.UNPROCESSABLE_ENTITY, "template.schema_must_be_object")

    attributes = schema.get("attributes", [])
    variant_axes = schema.get("variant_axes", [])

    if not isinstance(attributes, list):
        raise TemplateError(HTTPStatus.UNPROCESSABLE_ENTITY, "template.attributes_must_be_list")
    if not isinstance(variant_axes, list):
        raise TemplateError(HTTPStatus.UNPROCESSABLE_ENTITY, "template.axes_must_be_list")

    seen_keys: set[str] = set()

    for field in [*attributes, *variant_axes]:
        if not isinstance(field, dict):
            raise TemplateError(HTTPStatus.UNPROCESSABLE_ENTITY, "template.field_must_be_object")

        key = field.get("key", "")
        if not isinstance(key, str) or not key:
            raise TemplateError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "template.key_required",
                key=key,
            )
        if not _KEY_RE.match(key):
            raise TemplateError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "template.key_format",
                key=key,
            )
        if key in seen_keys:
            raise TemplateError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "template.key_duplicate",
                key=key,
            )
        seen_keys.add(key)

        label = field.get("label", "")
        if not isinstance(label, str) or not label:
            raise TemplateError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "template.label_required",
                key=key,
            )

        ftype = field.get("type", "")
        if ftype not in _VALID_TYPES:
            raise TemplateError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "template.type_invalid",
                key=key,
                ftype=ftype,
            )

        if ftype == "enum":
            options = field.get("options", [])
            if not isinstance(options, list) or not options:
                raise TemplateError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "template.options_required",
                    key=key,
                )
            if any(not isinstance(o, str) or not o for o in options):
                raise TemplateError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "template.options_must_be_strings",
                    key=key,
                )
            if len(options) != len(set(options)):
                raise TemplateError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "template.options_must_be_unique",
                    key=key,
                )


def _all_field_types(schema: dict) -> dict[str, str]:
    """key → type для всіх полів (attributes + variant_axes разом)."""
    result: dict[str, str] = {}
    for f in [*schema.get("attributes", []), *schema.get("variant_axes", [])]:
        result[f["key"]] = f["type"]
    return result


async def count_products_for_template(session: AsyncSession, template_id: int) -> int:
    """Кількість товарів, що посилаються на шаблон (включно з archived).

    Архівний товар досі посилається на поля схеми — видалення/зміна осі
    зламає і його, тому враховуємо без фільтра по archived.
    """
    count = await session.scalar(
        select(func.count(Product.id)).where(Product.template_id == template_id)
    )
    return count or 0


async def _load_own_template(
    session: AsyncSession, membership: Membership, template_id: int
) -> ProductTemplate:
    """Завантажити шаблон з перевіркою власності.

    shop_id IS NULL → 403 (базовий, read-only).
    shop_id != membership.shop_id → 404 (не світимо існування чужого).
    """
    template = await session.get(ProductTemplate, template_id)
    if template is None:
        raise TemplateError(HTTPStatus.NOT_FOUND, "catalog.template_not_found")
    if template.shop_id is None:
        raise TemplateError(HTTPStatus.FORBIDDEN, "template.base_immutable")
    if template.shop_id != membership.shop_id:
        raise TemplateError(HTTPStatus.NOT_FOUND, "catalog.template_not_found")
    return template


async def create_custom_template(
    session: AsyncSession,
    membership: Membership,
    name: str,
    field_schema: dict,
) -> ProductTemplate:
    validate_field_schema(field_schema)
    template = ProductTemplate(
        shop_id=membership.shop_id,
        code=TemplateCode.custom,
        name=name,
        field_schema=field_schema,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def patch_custom_template(
    session: AsyncSession,
    membership: Membership,
    template_id: int,
    name: str | None,
    field_schema: dict | None,
) -> ProductTemplate:
    template = await _load_own_template(session, membership, template_id)

    if field_schema is not None:
        validate_field_schema(field_schema)

        product_count = await count_products_for_template(session, template_id)
        if product_count > 0:
            old_types = _all_field_types(template.field_schema)
            new_types = _all_field_types(field_schema)

            for key in old_types:
                if key not in new_types:
                    raise TemplateError(HTTPStatus.CONFLICT, "template.field_in_use", key=key)
                if old_types[key] != new_types[key]:
                    raise TemplateError(
                        HTTPStatus.CONFLICT, "template.field_type_locked", key=key
                    )
            # нові ключі (є в new_types, нема в old_types) → ОК

        template.field_schema = field_schema

    if name is not None:
        template.name = name

    await session.commit()
    await session.refresh(template)
    return template


async def delete_custom_template(
    session: AsyncSession,
    membership: Membership,
    template_id: int,
) -> None:
    template = await _load_own_template(session, membership, template_id)

    product_count = await count_products_for_template(session, template_id)
    if product_count > 0:
        raise TemplateError(HTTPStatus.CONFLICT, "template.delete_blocked")

    await session.delete(template)
    await session.commit()
