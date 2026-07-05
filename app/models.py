"""
SkladBase — повна схема БД (SQLAlchemy 2.0).

Принципи:
  * Multi-tenant: КОЖНА орієнтована на дані таблиця несе shop_id.
    Ізоляція робиться на рівні запиту (див. tenant-залежність нижче файлу),
    жоден запит до товарів/складу не йде без WHERE shop_id = :current_shop.
  * Залишок/резерв/low-stock живуть на рівні ВАРІАНТА, не товару.
  * JSON-поля (attributes / limits / schema) портативні: на SQLite це JSON,
    на Postgres краще замінити на JSONB (нижче є примітка).
  * Усі статуси — enum, без "магічних" рядків.

Перехід SQLite -> Postgres:
  замінити `JSON` на `from sqlalchemy.dialects.postgresql import JSONB`
  для полів attributes/limits/schema/raw і повісити GIN-індекс де треба.
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_aware_utc(value: datetime) -> datetime:
    """SQLite не зберігає tzinfo на `DateTime(timezone=True)` — після
    перечитування з БД значення повертається naive. Postgres цього не робить,
    тож тут лише підстраховка для порівнянь типу `trial_ends_at > utcnow()`.
    Експортується — той самий захист потрібен у `services/subscriptions.py`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
#  Enums                                                                       #
# --------------------------------------------------------------------------- #
class ShopStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"      # заблокований (несплата / порушення)


class MemberRole(str, enum.Enum):
    owner = "owner"              # бачить усе, включно з фінансами
    manager = "manager"         # резерв + замовлення, БЕЗ фінансів


class TemplateCode(str, enum.Enum):
    clothing = "clothing"
    shoes = "shoes"
    cosmetics = "cosmetics"
    toys = "toys"               # фігурки / іграшки
    generic = "generic"
    custom = "custom"


class ReservationStatus(str, enum.Enum):
    active = "active"
    released = "released"        # знято (вручну або по expiry)
    fulfilled = "fulfilled"      # викуплено -> стало продажем
    shipped = "shipped"          # відправлено (Нова пошта тощо) -> чекає pick_up/not_picked_up


class ReservationSource(str, enum.Enum):
    manual = "manual"           # менеджер відклав
    website = "website"         # замовлення з сайту
    app = "app"


class OrderSource(str, enum.Enum):
    website = "website"
    app = "app"
    manual = "manual"


class OrderStatus(str, enum.Enum):
    pending = "pending"          # створено, чекає підтвердження/оплати
    confirmed = "confirmed"      # підтверджено власником
    fulfilled = "fulfilled"      # видано/відправлено -> списано зі складу
    canceled = "canceled"


class MovementType(str, enum.Enum):
    sale = "sale"               # -on_hand
    restock = "restock"         # +on_hand
    reserve = "reserve"         # +reserved
    release = "release"         # -reserved
    adjustment = "adjustment"   # ручна корекція
    ret = "return"              # повернення (+on_hand)


class SubStatus(str, enum.Enum):
    trial = "trial"
    active = "active"
    past_due = "past_due"        # авто-продовження не пройшло, грейс-період
    canceled = "canceled"        # auto_renew=False, доживає до period_end
    expired = "expired"          # доступ read-only


class SubProvider(str, enum.Enum):
    stars = "stars"             # Telegram Stars (нативне авто-продовження)
    card = "card"               # WayForPay/Fondy/LiqPay (токен, авто-списання)
    crypto = "crypto"           # NOWPayments (разово, без авто-списання)


class SubPeriod(str, enum.Enum):
    month = "month"
    year = "year"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class PromoType(str, enum.Enum):
    free_period = "free_period"  # value = к-сть днів безкоштовно
    percent = "percent"          # value = % знижки на першу оплату


# --------------------------------------------------------------------------- #
#  Tenancy + ролі                                                             #
# --------------------------------------------------------------------------- #
class Shop(Base):
    """Tenant. Один інста-магазин = один Shop."""
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)  # для публічного каталогу /c/{slug}

    # --- Брендування (фіча 2): "це моя власна апка" ---
    logo_url: Mapped[str | None] = mapped_column(String(500))
    accent_color: Mapped[str] = mapped_column(String(7), default="#2E7D32")  # hex
    public_catalog_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Website API (Стадія 4): server-to-server ключ для /api/website/* ---
    website_url: Mapped[str | None] = mapped_column(String(500))
    api_key_encrypted: Mapped[str | None] = mapped_column(String(500))  # AES-256-GCM, plaintext не зберігаємо
    api_key_prefix: Mapped[str | None] = mapped_column(String(8), index=True)  # для швидкого пошуку Shop за ключем

    # --- Вихідний вебхук на сайт при зміні залишків (Стадія 4b) ---
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(String(500))  # AES-256-GCM

    # --- Нова Пошта: трекінг відправлень (Фіча B1) ---
    np_api_key_encrypted: Mapped[str | None] = mapped_column(String(500))  # AES-256-GCM, plaintext не зберігаємо

    status: Mapped[ShopStatus] = mapped_column(SAEnum(ShopStatus), default=ShopStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["Membership"]] = relationship(back_populates="shop", cascade="all, delete-orphan")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="shop", uselist=False)


class Membership(Base):
    """Хто має доступ до магазину і з якою роллю (фіча 3)."""
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("shop_id", "tg_id", name="uq_membership_shop_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[MemberRole] = mapped_column(SAEnum(MemberRole), default=MemberRole.manager)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Granular permissions (Stage 1). All default to True so existing members lose no access.
    # owner always has all permissions via require_permission owner-override (role check, not column).
    can_view_inventory: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit_products: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_reservations: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    can_view_finance: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_billing: Mapped[bool] = mapped_column(Boolean, default=True)

    shop: Mapped["Shop"] = relationship(back_populates="members")


class Invite(Base):
    """Deep-link запрошення в команду (Стадія 2а, t.me/<bot>?startapp=invite_<token>).

    Багаторазове: кожен, хто перейде за посиланням до expires_at (48h від
    створення) і revoked_at IS NULL, приєднається як manager. shop_id при
    приєднанні береться ТІЛЬКИ звідси, ніколи з параметрів клієнта
    (CLAUDE.md, інваріант №1)."""
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_tg_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    shop: Mapped["Shop"] = relationship()

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and ensure_aware_utc(self.expires_at) > utcnow()


# --------------------------------------------------------------------------- #
#  Каталог: шаблони -> товари -> варіанти                                     #
# --------------------------------------------------------------------------- #
class ProductTemplate(Base):
    """
    Шаблон полів товару (фіча 6).
    shop_id IS NULL  -> системний шаблон (одяг/взуття/косметика/іграшки).
    shop_id IS NOT NULL -> кастомний шаблон конкретного магазину.

    `field_schema` приклад для одягу:
      {
        "attributes": [
          {"key": "material", "label": "Матеріал", "type": "string"}
        ],
        "variant_axes": [
          {"key": "size",  "label": "Розмір", "type": "enum",
           "options": ["XS","S","M","L","XL","XXL"]},
          {"key": "color", "label": "Колір", "type": "string"}
        ]
      }
    variant_axes -> по яких полях розмножуються варіанти (розмір×колір).
    attributes  -> загальні поля товару (не множать склад).
    """
    __tablename__ = "product_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    code: Mapped[TemplateCode] = mapped_column(SAEnum(TemplateCode), default=TemplateCode.generic)
    name: Mapped[str] = mapped_column(String(80))
    field_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    """Картка товару (parent). Реальні одиниці складу — у Variant."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("product_templates.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)   # значення для template.attributes
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)  # засіяні товари (фіча 1)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    variants: Mapped[list["Variant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    photos: Mapped[list["ProductPhoto"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class Variant(Base):
    """
    Конкретна складська одиниця: футболка / M / чорна.
    Для простих товарів (фігурка) — один варіант, у UI прихований.
    available = on_hand - reserved.
    """
    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("shop_id", "sku", name="uq_variant_shop_sku"),
        Index("ix_variant_lowstock", "shop_id", "low_stock_notified_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)  # денорм. для ізоляції
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)

    sku: Mapped[str | None] = mapped_column(String(64))
    axis_values: Mapped[dict] = mapped_column(JSON, default=dict)   # {"size":"M","color":"чорний"}
    photo_url: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=3)
    low_stock_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # для косметики: термін придатності -> окремий тип алерту
    expires_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped["Product"] = relationship(back_populates="variants")

    @hybrid_property
    def available(self) -> int:
        return self.on_hand - self.reserved

    @available.expression  # type: ignore[no-redef]
    def available(cls) -> int:
        return cls.on_hand - cls.reserved


# --------------------------------------------------------------------------- #
#  Галерея фото товару (F2)                                                   #
# --------------------------------------------------------------------------- #
class ProductPhoto(Base):
    """Одне фото в галереї товару. До 10 на товар (enforce в API-шарі).

    Tenant-ізоляція через product.shop_id — окремий shop_id не зберігаємо
    (JOIN через product достатній і не дублює дані).
    """
    __tablename__ = "product_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped["Product"] = relationship(back_populates="photos")


# --------------------------------------------------------------------------- #
#  Резерв + рух складу                                                        #
# --------------------------------------------------------------------------- #
class Reservation(Base):
    """Резерв (фіча 8). expires_at -> крон авто-знімає мертві резерви."""
    __tablename__ = "reservations"
    __table_args__ = (Index("ix_resv_active_expiry", "status", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))

    qty: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(200))
    customer_note: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[ReservationSource] = mapped_column(SAEnum(ReservationSource), default=ReservationSource.manual)
    status: Mapped[ReservationStatus] = mapped_column(SAEnum(ReservationStatus), default=ReservationStatus.active)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ttn: Mapped[str | None] = mapped_column(String(40))  # накладна Нової пошти тощо, опційна
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    np_status: Mapped[str | None] = mapped_column(String(120))  # останній текст статусу з трекінгу НП (фіча B1/B2)


class StockMovement(Base):
    """Журнал руху складу. Дає 'що продалось за тиждень' майже безкоштовно.

    Той самий журнал — джерело доходу (finance_summary): sale-рухи з
    price_at агрегуються в дохід, ret (поки не пишеться жодним кодом,
    фіча A) віднімається. reason/comment — лише для type=adjustment
    (списання з причиною); type=sale з fulfill()/write_off(sold) теж
    отримує price_at, але БЕЗ reason (це нормальний продаж, не списання)."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    type: Mapped[MovementType] = mapped_column(SAEnum(MovementType))
    delta: Mapped[int] = mapped_column(Integer)   # знакове: -3 продаж, +10 поповнення
    reason: Mapped[str | None] = mapped_column(String(40))  # sold/defect/correction/other — лише списання
    comment: Mapped[str | None] = mapped_column(Text)
    price_at: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # ціна за од. на момент руху (sale/ret)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# --------------------------------------------------------------------------- #
#  Замовлення (сайт + апка)                                                   #
# --------------------------------------------------------------------------- #
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("shop_id", "idempotency_key", name="uq_order_idem"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    source: Mapped[OrderSource] = mapped_column(SAEnum(OrderSource), default=OrderSource.app)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), default=OrderStatus.pending)

    external_ref: Mapped[str | None] = mapped_column(String(120))   # id з сайту
    idempotency_key: Mapped[str | None] = mapped_column(String(80))  # захист від подвійного POST
    customer_name: Mapped[str | None] = mapped_column(String(160))
    customer_contact: Mapped[str | None] = mapped_column(String(160))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="RESTRICT"))
    qty: Mapped[int] = mapped_column(Integer)
    price_at_order: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped["Order"] = relationship(back_populates="items")


# --------------------------------------------------------------------------- #
#  Білінг: плани / підписки / платежі / промокоди                            #
# --------------------------------------------------------------------------- #
class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)   # free / basic / pro
    name: Mapped[str] = mapped_column(String(80))
    period: Mapped[SubPeriod] = mapped_column(SAEnum(SubPeriod), default=SubPeriod.month)
    price_uah: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    price_stars: Mapped[int] = mapped_column(Integer, default=0)   # ціна в Telegram Stars
    limits: Mapped[dict] = mapped_column(JSON, default=dict)        # {"max_products":200,"photos":true}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    """Одна на магазин. Провайдер-агностична стейт-машина (логіка у subscriptions.py)."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), unique=True, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"))

    status: Mapped[SubStatus] = mapped_column(SAEnum(SubStatus), default=SubStatus.trial)
    provider: Mapped[SubProvider | None] = mapped_column(SAEnum(SubProvider))
    period: Mapped[SubPeriod] = mapped_column(SAEnum(SubPeriod), default=SubPeriod.month)

    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    is_comp: Mapped[bool] = mapped_column(Boolean, default=False)   # подарована (промокод) — не платна

    external_sub_id: Mapped[str | None] = mapped_column(String(120))  # telegram_payment_charge_id / wfp order / np id
    renewal_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    shop: Mapped["Shop"] = relationship(back_populates="subscription")

    @property
    def is_writable(self) -> bool:
        """Чи може магазин редагувати дані (не read-only).

        Free-стан (expired trial / expired sub / no paid plan) → True: магазин
        залишається робочим, обмеження накладають enforce-функції каталогу, а не
        цей прапор. Стіна прибрана (FREE_PLAN_SPEC §8).
        """
        if self.status in (SubStatus.active, SubStatus.canceled, SubStatus.past_due, SubStatus.expired):
            return True
        if (
            self.status == SubStatus.trial
            and self.trial_ends_at
            and ensure_aware_utc(self.trial_ends_at) > utcnow()
        ):
            return True
        # Expired trial (trial_ends_at у минулому) — теж free, теж writable.
        if self.status == SubStatus.trial:
            return True
        return False


class Payment(Base):
    """Леджер усіх платежів (для звітності й розслідувань)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"))
    provider: Mapped[SubProvider] = mapped_column(SAEnum(SubProvider))
    status: Mapped[PaymentStatus] = mapped_column(SAEnum(PaymentStatus), default=PaymentStatus.pending)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="UAH")  # UAH / XTR / USDT
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    external_id: Mapped[str | None] = mapped_column(String(160))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)            # сирий payload вебхука
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    type: Mapped[PromoType] = mapped_column(SAEnum(PromoType))
    value: Mapped[int] = mapped_column(Integer)            # днів (free_period) або % (percent)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"))
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def is_redeemable(self) -> bool:
        if not self.is_active or self.used_count >= self.max_uses:
            return False
        if self.expires_at and ensure_aware_utc(self.expires_at) < utcnow():
            return False
        return True


class PromoRedemption(Base):
    """Один промокод — одне погашення на магазин (анти-абʼюз)."""
    __tablename__ = "promo_redemptions"
    __table_args__ = (UniqueConstraint("promo_code_id", "shop_id", name="uq_promo_once_per_shop"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- #
#  Tenant-ізоляція: приклад залежності FastAPI                                #
# --------------------------------------------------------------------------- #
# Усі запити до товарів/складу мають проходити через resolve_shop, який
# дістає shop_id з валідованого Telegram initData, а не з тіла запиту.
# Ніколи не довіряй shop_id, що прийшов від клієнта.
#
#   async def resolve_membership(init_data: str, session) -> Membership:
#       tg_id = validate_init_data(init_data)        # HMAC-SHA256 перевірка
#       m = await session.scalar(
#           select(Membership).where(Membership.tg_id == tg_id)
#       )
#       if not m:
#           raise HTTPException(403, "no shop access")
#       return m
#
#   # потім у кожному запиті: .where(Variant.shop_id == m.shop_id)
