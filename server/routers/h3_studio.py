"""Phase 6 Slice 5 project-scale H3 studio operator API."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from lib.api_errors import BadRequestError, ConflictError, NotFoundError
from lib.reference_video.h3_repair_batch import H3RepairBatchAction
from server.auth import CurrentUser
from server.services.h3_studio_operator import (
    execute_h3_studio_batch,
    get_h3_studio_control,
    get_h3_studio_summary,
    get_h3_studio_ticket_evidence,
    preview_h3_studio_batch,
    set_h3_studio_paused,
    set_h3_studio_running_cap,
)

router = APIRouter(prefix="/projects/{project_name}/reference-videos/studio")


class H3StudioPauseRequest(BaseModel):
    paused: bool


class H3StudioRunningCapRequest(BaseModel):
    max_running_tasks: int | None = Field(default=None, ge=1)


class H3StudioBatchRequest(BaseModel):
    action: H3RepairBatchAction
    ticket_ids: list[str] = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=1000)


def _not_found(project_name: str) -> NotFoundError:
    return NotFoundError("project_not_found", name=project_name)


@router.get("/summary")
async def get_studio_summary(project_name: str):
    try:
        return await get_h3_studio_summary(project_name=project_name)
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc
    except RuntimeError as exc:
        raise ConflictError("h3_repair_state_conflict") from exc


@router.get("/control")
async def get_studio_control(project_name: str):
    try:
        return await get_h3_studio_control(project_name=project_name)
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc


@router.put("/control/pause")
async def set_studio_pause(project_name: str, body: H3StudioPauseRequest, user: CurrentUser):
    del user  # Authentication is required by the router; project control is not an approval identity.
    try:
        return await set_h3_studio_paused(project_name=project_name, paused=body.paused)
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc


@router.put("/control/running-cap")
async def set_studio_running_cap(project_name: str, body: H3StudioRunningCapRequest, user: CurrentUser):
    del user
    try:
        return await set_h3_studio_running_cap(
            project_name=project_name,
            max_running_tasks=body.max_running_tasks,
        )
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc


@router.post("/batch/preview")
async def preview_studio_batch(project_name: str, body: H3StudioBatchRequest, user: CurrentUser):
    del user
    try:
        return await preview_h3_studio_batch(
            project_name=project_name,
            action=body.action,
            ticket_ids=body.ticket_ids,
        )
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc
    except KeyError as exc:
        raise NotFoundError("h3_repair_ticket_not_found") from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc


@router.post("/batch/execute")
async def execute_studio_batch(project_name: str, body: H3StudioBatchRequest, user: CurrentUser):
    try:
        return await execute_h3_studio_batch(
            project_name=project_name,
            action=body.action,
            ticket_ids=body.ticket_ids,
            actor=user.id,
            reason=body.reason,
        )
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc
    except ValueError as exc:
        raise BadRequestError("h3_repair_bad_request") from exc
    except RuntimeError as exc:
        raise ConflictError("h3_repair_state_conflict") from exc


@router.get("/evidence/{ticket_id}")
async def get_studio_ticket_evidence(project_name: str, ticket_id: str):
    try:
        return await get_h3_studio_ticket_evidence(
            project_name=project_name,
            ticket_id=ticket_id,
        )
    except FileNotFoundError as exc:
        raise _not_found(project_name) from exc
    except KeyError as exc:
        raise NotFoundError("h3_repair_ticket_not_found", ticket_id=ticket_id) from exc
