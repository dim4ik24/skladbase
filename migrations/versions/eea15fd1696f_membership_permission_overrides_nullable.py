"""membership permission overrides nullable

Revision ID: eea15fd1696f
Revises: b943d7af268f
Create Date: 2026-07-11 20:46:52.685785

Фіча 3c — індивідуальні override поверх ролі. Ці 6 can_*-колонок Membership
з фічі 3b (нульового читання, дефолт True скрізь) стають знову активними,
але з ІНШОЮ семантикою: NULL = "як у role_ref", true/false = явний виняток
для цієї людини (effective_permission() у app/deps.py).

Phase 1: nullable=True + server_default=None. server_default обов'язково
прибрати ТУТ (не лише Python-дефолт у моделі) — інакше сирий INSERT, що
пропускає ці колонки, і далі отримував би `1` від старого server_default,
а не NULL, і override був би невиразним від "явний True" (той самий клас
багів, що і a1b2c3d4e5f6, де ці колонки взагалі отримали server_default).
Phase 2: bulk UPDATE усіх рядків на NULL — не бекфіл-з-логікою (як
b943d7af268f), просто загальний скид: усі наявні члени команди зараз
"без override", ефективні права = права їхньої ролі (без змін для НИХ,
бо права вже читаються з role_ref, не з цих колонок).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'eea15fd1696f'
down_revision: str | Sequence[str] | None = 'b943d7af268f'
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

# Ad-hoc проекція — той самий принцип, що й у b943d7af268f: міграція має
# лишатись коректним знімком СХЕМИ на цей момент, незалежно від app.models.
memberships = sa.table(
    "memberships",
    sa.column("id", sa.Integer),
    *(sa.column(col, sa.Boolean) for col in _PERM_COLS),
)


def upgrade() -> None:
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        for col in _PERM_COLS:
            batch_op.alter_column(
                col,
                existing_type=sa.Boolean(),
                nullable=True,
                server_default=None,
            )

    op.execute(memberships.update().values(**dict.fromkeys(_PERM_COLS, None)))


def downgrade() -> None:
    # NULL -> True перед тим, як знову заборонити NULL (симетрично до
    # b943d7af268f: наявні override не відновлюються, лишень безпечний
    # дефолт, що відповідає старій "усі True" семантиці цих колонок).
    conn = op.get_bind()
    for col in _PERM_COLS:
        conn.execute(
            memberships.update()
            .where(memberships.c[col].is_(None))
            .values(**{col: True})
        )

    with op.batch_alter_table("memberships", schema=None) as batch_op:
        for col in _PERM_COLS:
            batch_op.alter_column(
                col,
                existing_type=sa.Boolean(),
                nullable=False,
                server_default='1',
            )
