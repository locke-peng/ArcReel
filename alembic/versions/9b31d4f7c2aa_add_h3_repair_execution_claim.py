"""add h3 repair execution claim and project budget

Revision ID: 9b31d4f7c2aa
Revises: 7a91c2e4b6d3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b31d4f7c2aa"
down_revision: str | Sequence[str] | None = "7a91c2e4b6d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("h3_repair_tickets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("execution_task_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_h3_repair_tickets_execution_task_id_tasks",
            "tasks",
            ["execution_task_id"],
            ["task_id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_h3_repair_ticket_project_execution",
            ["project_name", "execution_identity"],
        )

    op.create_table(
        "h3_repair_project_budget",
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("provider_call_ceiling", sa.Integer(), nullable=False),
        sa.Column("provider_call_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_call_ceiling >= 1",
            name="ck_h3_repair_budget_ceiling_positive",
        ),
        sa.CheckConstraint(
            "provider_call_count >= 0",
            name="ck_h3_repair_budget_count_nonnegative",
        ),
        sa.PrimaryKeyConstraint("project_name"),
    )


def downgrade() -> None:
    op.drop_table("h3_repair_project_budget")
    with op.batch_alter_table("h3_repair_tickets", schema=None) as batch_op:
        batch_op.drop_constraint("uq_h3_repair_ticket_project_execution", type_="unique")
        batch_op.drop_constraint(
            "fk_h3_repair_tickets_execution_task_id_tasks",
            type_="foreignkey",
        )
        batch_op.drop_column("execution_task_id")
