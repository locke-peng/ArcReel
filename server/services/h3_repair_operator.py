"""Phase 5 Slice 6 operator read/command surface for H3 Repair Tickets.

This module is intentionally thin: it exposes the persisted lifecycle accepted in
Slices 1-5 and delegates every state transition, approval binding, queue operation,
provider execution and formal selection to the existing services.
"""

from __future__ import annotations

import asyncio
from typing import Any

from lib.db import safe_session_factory
from lib.generation_queue import get_generation_queue
from lib.project_manager import get_project_manager
from lib.reference_video.h3_provider_repair_runtime import resolve_h3_repair_source_version
from lib.reference_video.h3_repair_approval_service import (
    H3RepairApprovalFacts,
    H3RepairApprovalService,
)
from lib.reference_video.h3_repair_queue import H3RepairQueueService
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
    PersistedH3RepairTicket,
)


def _iso(value: object) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else None


def _ticket_view(ticket: PersistedH3RepairTicket) -> dict[str, Any]:
    immutable = ticket.ticket
    max_calls = ticket.max_provider_calls
    remaining = None if max_calls is None else max(max_calls - ticket.provider_call_count, 0)
    return {
        "ticket_id": immutable.ticket_id,
        "ticket_sha256": immutable.ticket_sha256,
        "unit_id": immutable.unit_id,
        "shot_id": immutable.shot_id,
        "scope_kind": immutable.scope_kind.value,
        "time_range": {
            "start_seconds": immutable.start_seconds,
            "end_seconds": immutable.end_seconds,
        },
        "failure_class": immutable.failure_class,
        "repair_action": immutable.repair_action,
        "canonical_violation": immutable.canonical_violation,
        "planner_reason": immutable.planner_reason,
        "provider_recall_required": immutable.provider_recall_required,
        "approval_eligible": immutable.approval_eligible,
        "provenance": {
            "source_media_sha256": immutable.source_media_sha256,
            "provider_prompt_sha256": immutable.provider_prompt_sha256,
            "reference_sha256": list(immutable.reference_sha256),
            "provider_task_id": immutable.provider_task_id,
            "provider_run_id": immutable.provider_run_id,
            "provider_artifact_id": immutable.provider_artifact_id,
        },
        "provider_call_allowance": {
            "max_provider_calls": max_calls,
            "provider_call_count": ticket.provider_call_count,
            "remaining_provider_calls": remaining,
        },
        "lifecycle": {
            "state": ticket.lifecycle_state.value,
            "reason": ticket.lifecycle_reason,
            "actor": ticket.lifecycle_actor,
            "at": _iso(ticket.lifecycle_at),
        },
        "approval": {
            "approved_by": ticket.approval_identity,
            "approved_at": _iso(ticket.approval_at),
        },
        "execution": {
            "execution_identity": ticket.execution_identity,
            "task_id": ticket.execution_task_id,
            "attempt_count": ticket.attempt_count,
        },
        "result": {
            "repair_output_sha256": ticket.repair_output_sha256,
            "reqa_outcome": ticket.reqa_outcome,
            "selected_artifact_id": ticket.selected_artifact_id,
            "selected_version_id": ticket.selected_version_id,
        },
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
    }


async def resolve_h3_repair_project_path(project_name: str):
    return await asyncio.to_thread(get_project_manager().get_project_path, project_name)


async def load_h3_repair_ticket_record(project_name: str, ticket_id: str) -> PersistedH3RepairTicket:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        ticket = await H3RepairTicketStore(session).load(project_name=project_name, ticket_id=ticket_id)
    if ticket is None:
        raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
    return ticket


async def list_h3_repair_tickets(
    *,
    project_name: str,
    lifecycle_state: H3RepairTicketLifecycleState | None = None,
    unit_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        tickets = await H3RepairTicketStore(session).list_for_project(
            project_name=project_name,
            lifecycle_state=lifecycle_state,
            unit_id=unit_id,
            limit=limit,
        )
    return [_ticket_view(ticket) for ticket in tickets]


async def get_h3_repair_ticket(*, project_name: str, ticket_id: str) -> dict[str, Any]:
    return _ticket_view(await load_h3_repair_ticket_record(project_name, ticket_id))


async def approve_and_enqueue_h3_repair(
    *,
    project_name: str,
    ticket_id: str,
    approved_by: str,
    max_provider_calls: int = 1,
) -> dict[str, Any]:
    project_path = await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        store = H3RepairTicketStore(session)
        persisted = await store.load(project_name=project_name, ticket_id=ticket_id)
        if persisted is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        try:
            source = await asyncio.to_thread(
                resolve_h3_repair_source_version,
                project_path=project_path,
                ticket=persisted.ticket,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("repair source media no longer exists") from exc
        if persisted.ticket.shot_id is None:
            raise RuntimeError("provider repair approval requires a shot-scoped Repair Ticket")
        current_facts = H3RepairApprovalFacts(
            source_media_sha256=source.media_sha256,
            shot_id=persisted.ticket.shot_id,
            repair_action=persisted.ticket.repair_action,
            provider_prompt_sha256=source.provider_prompt_sha256,
            reference_sha256=persisted.ticket.reference_sha256,
        )
        approval = await H3RepairApprovalService(session).approve(
            project_name=project_name,
            ticket_id=ticket_id,
            approved_by=approved_by,
            current_facts=current_facts,
            max_provider_calls=max_provider_calls,
        )
        queued = await H3RepairQueueService(session).enqueue_approved_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            user_id=approved_by,
        )
        refreshed = await store.load(project_name=project_name, ticket_id=ticket_id)
        if refreshed is None:
            raise RuntimeError("repair ticket disappeared after queue admission")
    return {
        "ticket": _ticket_view(refreshed),
        "approval": approval.approval.to_dict(),
        "queue": {
            "task_id": queued.task_id,
            "execution_identity": queued.execution_identity,
            "task_status": queued.task_status,
            "deduped": queued.deduped,
        },
    }


async def reject_h3_repair(
    *,
    project_name: str,
    ticket_id: str,
    rejected_by: str,
    reason: str | None = None,
) -> dict[str, Any]:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        ticket = await H3RepairApprovalService(session).reject(
            project_name=project_name,
            ticket_id=ticket_id,
            rejected_by=rejected_by,
            reason=reason,
        )
    return _ticket_view(ticket)


async def cancel_h3_repair(
    *,
    project_name: str,
    ticket_id: str,
    cancelled_by: str,
    reason: str | None = None,
) -> dict[str, Any]:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        before = await H3RepairTicketStore(session).load(project_name=project_name, ticket_id=ticket_id)
        if before is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        ticket = await H3RepairApprovalService(session).cancel(
            project_name=project_name,
            ticket_id=ticket_id,
            cancelled_by=cancelled_by,
            reason=reason,
        )

    task_cancel = None
    if before.execution_task_id is not None:
        queue = get_generation_queue()
        task = await queue.get_task(before.execution_task_id)
        if task is not None and task.get("status") in {"queued", "running", "cancelling"}:
            task_cancel = await queue.cancel_task(before.execution_task_id)
    return {"ticket": _ticket_view(ticket), "task_cancel": task_cancel}


def _execution_task_view(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if task is None:
        return None
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "provider_id": task.get("provider_id"),
        "provider_job_id": task.get("provider_job_id"),
        "provider_endpoint": task.get("provider_endpoint"),
        "queued_at": task.get("queued_at"),
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
    }


async def get_h3_repair_execution_status(*, project_name: str, ticket_id: str) -> dict[str, Any]:
    ticket = await load_h3_repair_ticket_record(project_name, ticket_id)
    task = (
        await get_generation_queue().get_task(ticket.execution_task_id)
        if ticket.execution_task_id is not None
        else None
    )
    return {
        "ticket_id": ticket.ticket.ticket_id,
        "lifecycle_state": ticket.lifecycle_state.value,
        "execution_identity": ticket.execution_identity,
        "attempt_count": ticket.attempt_count,
        "provider_call_count": ticket.provider_call_count,
        "task": _execution_task_view(task),
    }


async def get_h3_repair_result(*, project_name: str, ticket_id: str) -> dict[str, Any]:
    ticket = await load_h3_repair_ticket_record(project_name, ticket_id)
    task = (
        await get_generation_queue().get_task(ticket.execution_task_id)
        if ticket.execution_task_id is not None
        else None
    )
    task_result = task.get("result") if isinstance(task, dict) and isinstance(task.get("result"), dict) else {}
    return {
        "ticket_id": ticket.ticket.ticket_id,
        "lifecycle_state": ticket.lifecycle_state.value,
        "repair_output_sha256": ticket.repair_output_sha256,
        "reqa_outcome": ticket.reqa_outcome,
        "selected_current": ticket.lifecycle_state is H3RepairTicketLifecycleState.ACCEPTED,
        "selected_artifact_id": ticket.selected_artifact_id,
        "selected_version_id": ticket.selected_version_id,
        "output_media_path": task_result.get("output_media_path"),
        "provider_shot_path": task_result.get("provider_shot_path"),
        "reqa": task_result.get("reqa") if isinstance(task_result.get("reqa"), dict) else None,
    }
