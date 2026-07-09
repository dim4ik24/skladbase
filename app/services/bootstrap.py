"""
Перший вхід нового tg_id у систему (фіча 1 з ROADMAP, Стадія 1) +
приєднання по deep-link інвайту (Стадія 2а) + multi-shop (Стадія 3а):
одна людина може мати Membership у кількох магазинах.

Створює Shop + Membership(owner), гарантує наявність системних шаблонів і
тарифів, засіює демо-каталог і стартує 7-денний тріал. Викликається лише
з `deps.resolve_membership`, коли для tg_id з валідованого initData ще
нема ЖОДНОГО Membership (bootstrap: перший вхід) АБО коли є валідний
invite-токен (start_param) — тоді existing-юзер може приєднатись до ЩЕ
ОДНОГО магазину, не втрачаючи наявні.

Якщо при вході переданий валідний invite-токен (з підписаного Telegram
`start_param`, НІКОЛИ з довільного параметра клієнта) — замість нового
магазину створюється Membership(manager) У МАГАЗИНІ ІНВАЙТУ. shop_id
береться ТІЛЬКИ з Invite, знайденого в БД за токеном (CLAUDE.md,
інваріант №1).

"Перший" Membership (коли фронт не передав X-Shop-Id, деталі — deps.py)
визначається детерміновано: найменший id. Той самий порядок скрізь тут,
щоб `resolve_membership` і `bootstrap_shop` завжди узгоджувались, яке
членство "дефолтне".

Ідемпотентність під конкурентним входом: кілька паралельних запитів з
тим самим tg_id (типово кілька запитів TMA одразу при відкритті) можуть
одночасно дійти сюди, не побачивши чужого ще не закомітченого Membership.
Для нового магазину всі намагаються створити Shop з однаковим slug
`shop-{tg_id}`; для приєднання по інвайту — усі намагаються вставити
Membership з тим самим (shop_id, tg_id) — саме ця пара унікальна
(UniqueConstraint), НЕ голий tg_id (multi-shop). В обох випадках
переможець гонки комітить, решта ловлять `IntegrityError` на
unique-констрейнті при `flush()`, відкочуються і повертають вже
створений переможцем Membership — той самий прийом, що
`create_website_order` використовує для замовлень.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Invite, MemberRole, Membership, Role, Shop, ShopStatus
from app.security.initdata import TelegramUser
from app.seed import seed_demo_catalog, seed_plans, seed_system_templates
from app.services.subscriptions import SubscriptionService

_INVITE_PREFIX = "invite_"
OWNER_ROLE_NAME = "Власник"
MANAGER_ROLE_NAME = "Менеджер"


def parse_invite_token(start_param: str | None) -> str | None:
    """`startapp=invite_<token>` -> `<token>`. Все інше (нема параметра,
    чужий/майбутній формат deep-link) -> None, як "не інвайт"."""
    if start_param and start_param.startswith(_INVITE_PREFIX):
        return start_param[len(_INVITE_PREFIX):]
    return None


async def _find_membership(session: AsyncSession, tg_id: int) -> Membership | None:
    """"Дефолтне" членство цього tg_id (multi-shop: може бути не єдиним) —
    найменший id, той самий порядок, що й `resolve_membership` (deps.py).

    role_ref eager-loaded — повернене звідси Membership може дійти аж до
    `_check_permission` (сама sync-функція, лінивий доступ там впав би на
    async greenlet boundary)."""
    return await session.scalar(
        select(Membership)
        .options(selectinload(Membership.role_ref))
        .where(Membership.tg_id == tg_id)
        .order_by(Membership.id)
        .limit(1)
    )


async def _find_membership_in_shop(
    session: AsyncSession, tg_id: int, shop_id: int
) -> Membership | None:
    return await session.scalar(
        select(Membership)
        .options(selectinload(Membership.role_ref))
        .where(Membership.tg_id == tg_id, Membership.shop_id == shop_id)
    )


async def _get_system_role(session: AsyncSession, shop_id: int, name: str) -> Role:
    role = await session.scalar(
        select(Role).where(Role.shop_id == shop_id, Role.name == name, Role.is_system.is_(True))
    )
    if role is None:
        raise RuntimeError(f"system role {name!r} missing for shop {shop_id}")
    return role


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
    manager_role = await _get_system_role(session, invite.shop_id, MANAGER_ROLE_NAME)
    membership = Membership(
        shop_id=invite.shop_id,
        tg_id=user.id,
        display_name=user.first_name or None,
        role=MemberRole.manager,
        role_ref=manager_role,
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
) -> tuple[Membership, str | None]:
    existing = await _find_membership(session, user.id)
    invite_token = parse_invite_token(start_param)

    if existing is not None:
        return await _join_existing_member(session, user, existing, invite_token)

    invite = await _find_active_invite(session, invite_token) if invite_token else None
    if invite is not None:
        return await _join_via_invite(session, user, invite)

    await seed_system_templates(session)
    await seed_plans(session)

    shop_name = f"Магазин {user.first_name}".strip() or "Мій магазин"
    shop = Shop(owner_tg_id=user.id, name=shop_name, slug=f"shop-{user.id}")
    owner_role = Role(shop=shop, name=OWNER_ROLE_NAME, is_system=True)
    manager_role = Role(shop=shop, name=MANAGER_ROLE_NAME, is_system=True)
    membership = Membership(
        shop=shop,
        tg_id=user.id,
        display_name=user.first_name or None,
        role=MemberRole.owner,
        role_ref=owner_role,
    )
    session.add_all([shop, owner_role, manager_role, membership])

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
