"""seed default loyalty level

Начальный уровень, который получает новый бонусный счёт при регистрации (US-03).
Название и процент кешбэка — значения по умолчанию, бизнес меняет их через админку.

Revision ID: b3c5e1f7a2d4
Revises: a108a16aa1ae
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c5e1f7a2d4"
down_revision = "a108a16aa1ae"
branch_labels = None
depends_on = None

DEFAULT_LEVEL_ID = "00000000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO loyalty_levels
                (id, name, cashback_percent, threshold, effective_from, status)
            VALUES (CAST(:id AS uuid), 'Базовый', 3.00, 0, '2026-01-01T00:00:00+00:00', 'active')
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(id=DEFAULT_LEVEL_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM loyalty_levels WHERE id = CAST(:id AS uuid)").bindparams(
            id=DEFAULT_LEVEL_ID
        )
    )
