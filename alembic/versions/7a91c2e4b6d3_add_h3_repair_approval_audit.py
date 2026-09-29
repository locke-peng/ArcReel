"""add h3 repair approval audit fields

Revision ID: 7a91c2e4b6d3
Revises: 5e7c1a2d4f90
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a91c2e4b6d3"
down_revision: str | Sequence[str] | None = "5e7c1a2d4f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("h3_repair_tickets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("lifecycle_actor", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("lifecycle_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approval_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("h3_repair_tickets", schema=None) as batch_op:
        batch_op.drop_column("approval_json")
        batch_op.drop_column("lifecycle_at")
        batch_op.drop_column("lifecycle_actor")
