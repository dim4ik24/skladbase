"""promo type plan grant

Revision ID: 8d3e46c65646
Revises: eea15fd1696f
Create Date: 2026-07-12 09:00:13.076098

Додає PromoType.plan_grant (адмін видає конкретний платний план на N днів
безкоштовно — фіча "промокоди"). Розширення НАЯВНОГО PromoCode/PromoType
(стадія 5a), не нова таблиця: `plan_id` (nullable FK на plans) уже є в схемі,
просто досі не використовувався жодним типом промокоду; `value` (дні) так
само підходить без змін.

PromoType — SAEnum(native_enum=True, дефолт) -> нативний Postgres ENUM
(`promotype`) у проді, plain VARCHAR без CHECK на SQLite (звірено на
dev.db: `type VARCHAR(11) NOT NULL`, без constraint). Тобто:
  - SQLite (dev/CI): DDL не потрібен, колонка й так приймає будь-який рядок.
  - Postgres: `ALTER TYPE ... ADD VALUE` — до PG12 взагалі не можна
    виконати всередині транзакції, з PG12+ можна ДОДАТИ в транзакції, але
    НЕ МОЖНА використати нове значення в тій самій транзакції. Alembic
    оборачує кожну міграцію в транзакцію за замовчуванням, тож ADD VALUE
    йде через `autocommit_block()` (офіційно рекомендований Alembic-патерн
    саме для цього випадку) — інакше впаде або на старих PG, або на
    спробі одразу ж записати рядок з новим значенням.

downgrade() навмисно no-op: Postgres не підтримує видалення значення з
ENUM (той самий несиметричний підхід, що вже є в b943d7af268f/c4d8f1a29b3e
для необоротних кроків) — рядки з plan_grant, якщо встигли з'явитись,
довелось би чистити вручну перед даунгрейдом.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '8d3e46c65646'
down_revision: str | Sequence[str] | None = 'eea15fd1696f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE promotype ADD VALUE IF NOT EXISTS 'plan_grant'")
    # SQLite: колонка type — VARCHAR без CHECK, нове значення вже прийнятне.


def downgrade() -> None:
    # Postgres не вміє DROP VALUE з ENUM — необоротний крок.
    pass
