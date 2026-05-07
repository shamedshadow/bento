"""entries table

Revision ID: 0003_entries
Revises: 0002_foods
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_entries"
down_revision: Union[str, None] = "0002_foods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id"),
            nullable=False,
        ),
        sa.Column("amount_g", sa.Float(), nullable=False),
        sa.Column("meal_type", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_path", sa.String(), nullable=True),
        sa.Column("logged_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "meal_type IS NULL OR meal_type IN "
            "('breakfast','lunch','dinner','snack')",
            name="ck_entries_meal_type",
        ),
    )
    op.create_index(
        "ix_entries_user_logged", "entries", ["user_id", "logged_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_entries_user_logged", table_name="entries")
    op.drop_table("entries")
