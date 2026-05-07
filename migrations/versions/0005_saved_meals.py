"""saved_meals + saved_meal_items

Revision ID: 0005_saved_meals
Revises: 0004_favorites
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_saved_meals"
down_revision: Union[str, None] = "0004_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_meals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("default_meal_type", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "default_meal_type IS NULL OR default_meal_type IN "
            "('breakfast','lunch','dinner','snack')",
            name="ck_saved_meals_default_meal_type",
        ),
    )
    op.create_index("ix_saved_meals_user_id", "saved_meals", ["user_id"])

    op.create_table(
        "saved_meal_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "saved_meal_id",
            sa.Integer(),
            sa.ForeignKey("saved_meals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id"),
            nullable=False,
        ),
        sa.Column("amount_g", sa.Float(), nullable=False),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_table("saved_meal_items")
    op.drop_index("ix_saved_meals_user_id", table_name="saved_meals")
    op.drop_table("saved_meals")
