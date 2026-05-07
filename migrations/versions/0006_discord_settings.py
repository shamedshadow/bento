"""discord_settings table

Revision ID: 0006_discord_settings
Revises: 0005_saved_meals
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_discord_settings"
down_revision: Union[str, None] = "0005_saved_meals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discord_settings",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("webhook_url", sa.String(), nullable=True),
        sa.Column(
            "meal_reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("meal_reminders_times", sa.String(), nullable=True),
        sa.Column(
            "eod_summary_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "eod_summary_time",
            sa.String(),
            nullable=False,
            server_default="21:00",
        ),
        sa.Column(
            "weekly_summary_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "weekly_summary_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "log_nudge_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "log_nudge_after_hours",
            sa.Integer(),
            nullable=False,
            server_default="6",
        ),
        sa.Column(
            "auto_disabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("discord_settings")
