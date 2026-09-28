"""Phase 5 Repair Queue, atomic execution claim, and paid-call reservation.

This module reuses ArcReel's existing tasks table and task checkpoint column, but keeps
H3 repair jobs on a dedicated dormant media lane until Slice 4 wires the provider runtime.
That prevents the generic worker from treating an approved repair as an ordinary video
generation before the repair-specific execution adapter exists.

The paid-call boundary is deliberately conservative:

* claim grants execution ownership, not spend permission;
* reserve_provider_submission atomically consumes the approval/project allowance and
  writes the immutable pre-submit checkpoint;
* once that checkpoint exists, no caller may automatically submit again unless a persisted
  provider job identity proves the original submission can be resumed;
* a crash in the narrow checkpoint-to-provider-response gap therefore fails closed rather
  than risking duplicate supplier spend.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.base import DEFAULT_USER_ID, utc_now
from lib.db.models.h3_repair_ticket import H3RepairProjectBudget, H3RepairTicketRecord
from lib.db.models.task import Task
from lib.db.repositories.base import rowcount
from lib.reference_video.h3_repair_approval_service import (
    H3ProviderRepairApprovalBinding,
    H3RepairApprovalFacts,
    H3RepairApprovalService,
    H3RepairApprovalStaleError,
    h3_repair_approval_facts_from_ticket,
    validate_h3_repair_approval_binding,
)
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
)

H3_REPAIR_TASK_TYPE = "h3_provider_repair"
H3_REPAIR_MEDIA_TYPE = "h3_repair"
H3_REPAIR_RESOURCE_TYPE = "h3_repair_ticket"
H3_REPAIR_TASK_SOURCE = "h3_repair"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_ID_RE = re.compile(r"^h3rx_[0-9a-f]{24}$")
_CHECKPOINT_KIND = "h3_provider_repair_submit"
_LEGACY_CHECKPOINT_VERSION = 1
_CHECKPOINT_VERSION = 2


class H3RepairSubmissionDisposition(StrEnum):
    SUBMIT_ALLOWED = "submit_allowed"
    RESUME_ONLY = "resume_only"
    RESERVED_WITHOUT_PROVIDER_ID = "reserved_without_provider_id"


class H3RepairAllowanceExhausted(RuntimeError):
    """The approval or project repair-call allowance cannot fund another submission."""


class H3RepairExecutionConflict(RuntimeError):
    """Persisted task/ticket/checkpoint identity is inconsistent or concurrently owned."""


@dataclass(frozen=True)
class H3RepairProviderRequestFacts:
    """Immutable provider-request facts frozen before a paid H3 repair submission."""

    generation_type: str
    backend_model: str
    endpoint_guard: str | None
    prompt: str
    prompt_sha256: str
    duration_seconds: int
    aspect_ratio: str
    resolution: str | None
    generate_audio: bool
    service_tier: str
    seed: int | None

    _FIELDS = frozenset(
        {
            "generation_type",
            "backend_model",
            "endpoint_guard",
            "prompt",
            "prompt_sha256",
            "duration_seconds",
            "aspect_ratio",
            "resolution",
            "generate_audio",
            "service_tier",
            "seed",
        }
    )

    def __post_init__(self) -> None:
        if self.generation_type not in {"t2v", "i2v", "r2v"}:
            raise ValueError("unsupported H3 repair generation_type")
        if not self.backend_model.strip():
            raise ValueError("H3 repair backend_model is required")
        if not self.prompt.strip():
            raise ValueError("H3 repair provider prompt is required")
        _require_sha(self.prompt_sha256, "repair_prompt_sha256")
        actual = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        if actual != self.prompt_sha256:
            raise ValueError("H3 repair provider prompt SHA does not match prompt")
        if self.duration_seconds <= 0:
            raise ValueError("H3 repair duration_seconds must be positive")
        if not self.aspect_ratio.strip():
            raise ValueError("H3 repair aspect_ratio is required")
        if self.endpoint_guard is not None and not self.endpoint_guard.strip():
            raise ValueError("H3 repair endpoint_guard must be non-empty or null")
        if self.resolution is not None and not self.resolution.strip():
            raise ValueError("H3 repair resolution must be non-empty or null")
        if not self.service_tier.strip():
            raise ValueError("H3 repair service_tier is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "generation_type": self.generation_type,
            "backend_model": self.backend_model,
            "endpoint_guard": self.endpoint_guard,
            "prompt": self.prompt,
            "prompt_sha256": self.prompt_sha256,
            "duration_seconds": self.duration_seconds,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "generate_audio": self.generate_audio,
            "service_tier": self.service_tier,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, value: object) -> H3RepairProviderRequestFacts:
        if not isinstance(value, dict):
            raise H3RepairExecutionConflict("H3 repair provider request checkpoint must be an object")
        unexpected = set(value) - cls._FIELDS
        missing = cls._FIELDS - set(value)
        if unexpected or missing:
            raise H3RepairExecutionConflict(
                f"H3 repair provider request fields mismatch; missing={sorted(missing)} unexpected={sorted(unexpected)}"
            )
        return cls(
            generation_type=str(value["generation_type"]),
            backend_model=str(value["backend_model"]),
            endpoint_guard=str(value["endpoint_guard"]) if value["endpoint_guard"] is not None else None,
            prompt=str(value["prompt"]),
            prompt_sha256=str(value["prompt_sha256"]),
            duration_seconds=int(value["duration_seconds"]),
            aspect_ratio=str(value["aspect_ratio"]),
            resolution=str(value["resolution"]) if value["resolution"] is not None else None,
            generate_audio=bool(value["generate_audio"]),
            service_tier=str(value["service_tier"]),
            seed=int(value["seed"]) if value["seed"] is not None else None,
        )


@dataclass(frozen=True)
class H3RepairQueueEnqueueResult:
    task_id: str
    execution_identity: str
    task_status: str
    deduped: bool


@dataclass(frozen=True)
class H3RepairExecutionClaim:
    task_id: str
    project_name: str
    ticket_id: str
    execution_identity: str
    attempt_count: int


@dataclass(frozen=True)
class H3RepairSubmissionCheckpoint:
    schema_version: int
    kind: str
    project_name: str
    task_id: str
    execution_identity: str
    ticket_id: str
    ticket_sha256: str
    approval_sha256: str
    provider_id: str
    provider_model: str
    source_media_sha256: str
    shot_id: str
    repair_action: str
    provider_prompt_sha256: str | None
    reference_sha256: tuple[str, ...]
    provider_call_ordinal: int
    provider_request: H3RepairProviderRequestFacts | None = None

    _FIELDS_V1 = frozenset(
        {
            "schema_version",
            "kind",
            "project_name",
            "task_id",
            "execution_identity",
            "ticket_id",
            "ticket_sha256",
            "approval_sha256",
            "provider_id",
            "provider_model",
            "source_media_sha256",
            "shot_id",
            "repair_action",
            "provider_prompt_sha256",
            "reference_sha256",
            "provider_call_ordinal",
        }
    )
    _FIELDS_V2 = _FIELDS_V1 | {"provider_request"}

    def __post_init__(self) -> None:
        if self.schema_version not in {_LEGACY_CHECKPOINT_VERSION, _CHECKPOINT_VERSION}:
            raise ValueError("unsupported H3 repair submission checkpoint version")
        if self.schema_version == _LEGACY_CHECKPOINT_VERSION and self.provider_request is not None:
            raise ValueError("legacy H3 repair checkpoint cannot carry provider_request")
        if self.schema_version == _CHECKPOINT_VERSION and self.provider_request is None:
            raise ValueError("H3 repair checkpoint v2 requires provider_request")
        if self.kind != _CHECKPOINT_KIND:
            raise ValueError("invalid H3 repair submission checkpoint kind")
        if not self.project_name.strip() or not self.task_id.strip() or not self.ticket_id.strip():
            raise ValueError("checkpoint project/task/ticket identity is required")
        if not _EXECUTION_ID_RE.fullmatch(self.execution_identity):
            raise ValueError("invalid H3 repair execution identity")
        if not self.provider_id.strip() or not self.provider_model.strip():
            raise ValueError("checkpoint provider_id/provider_model is required")
        for field_name, value in (
            ("ticket_sha256", self.ticket_sha256),
            ("approval_sha256", self.approval_sha256),
            ("source_media_sha256", self.source_media_sha256),
        ):
            _require_sha(value, field_name)
        _require_optional_sha(self.provider_prompt_sha256, "provider_prompt_sha256")
        for index, value in enumerate(self.reference_sha256):
            _require_sha(value, f"reference_sha256[{index}]")
        if not self.shot_id.strip() or not self.repair_action.strip():
            raise ValueError("checkpoint shot/action is required")
        if self.provider_call_ordinal != 1:
            raise ValueError("Phase 5 approval permits exactly provider_call_ordinal=1")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "project_name": self.project_name,
            "task_id": self.task_id,
            "execution_identity": self.execution_identity,
            "ticket_id": self.ticket_id,
            "ticket_sha256": self.ticket_sha256,
            "approval_sha256": self.approval_sha256,
            "provider_id": self.provider_id,
            "provider_model": self.provider_model,
            "source_media_sha256": self.source_media_sha256,
            "shot_id": self.shot_id,
            "repair_action": self.repair_action,
            "provider_prompt_sha256": self.provider_prompt_sha256,
            "reference_sha256": list(self.reference_sha256),
            "provider_call_ordinal": self.provider_call_ordinal,
        }
        if self.schema_version == _CHECKPOINT_VERSION:
            if self.provider_request is None:
                raise H3RepairExecutionConflict("H3 repair checkpoint v2 is missing provider_request")
            result["provider_request"] = self.provider_request.to_dict()
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> H3RepairSubmissionCheckpoint:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise H3RepairExecutionConflict("H3 repair execution checkpoint must be an object")
        version = int(data.get("schema_version", 0))
        fields = cls._FIELDS_V1 if version == _LEGACY_CHECKPOINT_VERSION else cls._FIELDS_V2
        unexpected = set(data) - fields
        missing = fields - set(data)
        if unexpected or missing:
            raise H3RepairExecutionConflict(
                f"H3 repair checkpoint fields mismatch; missing={sorted(missing)} unexpected={sorted(unexpected)}"
            )
        return cls(
            schema_version=version,
            kind=str(data["kind"]),
            project_name=str(data["project_name"]),
            task_id=str(data["task_id"]),
            execution_identity=str(data["execution_identity"]),
            ticket_id=str(data["ticket_id"]),
            ticket_sha256=str(data["ticket_sha256"]),
            approval_sha256=str(data["approval_sha256"]),
            provider_id=str(data["provider_id"]),
            provider_model=str(data["provider_model"]),
            source_media_sha256=str(data["source_media_sha256"]),
            shot_id=str(data["shot_id"]),
            repair_action=str(data["repair_action"]),
            provider_prompt_sha256=(
                str(data["provider_prompt_sha256"]) if data["provider_prompt_sha256"] is not None else None
            ),
            reference_sha256=tuple(str(value) for value in data["reference_sha256"]),
            provider_call_ordinal=int(data["provider_call_ordinal"]),
            provider_request=(
                H3RepairProviderRequestFacts.from_dict(data["provider_request"])
                if version == _CHECKPOINT_VERSION
                else None
            ),
        )


@dataclass(frozen=True)
class H3RepairSubmissionReservation:
    disposition: H3RepairSubmissionDisposition
    checkpoint: H3RepairSubmissionCheckpoint
    provider_job_id: str | None
    provider_call_count: int
    project_provider_call_count: int | None


def _require_sha(value: str, field_name: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _require_optional_sha(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_sha(value, field_name)


def _approval_sha256(approval_json: str) -> str:
    return hashlib.sha256(approval_json.encode("utf-8")).hexdigest()


def _execution_identity(
    *,
    project_name: str,
    ticket_id: str,
    ticket_sha256: str,
    approval_json: str,
) -> str:
    payload = {
        "schema_version": 1,
        "project_name": project_name,
        "ticket_id": ticket_id,
        "ticket_sha256": ticket_sha256,
        "approval_sha256": _approval_sha256(approval_json),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"h3rx_{digest[:24]}"


def _task_payload(
    *,
    ticket_id: str,
    ticket_sha256: str,
    execution_identity: str,
    approval_json: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ticket_id": ticket_id,
        "ticket_sha256": ticket_sha256,
        "execution_identity": execution_identity,
        "approval_sha256": _approval_sha256(approval_json),
    }


def _decode_task_payload(task: Task) -> dict[str, Any]:
    try:
        raw = json.loads(task.payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise H3RepairExecutionConflict("H3 repair queue task payload is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise H3RepairExecutionConflict("H3 repair queue task payload must be an object")
    return raw


def _validate_task_identity(
    *,
    task: Task,
    project_name: str,
    ticket_id: str,
    ticket_sha256: str,
    execution_identity: str,
    approval_json: str,
) -> None:
    if (
        task.project_name != project_name
        or task.task_type != H3_REPAIR_TASK_TYPE
        or task.media_type != H3_REPAIR_MEDIA_TYPE
        or task.resource_type != H3_REPAIR_RESOURCE_TYPE
        or task.resource_id != execution_identity
    ):
        raise H3RepairExecutionConflict("persisted H3 repair task identity does not match Repair Ticket")
    expected = _task_payload(
        ticket_id=ticket_id,
        ticket_sha256=ticket_sha256,
        execution_identity=execution_identity,
        approval_json=approval_json,
    )
    if _decode_task_payload(task) != expected:
        raise H3RepairExecutionConflict("persisted H3 repair task payload does not match Repair Ticket approval")


def _checkpoint_for(
    *,
    project_name: str,
    task_id: str,
    execution_identity: str,
    ticket: H3RepairTicketRecord,
    binding: H3ProviderRepairApprovalBinding,
    approval_json: str,
    provider_id: str,
    provider_model: str,
    provider_request: H3RepairProviderRequestFacts | None,
) -> H3RepairSubmissionCheckpoint:
    return H3RepairSubmissionCheckpoint(
        schema_version=_CHECKPOINT_VERSION if provider_request is not None else _LEGACY_CHECKPOINT_VERSION,
        kind=_CHECKPOINT_KIND,
        project_name=project_name,
        task_id=task_id,
        execution_identity=execution_identity,
        ticket_id=ticket.ticket_id,
        ticket_sha256=ticket.ticket_sha256,
        approval_sha256=_approval_sha256(approval_json),
        provider_id=provider_id,
        provider_model=provider_model,
        source_media_sha256=binding.source_media_sha256,
        shot_id=binding.shot_id,
        repair_action=binding.repair_action,
        provider_prompt_sha256=binding.provider_prompt_sha256,
        reference_sha256=binding.reference_sha256,
        provider_call_ordinal=1,
        provider_request=provider_request,
    )


class H3RepairQueueService:
    """Repair-specific orchestration over ArcReel's shared task persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.store = H3RepairTicketStore(session)
        self.approvals = H3RepairApprovalService(session)

    async def configure_project_call_ceiling(self, *, project_name: str, ceiling: int) -> H3RepairProjectBudget:
        project_name = project_name.strip()
        if not project_name:
            raise ValueError("project_name is required")
        if ceiling < 1:
            raise ValueError("project repair-call ceiling must be >= 1")
        row = await self.session.get(H3RepairProjectBudget, project_name)
        if row is None:
            row = H3RepairProjectBudget(
                project_name=project_name,
                provider_call_ceiling=ceiling,
                provider_call_count=0,
            )
            self.session.add(row)
        else:
            if row.provider_call_count > ceiling:
                raise ValueError("project repair-call ceiling cannot be below already reserved calls")
            row.provider_call_ceiling = ceiling
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def clear_project_call_ceiling(self, *, project_name: str) -> None:
        await self.session.execute(
            delete(H3RepairProjectBudget).where(H3RepairProjectBudget.project_name == project_name)
        )
        await self.session.commit()

    async def enqueue_approved_ticket(
        self,
        *,
        project_name: str,
        ticket_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> H3RepairQueueEnqueueResult:
        persisted = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if persisted is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        if persisted.approval_json is None:
            raise RuntimeError("repair ticket has no persisted approval snapshot")

        binding = H3ProviderRepairApprovalBinding.from_json(persisted.approval_json)
        validate_h3_repair_approval_binding(persisted, binding)
        execution_identity = _execution_identity(
            project_name=project_name,
            ticket_id=ticket_id,
            ticket_sha256=persisted.ticket.ticket_sha256,
            approval_json=persisted.approval_json,
        )

        if persisted.execution_task_id is not None:
            task = await self.session.get(Task, persisted.execution_task_id)
            if task is None:
                raise H3RepairExecutionConflict("Repair Ticket points to a missing execution task")
            if persisted.execution_identity != execution_identity:
                raise H3RepairExecutionConflict("Repair Ticket execution identity no longer matches approval")
            _validate_task_identity(
                task=task,
                project_name=project_name,
                ticket_id=ticket_id,
                ticket_sha256=persisted.ticket.ticket_sha256,
                execution_identity=execution_identity,
                approval_json=persisted.approval_json,
            )
            return H3RepairQueueEnqueueResult(
                task_id=task.task_id,
                execution_identity=execution_identity,
                task_status=task.status,
                deduped=True,
            )

        if persisted.lifecycle_state is not H3RepairTicketLifecycleState.APPROVED:
            raise RuntimeError(f"repair ticket is not queueable: {persisted.lifecycle_state.value}")

        task_id = uuid.uuid4().hex
        now = utc_now()
        task = Task(
            task_id=task_id,
            project_name=project_name,
            task_type=H3_REPAIR_TASK_TYPE,
            media_type=H3_REPAIR_MEDIA_TYPE,
            resource_id=execution_identity,
            resource_type=H3_REPAIR_RESOURCE_TYPE,
            payload_json=json.dumps(
                _task_payload(
                    ticket_id=ticket_id,
                    ticket_sha256=persisted.ticket.ticket_sha256,
                    execution_identity=execution_identity,
                    approval_json=persisted.approval_json,
                ),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            status="queued",
            source=H3_REPAIR_TASK_SOURCE,
            queued_at=now,
            updated_at=now,
            user_id=user_id,
        )
        self.session.add(task)
        try:
            await self.session.flush()
            claimed = await self.session.execute(
                update(H3RepairTicketRecord)
                .where(
                    H3RepairTicketRecord.project_name == project_name,
                    H3RepairTicketRecord.ticket_id == ticket_id,
                    H3RepairTicketRecord.lifecycle_state == H3RepairTicketLifecycleState.APPROVED.value,
                    H3RepairTicketRecord.execution_task_id.is_(None),
                    H3RepairTicketRecord.execution_identity.is_(None),
                )
                .values(
                    lifecycle_state=H3RepairTicketLifecycleState.QUEUED.value,
                    lifecycle_reason="approved provider repair queued",
                    lifecycle_actor="system:repair-queue",
                    lifecycle_at=now,
                    execution_identity=execution_identity,
                    execution_task_id=task_id,
                    updated_at=now,
                )
            )
            if rowcount(claimed) != 1:
                raise H3RepairExecutionConflict("Repair Ticket was queued concurrently")
            await self.session.commit()
        except (IntegrityError, H3RepairExecutionConflict):
            await self.session.rollback()
            return await self._load_existing_execution(
                project_name=project_name,
                ticket_id=ticket_id,
                execution_identity=execution_identity,
            )

        return H3RepairQueueEnqueueResult(
            task_id=task_id,
            execution_identity=execution_identity,
            task_status="queued",
            deduped=False,
        )

    async def _load_existing_execution(
        self,
        *,
        project_name: str,
        ticket_id: str,
        execution_identity: str,
    ) -> H3RepairQueueEnqueueResult:
        persisted = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if (
            persisted is None
            or persisted.approval_json is None
            or persisted.execution_identity != execution_identity
            or persisted.execution_task_id is None
        ):
            raise H3RepairExecutionConflict("concurrent repair enqueue did not resolve to one persisted execution")
        task = await self.session.get(Task, persisted.execution_task_id)
        if task is None:
            raise H3RepairExecutionConflict("concurrent repair enqueue persisted no execution task")
        _validate_task_identity(
            task=task,
            project_name=project_name,
            ticket_id=ticket_id,
            ticket_sha256=persisted.ticket.ticket_sha256,
            execution_identity=execution_identity,
            approval_json=persisted.approval_json,
        )
        return H3RepairQueueEnqueueResult(
            task_id=task.task_id,
            execution_identity=execution_identity,
            task_status=task.status,
            deduped=True,
        )

    async def claim_next(self) -> H3RepairExecutionClaim | None:
        """Atomically claim one queued Repair Ticket plus its shared task row.

        The first write is a single UPDATE whose candidate task is a scalar subquery.
        This avoids the read-then-write upgrade race that is especially problematic for
        concurrent SQLite workers. PostgreSQL likewise rechecks the guarded row after lock
        acquisition. The task status update is in the same transaction; any mismatch rolls
        the ticket claim back.
        """

        candidate_task_id = (
            select(Task.task_id)
            .join(
                H3RepairTicketRecord,
                H3RepairTicketRecord.execution_task_id == Task.task_id,
            )
            .where(
                Task.task_type == H3_REPAIR_TASK_TYPE,
                Task.media_type == H3_REPAIR_MEDIA_TYPE,
                Task.status == "queued",
                H3RepairTicketRecord.lifecycle_state == H3RepairTicketLifecycleState.QUEUED.value,
            )
            .order_by(Task.queued_at, Task.task_id)
            .limit(1)
            .scalar_subquery()
        )
        now = utc_now()
        ticket_update = await self.session.execute(
            update(H3RepairTicketRecord)
            .where(
                H3RepairTicketRecord.lifecycle_state == H3RepairTicketLifecycleState.QUEUED.value,
                H3RepairTicketRecord.execution_task_id == candidate_task_id,
            )
            .values(
                lifecycle_state=H3RepairTicketLifecycleState.RUNNING.value,
                lifecycle_reason="repair execution atomically claimed",
                lifecycle_actor="system:repair-worker",
                lifecycle_at=now,
                attempt_count=H3RepairTicketRecord.attempt_count + 1,
                updated_at=now,
            )
            .returning(
                H3RepairTicketRecord.project_name,
                H3RepairTicketRecord.ticket_id,
                H3RepairTicketRecord.execution_task_id,
                H3RepairTicketRecord.execution_identity,
                H3RepairTicketRecord.attempt_count,
            )
        )
        claimed_row = ticket_update.first()
        if claimed_row is None:
            await self.session.rollback()
            return None

        project_name = str(claimed_row.project_name)
        ticket_id = str(claimed_row.ticket_id)
        task_id = str(claimed_row.execution_task_id)
        execution_identity = str(claimed_row.execution_identity)
        attempt_count = int(claimed_row.attempt_count)

        persisted = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if persisted is None or persisted.approval_json is None:
            await self.session.rollback()
            raise H3RepairExecutionConflict("queued H3 repair task has no persisted approval")
        if not _EXECUTION_ID_RE.fullmatch(execution_identity):
            await self.session.rollback()
            raise H3RepairExecutionConflict("claimed Repair Ticket has invalid execution identity")

        await self.approvals.validate_for_execution(
            project_name=project_name,
            ticket_id=ticket_id,
            current_facts=h3_repair_approval_facts_from_ticket(persisted),
        )
        task = await self.session.get(Task, task_id)
        if task is None:
            await self.session.rollback()
            raise H3RepairExecutionConflict("claimed Repair Ticket points to a missing task")
        _validate_task_identity(
            task=task,
            project_name=project_name,
            ticket_id=ticket_id,
            ticket_sha256=persisted.ticket.ticket_sha256,
            execution_identity=execution_identity,
            approval_json=persisted.approval_json,
        )

        task_update = await self.session.execute(
            update(Task)
            .where(
                Task.task_id == task_id,
                Task.status == "queued",
                Task.task_type == H3_REPAIR_TASK_TYPE,
                Task.resource_id == execution_identity,
            )
            .values(status="running", started_at=now, updated_at=now)
        )
        if rowcount(task_update) != 1:
            await self.session.rollback()
            return None
        await self.session.commit()

        return H3RepairExecutionClaim(
            task_id=task_id,
            project_name=project_name,
            ticket_id=ticket_id,
            execution_identity=execution_identity,
            attempt_count=attempt_count,
        )

    async def reserve_provider_submission(
        self,
        *,
        project_name: str,
        ticket_id: str,
        current_facts: H3RepairApprovalFacts,
        provider_id: str,
        provider_model: str,
        provider_request: H3RepairProviderRequestFacts | None = None,
    ) -> H3RepairSubmissionReservation:
        provider_id = provider_id.strip()
        provider_model = provider_model.strip()
        if not provider_id or not provider_model:
            raise ValueError("provider_id and provider_model are required")
        persisted = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if persisted is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        if persisted.execution_task_id is None or persisted.execution_identity is None:
            raise H3RepairExecutionConflict("Repair Ticket has no claimed execution task")
        task = await self.session.get(Task, persisted.execution_task_id)
        if task is None:
            raise H3RepairExecutionConflict("Repair Ticket execution task is missing")
        if task.status != "running" or persisted.lifecycle_state is not H3RepairTicketLifecycleState.RUNNING:
            raise H3RepairExecutionConflict("paid submission reservation requires running task and ticket")
        if persisted.approval_json is None:
            raise H3RepairExecutionConflict("running Repair Ticket has no approval snapshot")

        try:
            validated = await self.approvals.validate_for_execution(
                project_name=project_name,
                ticket_id=ticket_id,
                current_facts=current_facts,
            )
        except H3RepairApprovalStaleError:
            now = utc_now()
            await self.session.execute(
                update(Task)
                .where(Task.task_id == task.task_id, Task.status == "running")
                .values(
                    status="failed",
                    error_message="h3_repair_stale_approval_pre_submit",
                    finished_at=now,
                    updated_at=now,
                )
            )
            await self.session.commit()
            raise

        binding = validated.approval
        expected_checkpoint = _checkpoint_for(
            project_name=project_name,
            task_id=task.task_id,
            execution_identity=persisted.execution_identity,
            ticket=await self._ticket_record(project_name=project_name, ticket_id=ticket_id),
            binding=binding,
            approval_json=persisted.approval_json,
            provider_id=provider_id,
            provider_model=provider_model,
            provider_request=provider_request,
        )

        if task.execution_checkpoint_json is not None:
            checkpoint = H3RepairSubmissionCheckpoint.from_json(task.execution_checkpoint_json)
            if checkpoint != expected_checkpoint:
                raise H3RepairExecutionConflict("persisted H3 repair checkpoint conflicts with current execution")
            # The ticket snapshot above may have been read before a concurrent reservation
            # committed, while the later task read already observes that reservation's
            # checkpoint. Re-read only the mutable allowance counter from the database so
            # the committed checkpoint+counter transaction is observed consistently.
            reserved_call_count = await self.session.scalar(
                select(H3RepairTicketRecord.provider_call_count).where(
                    H3RepairTicketRecord.project_name == project_name,
                    H3RepairTicketRecord.ticket_id == ticket_id,
                )
            )
            if reserved_call_count is None:
                raise H3RepairExecutionConflict("checkpoint exists for a missing Repair Ticket")
            if reserved_call_count < 1:
                raise H3RepairExecutionConflict("checkpoint exists without consumed provider-call allowance")
            return H3RepairSubmissionReservation(
                disposition=(
                    H3RepairSubmissionDisposition.RESUME_ONLY
                    if task.provider_job_id
                    else H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID
                ),
                checkpoint=checkpoint,
                provider_job_id=task.provider_job_id,
                provider_call_count=int(reserved_call_count),
                project_provider_call_count=await self._project_budget_count(project_name),
            )

        if task.provider_job_id is not None:
            raise H3RepairExecutionConflict("provider job identity exists without H3 pre-submit checkpoint")
        if persisted.max_provider_calls is None or persisted.max_provider_calls < 1:
            await self._block_allowance(
                persisted.execution_task_id,
                project_name=project_name,
                ticket_id=ticket_id,
                reason="Repair Ticket has no positive provider-call allowance",
            )
            raise H3RepairAllowanceExhausted("Repair Ticket has no positive provider-call allowance")
        if persisted.provider_call_count >= persisted.max_provider_calls:
            await self._block_allowance(
                persisted.execution_task_id,
                project_name=project_name,
                ticket_id=ticket_id,
                reason="Repair Ticket provider-call allowance is exhausted",
            )
            raise H3RepairAllowanceExhausted("Repair Ticket provider-call allowance is exhausted")

        budget = await self.session.get(H3RepairProjectBudget, project_name)
        if budget is not None:
            budget_update = await self.session.execute(
                update(H3RepairProjectBudget)
                .where(
                    H3RepairProjectBudget.project_name == project_name,
                    H3RepairProjectBudget.provider_call_count < H3RepairProjectBudget.provider_call_ceiling,
                )
                .values(
                    provider_call_count=H3RepairProjectBudget.provider_call_count + 1,
                    updated_at=utc_now(),
                )
            )
            if rowcount(budget_update) != 1:
                await self.session.rollback()
                await self._block_allowance(
                    persisted.execution_task_id,
                    project_name=project_name,
                    ticket_id=ticket_id,
                    reason="project H3 repair-call ceiling is exhausted",
                )
                raise H3RepairAllowanceExhausted("project H3 repair-call ceiling is exhausted")

        ticket_update = await self.session.execute(
            update(H3RepairTicketRecord)
            .where(
                H3RepairTicketRecord.project_name == project_name,
                H3RepairTicketRecord.ticket_id == ticket_id,
                H3RepairTicketRecord.lifecycle_state == H3RepairTicketLifecycleState.RUNNING.value,
                H3RepairTicketRecord.execution_identity == persisted.execution_identity,
                H3RepairTicketRecord.execution_task_id == task.task_id,
                H3RepairTicketRecord.provider_call_count < H3RepairTicketRecord.max_provider_calls,
            )
            .values(
                provider_call_count=H3RepairTicketRecord.provider_call_count + 1,
                updated_at=utc_now(),
            )
        )
        if rowcount(ticket_update) != 1:
            await self.session.rollback()
            return await self._reservation_after_conflict(
                project_name=project_name,
                ticket_id=ticket_id,
                expected_checkpoint=expected_checkpoint,
            )

        task_update = await self.session.execute(
            update(Task)
            .where(
                Task.task_id == task.task_id,
                Task.status == "running",
                Task.task_type == H3_REPAIR_TASK_TYPE,
                Task.execution_checkpoint_json.is_(None),
                Task.provider_job_id.is_(None),
            )
            .values(
                execution_checkpoint_json=expected_checkpoint.to_json(),
                provider_id=provider_id,
                updated_at=utc_now(),
            )
        )
        if rowcount(task_update) != 1:
            await self.session.rollback()
            return await self._reservation_after_conflict(
                project_name=project_name,
                ticket_id=ticket_id,
                expected_checkpoint=expected_checkpoint,
            )

        await self.session.commit()
        refreshed = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if refreshed is None:
            raise H3RepairExecutionConflict("Repair Ticket disappeared after paid-call reservation")
        return H3RepairSubmissionReservation(
            disposition=H3RepairSubmissionDisposition.SUBMIT_ALLOWED,
            checkpoint=expected_checkpoint,
            provider_job_id=None,
            provider_call_count=refreshed.provider_call_count,
            project_provider_call_count=await self._project_budget_count(project_name),
        )

    async def _reservation_after_conflict(
        self,
        *,
        project_name: str,
        ticket_id: str,
        expected_checkpoint: H3RepairSubmissionCheckpoint,
    ) -> H3RepairSubmissionReservation:
        persisted = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if persisted is None or persisted.execution_task_id is None:
            raise H3RepairExecutionConflict("concurrent provider reservation lost Repair Ticket execution identity")
        task = await self.session.get(Task, persisted.execution_task_id)
        if task is None or task.execution_checkpoint_json is None:
            raise H3RepairAllowanceExhausted("provider-call allowance was consumed by another execution")
        checkpoint = H3RepairSubmissionCheckpoint.from_json(task.execution_checkpoint_json)
        if checkpoint != expected_checkpoint:
            raise H3RepairExecutionConflict("concurrent provider reservation checkpoint identity differs")
        return H3RepairSubmissionReservation(
            disposition=(
                H3RepairSubmissionDisposition.RESUME_ONLY
                if task.provider_job_id
                else H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID
            ),
            checkpoint=checkpoint,
            provider_job_id=task.provider_job_id,
            provider_call_count=persisted.provider_call_count,
            project_provider_call_count=await self._project_budget_count(project_name),
        )

    async def _block_allowance(
        self,
        task_id: str,
        *,
        project_name: str,
        ticket_id: str,
        reason: str,
    ) -> None:
        """Fail the queue task and move the ticket to human review without spending."""

        now = utc_now()
        ticket_update = await self.session.execute(
            update(H3RepairTicketRecord)
            .where(
                H3RepairTicketRecord.project_name == project_name,
                H3RepairTicketRecord.ticket_id == ticket_id,
                H3RepairTicketRecord.lifecycle_state == H3RepairTicketLifecycleState.RUNNING.value,
            )
            .values(
                lifecycle_state=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED.value,
                lifecycle_reason=reason,
                lifecycle_actor="system:repair-budget",
                lifecycle_at=now,
                updated_at=now,
            )
        )
        if rowcount(ticket_update) == 1:
            await self.session.execute(
                update(Task)
                .where(Task.task_id == task_id, Task.status == "running")
                .values(
                    status="failed",
                    error_message="h3_repair_allowance_exhausted",
                    finished_at=now,
                    updated_at=now,
                )
            )
            await self.session.commit()
        else:
            await self.session.rollback()

    async def persist_provider_job_identity(
        self,
        *,
        project_name: str,
        ticket_id: str,
        provider_job_id: str,
        endpoint: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if not provider_job_id.strip():
            raise ValueError("provider_job_id is required")
        persisted = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if (
            persisted is None
            or persisted.execution_task_id is None
            or persisted.execution_identity is None
            or persisted.lifecycle_state is not H3RepairTicketLifecycleState.RUNNING
        ):
            raise H3RepairExecutionConflict("Repair Ticket is not a running claimed execution")
        task = await self.session.get(Task, persisted.execution_task_id)
        if task is None or task.execution_checkpoint_json is None:
            raise H3RepairExecutionConflict("provider job identity cannot exist before submission checkpoint")
        checkpoint = H3RepairSubmissionCheckpoint.from_json(task.execution_checkpoint_json)
        if checkpoint.execution_identity != persisted.execution_identity:
            raise H3RepairExecutionConflict("provider job checkpoint execution identity mismatch")
        if task.provider_job_id is not None:
            if task.provider_job_id == provider_job_id:
                return
            raise H3RepairExecutionConflict("a different provider job identity is already persisted")

        values: dict[str, object] = {
            "provider_job_id": provider_job_id,
            "updated_at": utc_now(),
        }
        if endpoint is not None:
            values["provider_endpoint"] = endpoint
        if base_url is not None:
            values["submitted_base_url"] = base_url
        result = await self.session.execute(
            update(Task)
            .where(
                Task.task_id == task.task_id,
                Task.status == "running",
                Task.task_type == H3_REPAIR_TASK_TYPE,
                Task.execution_checkpoint_json == task.execution_checkpoint_json,
                Task.provider_job_id.is_(None),
            )
            .values(**values)
        )
        if rowcount(result) != 1:
            await self.session.rollback()
            refreshed = await self.session.get(Task, task.task_id)
            if refreshed is not None and refreshed.provider_job_id == provider_job_id:
                return
            raise H3RepairExecutionConflict("provider job identity persistence guard rejected execution")
        await self.session.commit()

    async def _ticket_record(self, *, project_name: str, ticket_id: str) -> H3RepairTicketRecord:
        record = await self.session.get(H3RepairTicketRecord, (project_name, ticket_id))
        if record is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        return record

    async def _project_budget_count(self, project_name: str) -> int | None:
        row = await self.session.get(H3RepairProjectBudget, project_name)
        return row.provider_call_count if row is not None else None
