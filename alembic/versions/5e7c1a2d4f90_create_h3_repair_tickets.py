"""create h3 repair tickets table

Revision ID: 5e7c1a2d4f90
Revises: c5a819b247de
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5e7c1a2d4f90"
down_revision: str | Sequence[str] | None = "c5a819b247de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "h3_repair_tickets",
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_sha256", sa.String(length=64), nullable=False),
        sa.Column("ticket_json", sa.Text(), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_reason", sa.Text(), nullable=True),
        sa.Column("approval_eligible", sa.Boolean(), nullable=False),
        sa.Column("unit_id", sa.String(length=128), nullable=False),
        sa.Column("shot_id", sa.String(length=128), nullable=True),
        sa.Column("scope_kind", sa.String(length=32), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=True),
        sa.Column("end_seconds", sa.Float(), nullable=True),
        sa.Column("failure_class", sa.String(length=64), nullable=False),
        sa.Column("repair_action", sa.String(length=64), nullable=False),
        sa.Column("source_media_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider_prompt_sha256", sa.String(length=64), nullable=True),
        sa.Column("approval_identity", sa.String(length=200), nullable=True),
        sa.Column("approval_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_provider_calls", sa.Integer(), nullable=True),
        sa.Column("execution_identity", sa.String(length=128), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("provider_call_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("repair_output_sha256", sa.String(length=64), nullable=True),
        sa.Column("reqa_outcome", sa.String(length=64), nullable=True),
        sa.Column("selected_artifact_id", sa.String(length=255), nullable=True),
        sa.Column("selected_version_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_name", "ticket_id"),
        sa.UniqueConstraint("project_name", "ticket_sha256", name="uq_h3_repair_ticket_project_sha"),
    )
    with op.batch_alter_table("h3_repair_tickets", schema=None) as batch_op:
        batch_op.create_index(
            "ix_h3_repair_tickets_project_state",
            ["project_name", "lifecycle_state"],
            unique=False,
        )
        batch_op.create_index(
            "ix_h3_repair_tickets_project_unit",
            ["project_name", "unit_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("h3_repair_tickets", schema=None) as batch_op:
        batch_op.drop_index("ix_h3_repair_tickets_project_unit")
        batch_op.drop_index("ix_h3_repair_tickets_project_state")
    op.drop_table("h3_repair_tickets")
