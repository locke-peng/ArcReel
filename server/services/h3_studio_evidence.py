"""Phase 6 Slice 7 deterministic project evidence export.

The bundle is a read-only reconstruction over accepted Phase 5/6 persisted facts. Raw
provider checkpoints are never exported; only their SHA-256 digest is retained.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from typing import Any

from lib.db import safe_session_factory
from lib.db.models.h3_repair_ticket import H3RepairProjectControl
from lib.db.models.task import Task
from lib.project_manager import ProjectManager
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketStore, PersistedH3RepairTicket
from server.services.h3_production_control import resolve_h3_production_projection
from server.services.h3_repair_budget_ledger import resolve_h3_repair_project_ledger


def _iso(value: object) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else None


def _approval_payload(ticket: PersistedH3RepairTicket) -> dict[str, Any] | None:
    if ticket.approval_json is None:
        return None
    try:
        payload = json.loads(ticket.approval_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("persisted H3 repair approval is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("persisted H3 repair approval must be an object")
    return payload


def _checkpoint_sha256(task: Task | None) -> str | None:
    if task is None or task.execution_checkpoint_json is None:
        return None
    return hashlib.sha256(task.execution_checkpoint_json.encode("utf-8")).hexdigest()


def _ticket_evidence(ticket: PersistedH3RepairTicket, task: Task | None) -> dict[str, Any]:
    if ticket.execution_task_id is not None and task is None:
        raise RuntimeError(f"H3 repair evidence lineage is missing task {ticket.execution_task_id}")
    return {
        "repair_ticket": ticket.ticket.to_dict(),
        "lifecycle": {
            "state": ticket.lifecycle_state.value,
            "reason": ticket.lifecycle_reason,
            "actor": ticket.lifecycle_actor,
            "at": _iso(ticket.lifecycle_at),
        },
        "approval": _approval_payload(ticket),
        "execution": {
            "execution_identity": ticket.execution_identity,
            "task_id": ticket.execution_task_id,
            "attempt_count": ticket.attempt_count,
            "provider_call_count": ticket.provider_call_count,
            "task_status": task.status if task is not None else None,
            "provider_id": task.provider_id if task is not None else None,
            "provider_job_id": task.provider_job_id if task is not None else None,
            "checkpoint_sha256": _checkpoint_sha256(task),
            "queued_at": _iso(task.queued_at) if task is not None else None,
            "started_at": _iso(task.started_at) if task is not None else None,
            "finished_at": _iso(task.finished_at) if task is not None else None,
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


def _bundle_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def get_h3_studio_evidence_bundle(
    *,
    project_name: str,
    project_manager: ProjectManager | None = None,
    tested_sha: str | None = None,
) -> dict[str, Any]:
    """Reconstruct one deterministic project-scale H3 evidence bundle."""

    projection = await resolve_h3_production_projection(
        project_name=project_name,
        project_manager=project_manager,
    )
    ledger = await resolve_h3_repair_project_ledger(project_name=project_name)

    async with safe_session_factory() as session:
        tickets = await H3RepairTicketStore(session).list_for_project(
            project_name=projection.project_name,
            limit=500,
        )
        control = await session.get(H3RepairProjectControl, projection.project_name)
        tasks: dict[str, Task] = {}
        for ticket in tickets:
            task_id = ticket.execution_task_id
            if task_id is None or task_id in tasks:
                continue
            task = await session.get(Task, task_id)
            if task is not None:
                tasks[task_id] = task

    resolved_sha = (
        tested_sha
        or os.environ.get("H3_PHASE6_TESTED_SHA")
        or os.environ.get("ARCREEL_BUILD_SHA")
        or os.environ.get("GITHUB_SHA")
    )
    if resolved_sha is not None:
        resolved_sha = resolved_sha.strip() or None

    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3_phase6_project_evidence",
        "project_name": projection.project_name,
        "tested_sha": resolved_sha,
        "production_projection": asdict(projection),
        "project_control": {
            "paused": control.paused if control is not None else False,
            "max_running_tasks": control.max_running_tasks if control is not None else None,
            "explicit": control is not None,
        },
        "budget_ledger": asdict(ledger),
        "tickets": [
            _ticket_evidence(
                ticket,
                tasks.get(ticket.execution_task_id)
                if ticket.execution_task_id is not None
                else None,
            )
            for ticket in sorted(tickets, key=lambda item: item.ticket.ticket_id)
        ],
    }
    return {**payload, "bundle_sha256": _bundle_sha256(payload)}
