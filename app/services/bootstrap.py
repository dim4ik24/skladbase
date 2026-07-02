"""
Перший вхід нового tg_id у систему (фіча 1 з ROADMAP, Стадія 1) +
приєднання по deep-link інвайту (Стадія 2а).

Створює Shop + Membership(owner), гарантує наявність системних шаблонів і
тарифів, засіює демо-каталог і стартує 7-денний тріал. Викликається лише
з `deps.resolve_membership`, коли для tg_id з валідованого initData ще
нема Membership.

Якщо при першому вході переданий валідний invite-токен (з підписаного
Telegram `start_param`, НІКОЛИ з довільного параметра клієнта) — замість
нового магазину створюється Membership(manager) У МАГАЗИНІ ІНВАЙТУ.
shop_id береться ТІЛЬКИ з Invite, знайденого в БД за токеном (CLAUDE.md,
інваріант №1).

Ідемпотентність під конкурентним першим входом: кілька паралельних запитів
з тим самим tg_id (типово кілька запитів TMA одразу при відкритті) можуть
одночасно дійти сюди, не побачивши чужого ще не закомітченого Membership.
Для нового магазину всі намагаються створити Shop з однаковим slug
`shop-{tg_id}`; для приєднання по інвайту — усі намагаються вставити
Membership з тим самим (shop_id, tg_id). В обох випадках переможець гонки
комітить, решта ловлять `IntegrityError` на unique-констрейнті при
`flush()`, відкочуються і повертають вже створений переможцем Membership —
той самий прийом, що `create_website_order` використовує для замовлень.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invite, MemberRole, Membership, Shop, ShopStatus
from app.security.initdata import TelegramUser
from app.seed import seed_demo_catalog, seed_plans, seed_system_templates
from app.services.subscriptions import SubscriptionService

_INVITE_PREFIX = "invite_"


def parse_invite_token(start_param: str | None) -> str | None:
    """`startapp=invite_<token>` -> `<token>`. Все інше (нема параметра,
    чужий/майбутній формат deep-link) -> None, як "не інвайт"."""
    if start_param and start_param.startswith(_INVITE_PREFIX):
        return start_param[len(_INVITE_PREFIX):]
    return None


async def _find_membership(session: AsyncSession, tg_id: int) -> Membership | None:
    return await session.scalar(select(Membership).where(Membership.tg_id == tg_id))


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
        existing = await _find_membership(session, user.id)
        if existing is not None:
            return existing, "joined"
        raise

    await session.commit()
    return membership, "joined"


async def bootstrap_shop(
    session: AsyncSession, user: TelegramUser, start_param: str | None = None
) -> tuple[Membership, str | None]:
    existing = await _find_membership(session, user.id)
    if existing is not None:
        return existing, None

    invite_token = parse_invite_token(start_param)
    invite = await _find_active_invite(session, invite_token) if invite_token else None
    if invite is not None:
        return await _join_via_invite(session, user, invite)

    await seed_system_templates(session)
    await seed_plans(session)

    shop_name = f"Магазин {user.first_name}".strip() or "Мій магазин"
    shop = Shop(owner_tg_id=user.id, name=shop_name, slug=f"shop-{user.id}")
    membership = Membership(
        shop=shop,
        tg_id=user.id,
        display_name=user.first_name or None,
        role=MemberRole.owner,
    )
    session.add_all([shop, membership])

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await _find_membership(session, user.id)
        if existing is not None:
            return existing, None
        raise

    await seed_demo_catalog(session, shop)
    await SubscriptionService(session).start_trial(shop)

    await session.commit()
    invite_status = "invite_invalid" if invite_token is not None else None
    return membership, invite_status
