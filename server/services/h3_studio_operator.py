"""Phase 6 Slice 5 studio operator service over accepted production-control primitives."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from lib.db import safe_session_factory
from lib.reference_video.h3_repair_batch import H3RepairBatchAction, build_h3_repair_batch_preview
from lib.reference_video.h3_repair_queue import H3RepairQueueService
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
)
from server.services.h3_production_control import resolve_h3_production_projection
from server.services.h3_repair_batch_operator import execute_h3_repair_batch
from server.services.h3_repair_budget_ledger import resolve_h3_repair_project_ledger
from server.services.h3_repair_operator import (
    get_h3_repair_ticket,
    list_h3_repair_tickets,
    resolve_h3_repair_project_path,
)


def _projection_payload(value: Any) -> dict[str, Any]:
    return asdict(value)


async def get_h3_studio_control(*, project_name: str) -> dict[str, Any]:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        control = await H3RepairQueueService(session).get_project_control(project_name=project_name)
    if control is None:
        return {
            "project_name": project_name,
            "paused": False,
            "max_running_tasks": None,
            "explicit": False,
        }
    return {
        "project_name": project_name,
        "paused": control.paused,
        "max_running_tasks": control.max_running_tasks,
        "explicit": True,
    }


async def set_h3_studio_paused(*, project_name: str, paused: bool) -> dict[str, Any]:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        control = await H3RepairQueueService(session).set_project_paused(
            project_name=project_name,
            paused=paused,
        )
    return {
        "project_name": project_name,
        "paused": control.paused,
        "max_running_tasks": control.max_running_tasks,
        "explicit": True,
    }


async def set_h3_studio_running_cap(
    *,
    project_name: str,
    max_running_tasks: int | None,
) -> dict[str, Any]:
    await resolve_h3_repair_project_path(project_name)
    async with safe_session_factory() as session:
        control = await H3RepairQueueService(session).configure_project_running_cap(
            project_name=project_name,
            max_running_tasks=max_running_tasks,
        )
    return {
        "project_name": project_name,
        "paused": control.paused,
        "max_running_tasks": control.max_running_tasks,
        "explicit": True,
    }


async def get_h3_studio_summary(*, project_name: str) -> dict[str, Any]:
    projection = await resolve_h3_production_projection(project_name=project_name)
    control = await get_h3_studio_control(project_name=project_name)
    ledger = await resolve_h3_repair_project_ledger(project_name=project_name)
    tickets = await list_h3_repair_tickets(project_name=project_name, limit=500)

    pending = [
        item
        for item in tickets
        if item["lifecycle"]["state"] == H3RepairTicketLifecycleState.AWAITING_APPROVAL.value
    ]
    human_review = [
        item
        for item in tickets
        if item["lifecycle"]["state"] == H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED.value
    ]
    approved_waiting = [
        item
        for item in tickets
        if item["lifecycle"]["state"] == H3RepairTicketLifecycleState.APPROVED.value
    ]
    active_states = {
        H3RepairTicketLifecycleState.RUNNING.value,
        H3RepairTicketLifecycleState.PROVIDER_COMPLETED.value,
        H3RepairTicketLifecycleState.REASSEMBLING.value,
        H3RepairTicketLifecycleState.REQA_RUNNING.value,
    }
    active = [item for item in tickets if item["lifecycle"]["state"] in active_states]

    return {
        "project": _projection_payload(projection),
        "control": control,
        "budget": _projection_payload(ledger),
        "queues": {
            "pending_approvals": pending,
            "approved_waiting": approved_waiting,
            "active_executions": active,
            "human_review_required": human_review,
        },
    }


async def preview_h3_studio_batch(
    *,
    project_name: str,
    action: H3RepairBatchAction,
    ticket_ids: Iterable[str],
) -> dict[str, Any]:
    await resolve_h3_repair_project_path(project_name)
    normalized_ids = tuple(ticket_id.strip() for ticket_id in ticket_ids)
    if any(not ticket_id for ticket_id in normalized_ids):
        raise ValueError("batch ticket_id is required")
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("duplicate Repair Ticket in batch")

    async with safe_session_factory() as session:
        store = H3RepairTicketStore(session)
        tickets = []
        for ticket_id in normalized_ids:
            ticket = await store.load(project_name=project_name, ticket_id=ticket_id)
            if ticket is None:
                raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
            tickets.append(ticket)

    return _projection_payload(
        build_h3_repair_batch_preview(
            project_name=project_name,
            action=action,
            tickets=tickets,
        )
    )


async def execute_h3_studio_batch(
    *,
    project_name: str,
    action: H3RepairBatchAction,
    ticket_ids: Iterable[str],
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return _projection_payload(
        await execute_h3_repair_batch(
            project_name=project_name,
            action=action,
            ticket_ids=ticket_ids,
            actor=actor,
            reason=reason,
        )
    )


async def get_h3_studio_ticket_evidence(*, project_name: str, ticket_id: str) -> dict[str, Any]:
    """Expose the accepted persisted ticket view; raw execution checkpoints remain hidden."""

    return await get_h3_repair_ticket(project_name=project_name, ticket_id=ticket_id)
