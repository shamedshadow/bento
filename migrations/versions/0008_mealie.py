"""mealie_settings table + allow source='mealie' on foods

Revision ID: 0008_mealie
Revises: 0007_reminder_log
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_mealie"
down_revision: Union[str, None] = "0007_reminder_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite can't ALTER a CHECK constraint in place; batch mode rebuilds the
    # table. The render_as_batch=True in env.py is what makes this work.
    with op.batch_alter_table("foods") as batch_op:
        batch_op.drop_constraint("ck_foods_source", type_="check")
        batch_op.create_check_constraint(
            "ck_foods_source",
            "source IN ('openfoodfacts','usda','custom','mealie')",
        )

    op.create_table(
        "mealie_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("api_token", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_summary", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("mealie_settings")
    with op.batch_alter_table("foods") as batch_op:
        batch_op.drop_constraint("ck_foods_source", type_="check")
        batch_op.create_check_constraint(
            "ck_foods_source",
            "source IN ('openfoodfacts','usda','custom')",
        )
