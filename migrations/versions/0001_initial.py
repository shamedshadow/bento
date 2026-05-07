"""initial — users, magic_links, sessions

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("primary_metric", sa.String(), nullable=False),
        sa.Column("daily_target_primary", sa.Integer(), nullable=False),
        sa.Column("secondary_metric", sa.String(), nullable=True),
        sa.Column("secondary_target", sa.Integer(), nullable=True),
        sa.Column("secondary_target_type", sa.String(), nullable=True),
        sa.Column("pin_hash", sa.String(), nullable=True),
        sa.Column("pin_set_at", sa.DateTime(), nullable=True),
        sa.Column("failed_pin_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pin_locked_until", sa.DateTime(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(),
            nullable=False,
            server_default="America/New_York",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "primary_metric IN ('calories','net_carbs','total_carbs','protein')",
            name="ck_users_primary_metric",
        ),
        sa.CheckConstraint(
            "secondary_target_type IS NULL OR secondary_target_type IN ('min','max')",
            name="ck_users_secondary_target_type",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "magic_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("token", name="uq_magic_links_token"),
    )
    op.create_index("ix_magic_links_user_id", "magic_links", ["user_id"])
    op.create_index("ix_magic_links_token", "magic_links", ["token"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("token", name="uq_sessions_token"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token", "sessions", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sessions_token", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_magic_links_token", table_name="magic_links")
    op.drop_index("ix_magic_links_user_id", table_name="magic_links")
    op.drop_table("magic_links")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
