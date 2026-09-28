"""Phase 5 Slice 2 approval-audit migration contract."""

from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command


def test_h3_repair_approval_audit_migration_round_trip(
    alembic_cfg: tuple[Config, Path], migration_revisions: Callable[[str], tuple[str, str]]
) -> None:
    revision, parent = migration_revisions("*_add_h3_repair_approval_audit.py")
    cfg, path = alembic_cfg
    command.upgrade(cfg, revision)
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        columns = {column["name"] for column in sa.inspect(engine).get_columns("h3_repair_tickets")}
        assert {"lifecycle_actor", "lifecycle_at", "approval_json"}.issubset(columns)

        command.downgrade(cfg, parent)
        downgraded = {column["name"] for column in sa.inspect(engine).get_columns("h3_repair_tickets")}
        assert "lifecycle_actor" not in downgraded
        assert "lifecycle_at" not in downgraded
        assert "approval_json" not in downgraded

        command.upgrade(cfg, revision)
        upgraded = {column["name"] for column in sa.inspect(engine).get_columns("h3_repair_tickets")}
        assert {"lifecycle_actor", "lifecycle_at", "approval_json"}.issubset(upgraded)
    finally:
        engine.dispose()
