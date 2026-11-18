"""add sessions and refresh token rotation

Сессии устройств и одноразовые refresh-токены (US-25).

Refresh-токены из US-03 не привязаны к устройству, поэтому удаляются:
пользователи войдут заново. Без этого session_id нельзя сделать NOT NULL.
revoked_at у токена больше не нужен — отзывается сессия целиком.

Revision ID: e369e591d1d5
Revises: b3c5e1f7a2d4
"""

import sqlalchemy as sa
from alembic import op

revision = "e369e591d1d5"
down_revision = "b3c5e1f7a2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(
        "ix_sessions_user_id_device_id", "sessions", ["user_id", "device_id"], unique=False
    )

    # Старые токены без устройства отзываются удалением.
    op.execute("DELETE FROM refresh_tokens")

    op.add_column("refresh_tokens", sa.Column("session_id", sa.Uuid(), nullable=False))
    op.add_column("refresh_tokens", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_refresh_tokens_session_id_sessions"),
        "refresh_tokens",
        "sessions",
        ["session_id"],
        ["id"],
    )
    op.drop_column("refresh_tokens", "revoked_at")


def downgrade() -> None:
    # Отозванные сессии при откате не восстановить: токены используемых
    # и отозванных сессий помечаются отозванными, действующие остаются рабочими.
    op.add_column(
        "refresh_tokens",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE refresh_tokens AS t
        SET revoked_at = COALESCE(t.used_at, s.revoked_at)
        FROM sessions AS s
        WHERE s.id = t.session_id AND (t.used_at IS NOT NULL OR s.revoked_at IS NOT NULL)
        """
    )
    op.drop_constraint(
        op.f("fk_refresh_tokens_session_id_sessions"), "refresh_tokens", type_="foreignkey"
    )
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "used_at")
    op.drop_column("refresh_tokens", "session_id")
    op.drop_index("ix_sessions_user_id_device_id", table_name="sessions")
    op.drop_table("sessions")
