"""foods table

Revision ID: 0002_foods
Revises: 0001_initial
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_foods"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("default_serving_g", sa.Float(), nullable=True),
        sa.Column("default_serving_label", sa.String(), nullable=True),
        sa.Column("calories_per_100g", sa.Float(), nullable=True),
        sa.Column("carbs_per_100g", sa.Float(), nullable=True),
        sa.Column("fiber_per_100g", sa.Float(), nullable=True),
        sa.Column("protein_per_100g", sa.Float(), nullable=True),
        sa.Column("fat_per_100g", sa.Float(), nullable=True),
        sa.Column("sugar_per_100g", sa.Float(), nullable=True),
        sa.Column("sodium_per_100g", sa.Float(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("photo_path", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "source_id", name="uq_foods_source_id"),
        sa.CheckConstraint(
            "source IN ('openfoodfacts','usda','custom')",
            name="ck_foods_source",
        ),
    )
    op.create_index("ix_foods_barcode", "foods", ["barcode"])
    op.create_index("ix_foods_name", "foods", ["name"])


def downgrade() -> None:
    op.drop_index("ix_foods_name", table_name="foods")
    op.drop_index("ix_foods_barcode", table_name="foods")
    op.drop_table("foods")
