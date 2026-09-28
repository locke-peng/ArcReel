"""Phase 5 Slice 6 operator/API surface for H3 provider repair."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from lib.api_errors import BadRequestError, ConflictError, NotFoundError
from lib.reference_video.h3_repair_approval_service import (
    H3RepairApprovalConflictError,
    H3RepairApprovalStaleError,
)
from lib.reference_video.h3_repair_queue import H3RepairExecutionConflict
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState
from server.services.h3_repair_operator import (
    approve_and_enqueue_h3_repair,
    cancel_h3_repair,
    get_h3_repair_execution_status,
    get_h3_repair_result,
    get_h3_repair_ticket,
    list_h3_repair_tickets,
    reject_h3_repair,
)

router = APIRouter(prefix="/projects/{project_name}/reference-videos/repairs")


class H3RepairApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=200)
    max_provider_calls: Literal[1] = 1


class H3RepairDecisionRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)


def _repair_not_found(ticket_id: str) -> NotFoundError:
    return NotFoundError("h3_repair_ticket_not_found", ticket_id=ticket_id)


@router.get("/pending")
async def list_pending_h3_repairs(
    project_name: str,
    unit_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        items = await list_h3_repair_tickets(
            project_name=project_name,
            lifecycle_state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            unit_id=unit_id,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    return {"items": items, "count": len(items)}


@router.get("")
async def list_h3_repairs(
    project_name: str,
    lifecycle_state: H3RepairTicketLifecycleState | None = None,
    unit_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        items = await list_h3_repair_tickets(
            project_name=project_name,
            lifecycle_state=lifecycle_state,
            unit_id=unit_id,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    return {"items": items, "count": len(items)}


@router.get("/{ticket_id}")
async def get_h3_repair(project_name: str, ticket_id: str):
    try:
        return await get_h3_repair_ticket(project_name=project_name, ticket_id=ticket_id)
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except KeyError as exc:
        raise _repair_not_found(ticket_id) from exc


@router.post("/{ticket_id}/approve")
async def approve_h3_repair(project_name: str, ticket_id: str, body: H3RepairApproveRequest):
    try:
        return await approve_and_enqueue_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            approved_by=body.approved_by,
            max_provider_calls=body.max_provider_calls,
        )
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except KeyError as exc:
        raise _repair_not_found(ticket_id) from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc
    except (H3RepairApprovalStaleError, H3RepairApprovalConflictError, H3RepairExecutionConflict, RuntimeError) as exc:
        raise ConflictError("h3_repair_state_conflict", ticket_id=ticket_id) from exc


@router.post("/{ticket_id}/reject")
async def reject_h3_repair_ticket(project_name: str, ticket_id: str, body: H3RepairDecisionRequest):
    try:
        return await reject_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            rejected_by=body.actor,
            reason=body.reason,
        )
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except KeyError as exc:
        raise _repair_not_found(ticket_id) from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc
    except RuntimeError as exc:
        raise ConflictError("h3_repair_state_conflict", ticket_id=ticket_id) from exc


@router.post("/{ticket_id}/cancel")
async def cancel_h3_repair_ticket(project_name: str, ticket_id: str, body: H3RepairDecisionRequest):
    try:
        return await cancel_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            cancelled_by=body.actor,
            reason=body.reason,
        )
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except KeyError as exc:
        raise _repair_not_found(ticket_id) from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc
    except RuntimeError as exc:
        raise ConflictError("h3_repair_state_conflict", ticket_id=ticket_id) from exc


@router.get("/{ticket_id}/execution")
async def get_h3_repair_execution(project_name: str, ticket_id: str):
    try:
        return await get_h3_repair_execution_status(project_name=project_name, ticket_id=ticket_id)
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except KeyError as exc:
        raise _repair_not_found(ticket_id) from exc


@router.get("/{ticket_id}/result")
async def get_h3_repair_result_route(project_name: str, ticket_id: str):
    try:
        return await get_h3_repair_result(project_name=project_name, ticket_id=ticket_id)
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except KeyError as exc:
        raise _repair_not_found(ticket_id) from exc
