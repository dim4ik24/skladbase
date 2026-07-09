"""custom roles

Revision ID: b943d7af268f
Revises: 7aeff9226ecc
Create Date: 2026-07-09 00:00:00.000000

Membership permissions move from 6 can_*-columns per person to a per-shop
Role entity, assigned via memberships.role_id (фіча 3b, кастомні ролі).
Chained in one revision: add roles table -> add nullable role_id -> backfill
-> alter role_id NOT NULL. Backfill logic:
  - кожен shop_id отримує дві системні ролі: "Власник" (усі can_*=True) і
    "Менеджер" (поточні дефолти Membership — теж усі True).
  - role='owner' -> "Власник" свого магазину.
  - role='manager' з усіма 6 колонками True (дефолт, чекбокси не чіпали) ->
    "Менеджер" свого магазину.
  - role='manager' з БУДЬ-ЯКОЮ колонкою != True (хтось міняв чекбокси через
    старий PATCH /permissions) -> окрема "Індивідуальна (...)" роль з ЙОГО
    точними значеннями — нічиї фактичні права тихо не міняються.
The 6 can_*-колонки на Membership цією міграцією НЕ чіпаються (лишаються
для безпечного відкату) — застосунок просто перестає їх читати.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = 'b943d7af268f'
down_revision: str | Sequence[str] | None = '7aeff9226ecc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERM_COLS = [
    'can_view_inventory',
    'can_edit_products',
    'can_manage_reservations',
    'can_manage_stock',
    'can_view_finance',
    'can_manage_billing',
]

_OWNER_ROLE_NAME = 'Власник'
_MANAGER_ROLE_NAME = 'Менеджер'

# Ad-hoc проекції (не app.models — той самий інцидент-driven принцип, що і в
# 722d93030623/c4d8f1a29b3e: міграція має лишатись коректним знімком СХЕМИ
# на цей момент, незалежно від того, як зміниться модель в майбутньому).
memberships = sa.table(
    "memberships",
    sa.column("id", sa.Integer),
    sa.column("shop_id", sa.Integer),
    sa.column("tg_id", sa.BigInteger),
    sa.column("display_name", sa.String),
    sa.column("role", sa.String),
    sa.column("role_id", sa.Integer),
    *(sa.column(col, sa.Boolean) for col in _PERM_COLS),
)
roles = sa.table(
    "roles",
    sa.column("id", sa.Integer),
    sa.column("shop_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("is_system", sa.Boolean),
    sa.column("created_at", sa.DateTime),
    *(sa.column(col, sa.Boolean) for col in _PERM_COLS),
)


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("can_view_inventory", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("can_edit_products", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("can_manage_reservations", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("can_manage_stock", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("can_view_finance", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("can_manage_billing", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_id", "name", name="uq_role_shop_name"),
    )
    with op.batch_alter_table("roles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_roles_shop_id"), ["shop_id"], unique=False)

    # Phase 1: role_id nullable — рядки memberships ще без ролі до бекфілу нижче.
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.add_column(sa.Column("role_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_memberships_role_id", "roles", ["role_id"], ["id"])
        batch_op.create_index(batch_op.f("ix_memberships_role_id"), ["role_id"], unique=False)

    # Phase 2: бекфіл — системні ролі на кожен магазин + призначення.
    conn = op.get_bind()
    now = datetime.now(UTC)

    shop_ids = [row[0] for row in conn.execute(sa.select(memberships.c.shop_id).distinct())]

    for shop_id in shop_ids:
        # sa.table() ad-hoc проекції не несуть PK-метадані — .inserted_primary_key
        # на них порожній (IndexError). .returning(roles.c.id) явний і портативний
        # (SQLite 3.35+/Postgres — обидва підтримують RETURNING).
        owner_role_id = conn.execute(
            roles.insert()
            .values(
                shop_id=shop_id, name=_OWNER_ROLE_NAME, is_system=True, created_at=now,
                **dict.fromkeys(_PERM_COLS, True),
            )
            .returning(roles.c.id)
        ).scalar_one()
        manager_role_id = conn.execute(
            roles.insert()
            .values(
                shop_id=shop_id, name=_MANAGER_ROLE_NAME, is_system=True, created_at=now,
                **dict.fromkeys(_PERM_COLS, True),
            )
            .returning(roles.c.id)
        ).scalar_one()

        conn.execute(
            memberships.update()
            .where(
                memberships.c.shop_id == shop_id,
                # role — нативний Postgres ENUM (memberrole) у проді, plain TEXT
                # на sqlite (CI/dev). Каст КОЛОНКИ до Text прибирає розбіжність
                # на обох базах (той самий прийом, що 722d93030623/c4d8f1a29b3e).
                sa.cast(memberships.c.role, sa.Text) == "owner",
            )
            .values(role_id=owner_role_id)
        )

        is_default_perms = sa.and_(*(memberships.c[col].is_(True) for col in _PERM_COLS))

        conn.execute(
            memberships.update()
            .where(
                memberships.c.shop_id == shop_id,
                sa.cast(memberships.c.role, sa.Text) == "manager",
                is_default_perms,
            )
            .values(role_id=manager_role_id)
        )

        custom_rows = conn.execute(
            sa.select(
                memberships.c.id, memberships.c.tg_id, memberships.c.display_name,
                *(memberships.c[col] for col in _PERM_COLS),
            ).where(
                memberships.c.shop_id == shop_id,
                sa.cast(memberships.c.role, sa.Text) == "manager",
                sa.not_(is_default_perms),
            )
        ).all()

        used_names: set[str] = set()
        for row in custom_rows:
            base = (row.display_name or str(row.tg_id))[:20]
            name = f"Індивідуальна ({base})"
            if name in used_names:
                # Колізія (два менеджери магазину truncate-яться в однакове
                # ім'я) — UniqueConstraint(shop_id, name) інакше впаде.
                name = f"Індивідуальна ({base}) #{row.id}"
            used_names.add(name)

            individual_role_id = conn.execute(
                roles.insert()
                .values(
                    shop_id=shop_id, name=name, is_system=False, created_at=now,
                    **{col: getattr(row, col) for col in _PERM_COLS},
                )
                .returning(roles.c.id)
            ).scalar_one()

            conn.execute(
                memberships.update()
                .where(memberships.c.id == row.id)
                .values(role_id=individual_role_id)
            )

    # Phase 3: усі рядки мають role_id — тепер безпечно заборонити NULL.
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.alter_column("role_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # can_*-колонки Membership ніколи не чіпались — даунгрейд безпечний для
    # НИХ, але призначення ролей (роль -> хто яку мав) не відновлюється:
    # той самий intentionally non-symmetric підхід, що й у c4d8f1a29b3e.
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_memberships_role_id"))
        batch_op.drop_constraint("fk_memberships_role_id", type_="foreignkey")
        batch_op.drop_column("role_id")
    op.drop_table("roles")
