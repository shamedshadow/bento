"""reminder_log table

Revision ID: 0007_reminder_log
Revises: 0006_discord_settings
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_reminder_log"
down_revision: Union[str, None] = "0006_discord_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reminder_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reminder_type", sa.String(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_reminder_log_user_id", "reminder_log", ["user_id"])
    op.create_index(
        "ix_reminder_log_user_type_sent",
        "reminder_log",
        ["user_id", "reminder_type", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reminder_log_user_type_sent", table_name="reminder_log")
    op.drop_index("ix_reminder_log_user_id", table_name="reminder_log")
    op.drop_table("reminder_log")
