"""allow draft content without dates

Черновик акции или события можно сохранить без сроков (US-17). Опубликованная
и снятая с публикации запись — всегда со сроками: это гарантирует CHECK.

Revision ID: 0f658e8bab94
Revises: f98e66cf65cb
"""

import sqlalchemy as sa
from alembic import op

revision = "0f658e8bab94"
down_revision = "f98e66cf65cb"
branch_labels = None
depends_on = None

TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.alter_column("events", "starts_at", existing_type=TIMESTAMPTZ, nullable=True)
    op.alter_column("promotions", "starts_at", existing_type=TIMESTAMPTZ, nullable=True)
    op.alter_column("promotions", "ends_at", existing_type=TIMESTAMPTZ, nullable=True)
    op.create_check_constraint(
        "published_has_starts_at",
        "events",
        "status = 'draft' OR starts_at IS NOT NULL",
    )
    op.create_check_constraint(
        "published_has_dates",
        "promotions",
        "status = 'draft' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("published_has_dates", "promotions", type_="check")
    op.drop_constraint("published_has_starts_at", "events", type_="check")
    # Пустые сроки бывают только у черновиков, клиенты их не видят: подставляем
    # дату создания, чтобы откат не удалял черновики.
    op.execute("UPDATE events SET starts_at = created_at WHERE starts_at IS NULL")
    op.execute("UPDATE promotions SET starts_at = created_at WHERE starts_at IS NULL")
    op.execute("UPDATE promotions SET ends_at = starts_at WHERE ends_at IS NULL")
    op.alter_column("promotions", "ends_at", existing_type=TIMESTAMPTZ, nullable=False)
    op.alter_column("promotions", "starts_at", existing_type=TIMESTAMPTZ, nullable=False)
    op.alter_column("events", "starts_at", existing_type=TIMESTAMPTZ, nullable=False)
