"""Phase 5 H3 Repair Ticket persistence migration contract."""

from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command


def test_h3_repair_ticket_migration_round_trip(
    alembic_cfg: tuple[Config, Path], migration_revisions: Callable[[str], tuple[str, str]]
) -> None:
    revision, parent = migration_revisions("*_create_h3_repair_tickets.py")
    cfg, path = alembic_cfg
    command.upgrade(cfg, revision)
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        inspector = sa.inspect(engine)
        assert "h3_repair_tickets" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("h3_repair_tickets")}
        assert {
            "project_name",
            "ticket_id",
            "ticket_sha256",
            "ticket_json",
            "lifecycle_state",
            "approval_eligible",
            "unit_id",
            "shot_id",
            "scope_kind",
            "source_media_sha256",
            "provider_prompt_sha256",
            "approval_identity",
            "approval_at",
            "max_provider_calls",
            "execution_identity",
            "attempt_count",
            "provider_call_count",
            "repair_output_sha256",
            "reqa_outcome",
            "selected_artifact_id",
            "selected_version_id",
            "created_at",
            "updated_at",
        }.issubset(columns)
        assert inspector.get_pk_constraint("h3_repair_tickets")["constrained_columns"] == [
            "project_name",
            "ticket_id",
        ]
        index_names = {index["name"] for index in inspector.get_indexes("h3_repair_tickets")}
        assert {
            "ix_h3_repair_tickets_project_state",
            "ix_h3_repair_tickets_project_unit",
        }.issubset(index_names)

        command.downgrade(cfg, parent)
        assert "h3_repair_tickets" not in sa.inspect(engine).get_table_names()
        command.upgrade(cfg, revision)
        assert "h3_repair_tickets" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
