"""Phase 5 persistence boundary and lifecycle state machine for H3 Repair Tickets.

The immutable Phase 4 H3RepairTicket remains the repair decision artifact. This module
adds project-scoped persistence and lifecycle state only; it does not create a second
failure taxonomy, repair planner, or provider routing policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.models.h3_repair_ticket import H3RepairTicketRecord
from lib.db.repositories.h3_repair_ticket_repo import H3RepairTicketRepository
from lib.reference_video.h3_repair_ticket import (
    H3RepairScopeKind,
    H3RepairTicket,
    H3RepairTicketStatus,
)


class H3RepairTicketLifecycleState(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    PROVIDER_COMPLETED = "provider_completed"
    REASSEMBLING = "reassembling"
    REQA_RUNNING = "reqa_running"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


_ALLOWED_TRANSITIONS: dict[H3RepairTicketLifecycleState, frozenset[H3RepairTicketLifecycleState]] = {
    H3RepairTicketLifecycleState.AWAITING_APPROVAL: frozenset(
        {
            H3RepairTicketLifecycleState.APPROVED,
            H3RepairTicketLifecycleState.REJECTED,
            H3RepairTicketLifecycleState.CANCELLED,
            H3RepairTicketLifecycleState.EXPIRED,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.APPROVED: frozenset(
        {
            H3RepairTicketLifecycleState.QUEUED,
            H3RepairTicketLifecycleState.CANCELLED,
            H3RepairTicketLifecycleState.EXPIRED,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.QUEUED: frozenset(
        {
            H3RepairTicketLifecycleState.RUNNING,
            H3RepairTicketLifecycleState.CANCELLED,
            H3RepairTicketLifecycleState.EXPIRED,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.RUNNING: frozenset(
        {
            H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            H3RepairTicketLifecycleState.CANCELLED,
            H3RepairTicketLifecycleState.EXPIRED,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.PROVIDER_COMPLETED: frozenset(
        {
            H3RepairTicketLifecycleState.REASSEMBLING,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.REASSEMBLING: frozenset(
        {
            H3RepairTicketLifecycleState.REQA_RUNNING,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.REQA_RUNNING: frozenset(
        {
            H3RepairTicketLifecycleState.ACCEPTED,
            H3RepairTicketLifecycleState.REJECTED,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    H3RepairTicketLifecycleState.ACCEPTED: frozenset(),
    H3RepairTicketLifecycleState.REJECTED: frozenset(),
    H3RepairTicketLifecycleState.CANCELLED: frozenset(),
    H3RepairTicketLifecycleState.EXPIRED: frozenset(),
    H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED: frozenset(),
}


@dataclass(frozen=True)
class PersistedH3RepairTicket:
    project_name: str
    ticket: H3RepairTicket
    lifecycle_state: H3RepairTicketLifecycleState
    lifecycle_reason: str | None
    lifecycle_actor: str | None
    lifecycle_at: datetime | None
    approval_json: str | None
    approval_identity: str | None
    approval_at: datetime | None
    max_provider_calls: int | None
    execution_identity: str | None
    execution_task_id: str | None
    attempt_count: int
    provider_call_count: int
    repair_output_sha256: str | None
    reqa_outcome: str | None
    selected_artifact_id: str | None
    selected_version_id: str | None
    created_at: datetime
    updated_at: datetime


def validate_h3_repair_ticket_transition(
    current: H3RepairTicketLifecycleState,
    target: H3RepairTicketLifecycleState,
) -> None:
    """Fail closed on lifecycle skips/backwards moves; same-state requests are idempotent."""

    if current is target:
        return
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise RuntimeError(f"illegal H3 Repair Ticket lifecycle transition: {current.value} -> {target.value}")


def _ticket_snapshot(ticket: H3RepairTicket) -> str:
    return json.dumps(ticket.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_immutable_ticket_identity(ticket: H3RepairTicket) -> None:
    encoded = json.dumps(
        ticket.payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    if ticket.ticket_sha256 != digest or ticket.ticket_id != f"h3rt_{digest[:24]}":
        raise RuntimeError("H3 Repair Ticket cryptographic identity does not match its immutable payload")


def _ticket_from_snapshot(snapshot: str) -> H3RepairTicket:
    data = json.loads(snapshot)
    if not isinstance(data, dict):
        raise RuntimeError("persisted H3 Repair Ticket snapshot must be an object")
    return H3RepairTicket(
        schema_version=int(data["schema_version"]),
        ticket_id=str(data["ticket_id"]),
        ticket_sha256=str(data["ticket_sha256"]),
        status=H3RepairTicketStatus(str(data["status"])),
        approval_eligible=bool(data["approval_eligible"]),
        unit_id=str(data["unit_id"]),
        shot_id=str(data["shot_id"]) if data.get("shot_id") is not None else None,
        scope_kind=H3RepairScopeKind(str(data["scope_kind"])),
        start_seconds=float(data["start_seconds"]) if data.get("start_seconds") is not None else None,
        end_seconds=float(data["end_seconds"]) if data.get("end_seconds") is not None else None,
        region=str(data["region"]) if data.get("region") is not None else None,
        failure_class=str(data["failure_class"]),
        repair_action=str(data["repair_action"]),
        provider_recall_required=bool(data["provider_recall_required"]),
        canonical_violation=str(data["canonical_violation"]),
        planner_reason=str(data["planner_reason"]),
        source_media_sha256=str(data["source_media_sha256"]),
        provider_prompt_sha256=(
            str(data["provider_prompt_sha256"]) if data.get("provider_prompt_sha256") is not None else None
        ),
        reference_sha256=tuple(str(value) for value in data.get("reference_sha256", [])),
        evidence_frames=tuple(int(value) for value in data.get("evidence_frames", [])),
        tags=tuple(str(value) for value in data.get("tags", [])),
        provider_task_id=str(data["provider_task_id"]) if data.get("provider_task_id") is not None else None,
        provider_run_id=int(data["provider_run_id"]) if data.get("provider_run_id") is not None else None,
        provider_artifact_id=(
            int(data["provider_artifact_id"]) if data.get("provider_artifact_id") is not None else None
        ),
    )


def _initial_state(ticket: H3RepairTicket) -> H3RepairTicketLifecycleState:
    if ticket.status is H3RepairTicketStatus.AWAITING_APPROVAL:
        return H3RepairTicketLifecycleState.AWAITING_APPROVAL
    if ticket.status is H3RepairTicketStatus.HUMAN_REVIEW_REQUIRED:
        return H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED
    raise RuntimeError(f"unsupported Phase 4 repair ticket status: {ticket.status.value}")


def _record_to_domain(record: H3RepairTicketRecord) -> PersistedH3RepairTicket:
    ticket = _ticket_from_snapshot(record.ticket_json)
    _validate_immutable_ticket_identity(ticket)
    expected = {
        "ticket_id": record.ticket_id,
        "ticket_sha256": record.ticket_sha256,
        "unit_id": record.unit_id,
        "shot_id": record.shot_id,
        "scope_kind": record.scope_kind,
        "failure_class": record.failure_class,
        "repair_action": record.repair_action,
        "source_media_sha256": record.source_media_sha256,
        "provider_prompt_sha256": record.provider_prompt_sha256,
        "approval_eligible": record.approval_eligible,
    }
    actual: dict[str, Any] = {
        "ticket_id": ticket.ticket_id,
        "ticket_sha256": ticket.ticket_sha256,
        "unit_id": ticket.unit_id,
        "shot_id": ticket.shot_id,
        "scope_kind": ticket.scope_kind.value,
        "failure_class": ticket.failure_class,
        "repair_action": ticket.repair_action,
        "source_media_sha256": ticket.source_media_sha256,
        "provider_prompt_sha256": ticket.provider_prompt_sha256,
        "approval_eligible": ticket.approval_eligible,
    }
    if actual != expected or _ticket_snapshot(ticket) != record.ticket_json:
        raise RuntimeError("persisted H3 Repair Ticket immutable identity does not match its snapshot")

    return PersistedH3RepairTicket(
        project_name=record.project_name,
        ticket=ticket,
        lifecycle_state=H3RepairTicketLifecycleState(record.lifecycle_state),
        lifecycle_reason=record.lifecycle_reason,
        lifecycle_actor=record.lifecycle_actor,
        lifecycle_at=record.lifecycle_at,
        approval_json=record.approval_json,
        approval_identity=record.approval_identity,
        approval_at=record.approval_at,
        max_provider_calls=record.max_provider_calls,
        execution_identity=record.execution_identity,
        execution_task_id=record.execution_task_id,
        attempt_count=record.attempt_count,
        provider_call_count=record.provider_call_count,
        repair_output_sha256=record.repair_output_sha256,
        reqa_outcome=record.reqa_outcome,
        selected_artifact_id=record.selected_artifact_id,
        selected_version_id=record.selected_version_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class H3RepairTicketStore:
    """Transactional service for ticket persistence and lifecycle transitions.

    Methods flush but do not commit. The caller owns the surrounding transaction so ticket
    creation can be composed atomically with later approval/queue operations.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = H3RepairTicketRepository(session)

    async def persist(self, *, project_name: str, ticket: H3RepairTicket) -> PersistedH3RepairTicket:
        project_name = project_name.strip()
        if not project_name:
            raise ValueError("project_name is required")

        _validate_immutable_ticket_identity(ticket)
        existing = await self.repository.get(project_name=project_name, ticket_id=ticket.ticket_id)
        snapshot = _ticket_snapshot(ticket)
        if existing is not None:
            if existing.ticket_sha256 != ticket.ticket_sha256 or existing.ticket_json != snapshot:
                raise RuntimeError("repair ticket_id already exists with different immutable identity")
            return _record_to_domain(existing)

        record = H3RepairTicketRecord(
            project_name=project_name,
            ticket_id=ticket.ticket_id,
            ticket_sha256=ticket.ticket_sha256,
            ticket_json=snapshot,
            lifecycle_state=_initial_state(ticket).value,
            approval_eligible=ticket.approval_eligible,
            unit_id=ticket.unit_id,
            shot_id=ticket.shot_id,
            scope_kind=ticket.scope_kind.value,
            start_seconds=ticket.start_seconds,
            end_seconds=ticket.end_seconds,
            failure_class=ticket.failure_class,
            repair_action=ticket.repair_action,
            source_media_sha256=ticket.source_media_sha256,
            provider_prompt_sha256=ticket.provider_prompt_sha256,
        )
        await self.repository.add(record)
        return _record_to_domain(record)

    async def load(self, *, project_name: str, ticket_id: str) -> PersistedH3RepairTicket | None:
        record = await self.repository.get(project_name=project_name, ticket_id=ticket_id)
        return _record_to_domain(record) if record is not None else None

    async def list_for_project(
        self,
        *,
        project_name: str,
        lifecycle_state: H3RepairTicketLifecycleState | None = None,
        unit_id: str | None = None,
        limit: int = 100,
    ) -> list[PersistedH3RepairTicket]:
        records = await self.repository.list_for_project(
            project_name=project_name,
            lifecycle_state=lifecycle_state.value if lifecycle_state is not None else None,
            unit_id=unit_id,
            limit=limit,
        )
        return [_record_to_domain(record) for record in records]

    async def transition(
        self,
        *,
        project_name: str,
        ticket_id: str,
        target: H3RepairTicketLifecycleState,
        reason: str | None = None,
    ) -> PersistedH3RepairTicket:
        record = await self.repository.get(project_name=project_name, ticket_id=ticket_id)
        if record is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")

        current = H3RepairTicketLifecycleState(record.lifecycle_state)
        validate_h3_repair_ticket_transition(current, target)
        if current is not target:
            record.lifecycle_state = target.value
            record.lifecycle_reason = reason
            await self.session.flush()
        return _record_to_domain(record)
