"""Persistent Phase 5 lifecycle state for immutable H3 Repair Tickets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class H3RepairTicketRecord(TimestampMixin, Base):
    """Project-scoped persistence row for one immutable Phase 4 H3RepairTicket.

    ticket_json is the authoritative immutable snapshot. The duplicated identity/scope
    columns are query projections only and are verified against the snapshot whenever the
    ticket is loaded through the Phase 5 store.
    """

    __tablename__ = "h3_repair_tickets"
    __table_args__ = (
        UniqueConstraint("project_name", "ticket_sha256", name="uq_h3_repair_ticket_project_sha"),
        Index("ix_h3_repair_tickets_project_state", "project_name", "lifecycle_state"),
        Index("ix_h3_repair_tickets_project_unit", "project_name", "unit_id"),
    )

    project_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ticket_json: Mapped[str] = mapped_column(Text, nullable=False)

    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_reason: Mapped[str | None] = mapped_column(Text)
    lifecycle_actor: Mapped[str | None] = mapped_column(String(200))
    lifecycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    approval_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    shot_id: Mapped[str | None] = mapped_column(String(128))
    scope_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    start_seconds: Mapped[float | None] = mapped_column(Float)
    end_seconds: Mapped[float | None] = mapped_column(Float)
    failure_class: Mapped[str] = mapped_column(String(64), nullable=False)
    repair_action: Mapped[str] = mapped_column(String(64), nullable=False)
    source_media_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_prompt_sha256: Mapped[str | None] = mapped_column(String(64))

    # The explicit approval snapshot is separate from ticket_json: the ticket remains the
    # immutable Phase 4 repair decision while approval_json records the human authorization
    # and the current execution facts that were checked at approval time.
    approval_json: Mapped[str | None] = mapped_column(Text)
    approval_identity: Mapped[str | None] = mapped_column(String(200))
    approval_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_provider_calls: Mapped[int | None] = mapped_column(Integer)

    # Slice 3+ execution/result fields are created with the ticket table so later slices can
    # populate them without weakening the persisted lifecycle contract.
    execution_identity: Mapped[str | None] = mapped_column(String(128))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    provider_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    repair_output_sha256: Mapped[str | None] = mapped_column(String(64))
    reqa_outcome: Mapped[str | None] = mapped_column(String(64))
    selected_artifact_id: Mapped[str | None] = mapped_column(String(255))
    selected_version_id: Mapped[str | None] = mapped_column(String(255))
