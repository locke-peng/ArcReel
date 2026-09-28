"""Persistent Phase 5 lifecycle state for immutable H3 Repair Tickets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class H3RepairTicketRecord(TimestampMixin, Base):
    """Project-scoped persistence row for one immutable Phase 4 H3RepairTicket."""

    __tablename__ = "h3_repair_tickets"
    __table_args__ = (
        UniqueConstraint("project_name", "ticket_sha256", name="uq_h3_repair_ticket_project_sha"),
        UniqueConstraint("project_name", "execution_identity", name="uq_h3_repair_ticket_project_execution"),
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

    # Slice 3 queue identity. execution_identity is deterministic for one immutable
    # ticket+approval binding; execution_task_id points at the one queue row owning it.
    execution_identity: Mapped[str | None] = mapped_column(String(128))
    execution_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    provider_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    # Slice 4+ result fields.
    repair_output_sha256: Mapped[str | None] = mapped_column(String(64))
    reqa_outcome: Mapped[str | None] = mapped_column(String(64))
    selected_artifact_id: Mapped[str | None] = mapped_column(String(255))
    selected_version_id: Mapped[str | None] = mapped_column(String(255))


class H3RepairProjectBudget(TimestampMixin, Base):
    """Optional project-level paid-repair ceiling.

    Absence of a row means no project ceiling. Per-approval max_provider_calls remains
    mandatory regardless of whether a project ceiling exists.
    """

    __tablename__ = "h3_repair_project_budget"
    __table_args__ = (
        CheckConstraint("provider_call_ceiling >= 1", name="ck_h3_repair_budget_ceiling_positive"),
        CheckConstraint("provider_call_count >= 0", name="ck_h3_repair_budget_count_nonnegative"),
    )

    project_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    provider_call_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_call_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )



class H3RepairProjectControl(TimestampMixin, Base):
    """Optional Phase 6 project-level repair admission controls.

    Absence of a row means admission is enabled and no project-specific running-task
    ceiling is applied. This table coordinates the existing Phase 5 queue; it is not a
    second queue or execution state machine.
    """

    __tablename__ = "h3_repair_project_control"
    __table_args__ = (
        CheckConstraint(
            "max_running_tasks IS NULL OR max_running_tasks >= 1",
            name="ck_h3_repair_project_control_max_running_positive",
        ),
    )

    project_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    paused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    max_running_tasks: Mapped[int | None] = mapped_column(Integer)
