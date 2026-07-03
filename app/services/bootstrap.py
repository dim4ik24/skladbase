"""
Приєднання по deep-link інвайту (Стадія 2а) + multi-shop (Стадія 3а):
одна людина може мати Membership у кількох магазинах.

Авто-створення магазину на першому вході ПРИБРАНО (shop lifecycle): якщо
для tg_id нема ЖОДНОГО Membership і нема валідного invite-токена, `bootstrap_shop`
повертає `(None, None)` — викликач (`deps.resolve_membership`) сам вирішує,
що з цим робити (404 "немає магазину"). Явне створення нового магазину —
`POST /api/shops` (app/api/shop.py, app/services/shops.py), окремий шлях,
доступний БУДЬ-ЯКОМУ tg_id з валідним initData (multi-shop: можна створити
ще один магазин, повторний виклик не дедуплікується).

Якщо при вході переданий валідний invite-токен (з підписаного Telegram
`start_param`, НІКОЛИ з довільного параметра клієнта) — існуючий АБО новий
(без власного магазину, але з валідним інвайтом) юзер отримує
Membership(manager) У МАГАЗИНІ ІНВАЙТУ. shop_id береться ТІЛЬКИ з Invite,
знайденого в БД за токеном (CLAUDE.md, інваріант №1).

"Перший" Membership (коли фронт не передав X-Shop-Id, деталі — deps.py)
визначається детерміновано: найменший id. Той самий порядок скрізь тут,
щоб `resolve_membership` і `bootstrap_shop` завжди узгоджувались, яке
членство "дефолтне".

Ідемпотентність приєднання по інвайту під конкурентним входом: кілька
паралельних запитів з тим самим tg_id можуть одночасно намагатись вставити
Membership з тим самим (shop_id, tg_id) — саме ця пара унікальна
(UniqueConstraint), НЕ голий tg_id (multi-shop). Переможець гонки комітить,
решта ловлять `IntegrityError` на unique-констрейнті при `flush()`,
відкочуються і повертають вже створений переможцем Membership.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invite, MemberRole, Membership, Shop, ShopStatus
from app.security.initdata import TelegramUser

_INVITE_PREFIX = "invite_"


def parse_invite_token(start_param: str | None) -> str | None:
    """`startapp=invite_<token>` -> `<token>`. Все інше (нема параметра,
    чужий/майбутній формат deep-link) -> None, як "не інвайт"."""
    if start_param and start_param.startswith(_INVITE_PREFIX):
        return start_param[len(_INVITE_PREFIX):]
    return None


async def _find_membership(session: AsyncSession, tg_id: int) -> Membership | None:
    """"Дефолтне" членство цього tg_id (multi-shop: може бути не єдиним) —
    найменший id, той самий порядок, що й `resolve_membership` (deps.py)."""
    return await session.scalar(
        select(Membership).where(Membership.tg_id == tg_id).order_by(Membership.id).limit(1)
    )


async def _find_membership_in_shop(
    session: AsyncSession, tg_id: int, shop_id: int
) -> Membership | None:
    return await session.scalar(
        select(Membership).where(Membership.tg_id == tg_id, Membership.shop_id == shop_id)
    )


async def _find_active_invite(session: AsyncSession, token: str) -> Invite | None:
    invite = await session.scalar(select(Invite).where(Invite.token == token))
    if invite is None or not invite.is_active:
        return None
    shop = await session.get(Shop, invite.shop_id)
    if shop is None or shop.status != ShopStatus.active:
        return None
    return invite


async def _join_via_invite(
    session: AsyncSession, user: TelegramUser, invite: Invite
) -> tuple[Membership, str]:
    membership = Membership(
        shop_id=invite.shop_id,
        tg_id=user.id,
        display_name=user.first_name or None,
        role=MemberRole.manager,
    )
    session.add(membership)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # Race — конкурентний запит з тим самим tg_id встиг вставити
        # Membership у ТОЙ САМИЙ shop_id першим (це і є unique-констрейнт,
        # що впав). Не можна відновлюватись через `_find_membership` (any
        # shop, multi-shop) — юзер міг мати ІНШІ, не пов'язані з цим
        # інвайтом, членства з меншим id, і рекавері підхопило б не те.
        existing = await _find_membership_in_shop(session, user.id, invite.shop_id)
        if existing is not None:
            return existing, "joined"
        raise

    await session.commit()
    return membership, "joined"


async def _join_existing_member(
    session: AsyncSession, user: TelegramUser, existing: Membership, invite_token: str | None
) -> tuple[Membership, str | None]:
    """Existing юзер (уже має хоча б одне Membership) з можливим invite-токеном.

    - без токена -> лишається на своєму дефолтному членстві.
    - валідний токен на магазин, де він УЖЕ є -> "already_in_shop", без дублю.
    - валідний токен на НОВИЙ для нього магазин -> ДОДАТКОВЕ Membership(manager),
      "joined" — і повертаємо САМЕ ЙОГО (юзер одразу опиняється в приєднаному
      магазині, а не лишається у старому контексті).
    - мертвий/чужий-формату токен -> "invite_invalid", свій магазин НЕ чіпаємо
      і новий НЕ створюємо (на відміну від зовсім нового юзера).
    """
    if invite_token is None:
        return existing, None

    invite = await _find_active_invite(session, invite_token)
    if invite is None:
        return existing, "invite_invalid"

    same_shop = await _find_membership_in_shop(session, user.id, invite.shop_id)
    if same_shop is not None:
        return same_shop, "already_in_shop"

    return await _join_via_invite(session, user, invite)


async def bootstrap_shop(
    session: AsyncSession, user: TelegramUser, start_param: str | None = None
) -> tuple[Membership | None, str | None]:
    """- existing membership (можливо з invite-токеном) -> `_join_existing_member`.
    - нема membership, є ВАЛІДНИЙ invite -> `_join_via_invite` (`joined`).
    - нема membership, нема валідного invite -> `(None, None)` — викликач
      (`resolve_membership`) сам вирішує, що з цим робити (404 no_shop)."""
    existing = await _find_membership(session, user.id)
    invite_token = parse_invite_token(start_param)

    if existing is not None:
        return await _join_existing_member(session, user, existing, invite_token)

    invite = await _find_active_invite(session, invite_token) if invite_token else None
    if invite is not None:
        return await _join_via_invite(session, user, invite)

    return None, None
