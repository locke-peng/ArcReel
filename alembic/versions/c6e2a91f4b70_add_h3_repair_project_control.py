"""add h3 repair project admission controls

Revision ID: c6e2a91f4b70
Revises: 9b31d4f7c2aa
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c6e2a91f4b70"
down_revision: str | Sequence[str] | None = "9b31d4f7c2aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "h3_repair_project_control",
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("paused", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("max_running_tasks", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "max_running_tasks IS NULL OR max_running_tasks >= 1",
            name="ck_h3_repair_project_control_max_running_positive",
        ),
        sa.PrimaryKeyConstraint("project_name"),
    )


def downgrade() -> None:
    op.drop_table("h3_repair_project_control")
