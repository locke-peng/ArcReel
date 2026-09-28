"""Phase 5 Slice 3 execution-claim migration contract."""

from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command


def test_h3_repair_execution_claim_migration_round_trip(
    alembic_cfg: tuple[Config, Path], migration_revisions: Callable[[str], tuple[str, str]]
) -> None:
    revision, parent = migration_revisions("*_add_h3_repair_execution_claim.py")
    cfg, path = alembic_cfg
    command.upgrade(cfg, revision)
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        inspector = sa.inspect(engine)
        ticket_columns = {column["name"] for column in inspector.get_columns("h3_repair_tickets")}
        assert "execution_task_id" in ticket_columns
        assert "h3_repair_project_budget" in inspector.get_table_names()

        budget_columns = {column["name"] for column in inspector.get_columns("h3_repair_project_budget")}
        assert budget_columns == {
            "project_name",
            "provider_call_ceiling",
            "provider_call_count",
            "created_at",
            "updated_at",
        }

        uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("h3_repair_tickets")
        }
        assert ("project_name", "execution_identity") in uniques

        foreign_keys = inspector.get_foreign_keys("h3_repair_tickets")
        assert any(
            fk["constrained_columns"] == ["execution_task_id"]
            and fk["referred_table"] == "tasks"
            and fk["referred_columns"] == ["task_id"]
            for fk in foreign_keys
        )

        command.downgrade(cfg, parent)
        inspector = sa.inspect(engine)
        assert "h3_repair_project_budget" not in inspector.get_table_names()
        downgraded = {column["name"] for column in inspector.get_columns("h3_repair_tickets")}
        assert "execution_task_id" not in downgraded

        command.upgrade(cfg, revision)
        inspector = sa.inspect(engine)
        assert "h3_repair_project_budget" in inspector.get_table_names()
        assert "execution_task_id" in {
            column["name"] for column in inspector.get_columns("h3_repair_tickets")
        }
    finally:
        engine.dispose()
