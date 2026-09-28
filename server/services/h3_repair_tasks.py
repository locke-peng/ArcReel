"""Phase 5 H3 provider-repair task execution.

This service adapts one persisted/claimed Repair Ticket to ArcReel's existing video backend
stack, then hands the completed provider shot to the Phase 4 shot-scoped executor for
scope-locked deterministic reassembly. Slice 5 continues from REQA_RUNNING through the trusted
Phase 4 runtime gate and formal-selection service. This module never selects a repair action.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from lib.config.resolver import VideoGenerationType
from lib.config.service import DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS
from lib.db import safe_session_factory
from lib.db.base import DEFAULT_USER_ID, utc_now
from lib.db.models.h3_repair_ticket import H3RepairTicketRecord
from lib.db.repositories.task_repo import TaskRepository
from lib.path_safety import safe_join
from lib.project_manager import get_project_manager
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_provider_repair_runtime import (
    assemble_h3_shot_window,
    build_h3_shot_repair_prompt,
    resolve_h3_repair_source_version,
)
from lib.reference_video.h3_repair_approval_service import (
    H3ProviderRepairApprovalBinding,
    H3RepairApprovalFacts,
)
from lib.reference_video.h3_repair_queue import (
    H3_REPAIR_TASK_TYPE,
    H3RepairExecutionConflict,
    H3RepairProviderRequestFacts,
    H3RepairQueueService,
    H3RepairSubmissionCheckpoint,
    H3RepairSubmissionDisposition,
)
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
    validate_h3_repair_ticket_transition,
)
from lib.reference_video.h3_shot_repair_executor import (
    H3ShotRepairExecutionResult,
    build_h3_shot_repair_request,
    execute_h3_shot_scoped_provider_repair,
)
from lib.resource_paths import H3_REPAIR_SHOT_RESOURCE_TYPE, resource_relative_path
from server.services.generation_context import VideoLaneRequest, resolve_generation_context
from server.services.h3_repair_reqa import execute_h3_repair_reqa


async def _load_persisted_ticket(project_name: str, ticket_id: str):
    async with safe_session_factory() as session:
        ticket = await H3RepairTicketStore(session).load(project_name=project_name, ticket_id=ticket_id)
    if ticket is None:
        raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
    return ticket


async def _load_task_snapshot(task_id: str) -> dict[str, Any] | None:
    async with safe_session_factory() as session:
        return await TaskRepository(session).get(task_id)


async def _transition_ticket(
    *,
    project_name: str,
    ticket_id: str,
    target: H3RepairTicketLifecycleState,
    reason: str,
    actor: str,
    repair_output_sha256: str | None = None,
) -> None:
    async with safe_session_factory() as session:
        record = await session.get(H3RepairTicketRecord, (project_name, ticket_id))
        if record is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        current = H3RepairTicketLifecycleState(record.lifecycle_state)
        validate_h3_repair_ticket_transition(current, target)
        if current is not target:
            record.lifecycle_state = target.value
        record.lifecycle_reason = reason
        record.lifecycle_actor = actor
        record.lifecycle_at = utc_now()
        record.updated_at = utc_now()
        if repair_output_sha256 is not None:
            record.repair_output_sha256 = repair_output_sha256
        await session.commit()


async def _mark_human_review_if_active(*, project_name: str, ticket_id: str, reason: str) -> None:
    async with safe_session_factory() as session:
        record = await session.get(H3RepairTicketRecord, (project_name, ticket_id))
        if record is None:
            return
        current = H3RepairTicketLifecycleState(record.lifecycle_state)
        if current not in {
            H3RepairTicketLifecycleState.RUNNING,
            H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            H3RepairTicketLifecycleState.REASSEMBLING,
            H3RepairTicketLifecycleState.REQA_RUNNING,
        }:
            return
        validate_h3_repair_ticket_transition(current, H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED)
        now = utc_now()
        record.lifecycle_state = H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED.value
        record.lifecycle_reason = reason
        record.lifecycle_actor = "system:repair-runtime"
        record.lifecycle_at = now
        record.updated_at = now
        await session.commit()


async def _record_repair_cancellation(*, project_name: str, ticket_id: str) -> None:
    """Keep ticket lifecycle consistent with worker cancellation semantics."""

    async with safe_session_factory() as session:
        record = await session.get(H3RepairTicketRecord, (project_name, ticket_id))
        if record is None:
            return
        current = H3RepairTicketLifecycleState(record.lifecycle_state)
        if current is H3RepairTicketLifecycleState.RUNNING:
            target = H3RepairTicketLifecycleState.CANCELLED
            reason = "repair execution cancelled before provider completion"
        elif current in {
            H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            H3RepairTicketLifecycleState.REASSEMBLING,
        }:
            target = H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED
            reason = "repair execution cancelled after provider completion; inspect retained paid artifact"
        else:
            return
        validate_h3_repair_ticket_transition(current, target)
        now = utc_now()
        record.lifecycle_state = target.value
        record.lifecycle_reason = reason
        record.lifecycle_actor = "system:repair-runtime"
        record.lifecycle_at = now
        record.updated_at = now
        await session.commit()


def _ticket_id_from_task(task: dict[str, Any]) -> str:
    payload = task.get("payload")
    if not isinstance(payload, dict):
        raise H3RepairExecutionConflict("H3 repair task payload is missing")
    ticket_id = payload.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        raise H3RepairExecutionConflict("H3 repair task payload has no ticket_id")
    return ticket_id.strip()


def _integer_duration(seconds: float) -> int:
    rounded = round(seconds)
    if rounded <= 0 or abs(seconds - rounded) > 1e-6:
        raise RuntimeError("H3 repair provider duration must be a positive whole number of seconds")
    return int(rounded)


def _resolver_payload(provider_id: str, provider_model: str, generation_type: str) -> dict[str, str]:
    if generation_type not in {"i2v", "r2v"}:
        raise RuntimeError(f"unsupported H3 repair generation bucket: {generation_type}")
    return {
        f"video_provider_{generation_type}": f"{provider_id}/{provider_model}",
    }


async def _resolve_provider_context(
    *,
    project_name: str,
    project: dict[str, Any],
    user_id: str,
    provider_id: str,
    provider_model: str,
    provider_request: H3RepairProviderRequestFacts,
):
    generation_type = cast(VideoGenerationType, provider_request.generation_type)
    ctx = await resolve_generation_context(
        project_name,
        _resolver_payload(provider_id, provider_model, provider_request.generation_type),
        project=project,
        user_id=user_id,
        video=VideoLaneRequest(generation_type=generation_type),
    )
    actual = (
        ctx.video.provider_model.provider_id,
        ctx.video.provider_model.model_id,
        ctx.video.backend_model,
        ctx.video.endpoint,
    )
    expected = (
        provider_id,
        provider_model,
        provider_request.backend_model,
        provider_request.endpoint_guard,
    )
    if actual != expected:
        raise H3RepairExecutionConflict(
            "resolved provider/model/backend/endpoint identity differs from frozen H3 repair request"
        )
    if len(provider_request.prompt) > ctx.video.max_prompt_chars:
        raise RuntimeError(
            f"H3 repair prompt is {len(provider_request.prompt)} characters; "
            f"provider limit is {ctx.video.max_prompt_chars}"
        )
    return ctx


async def _strict_job_persistence(
    *,
    project_name: str,
    ticket_id: str,
    job_id: str,
    endpoint: str | None,
    base_url: str | None,
) -> None:
    async with safe_session_factory() as session:
        await H3RepairQueueService(session).persist_provider_job_identity(
            project_name=project_name,
            ticket_id=ticket_id,
            provider_job_id=job_id,
            endpoint=endpoint,
            base_url=base_url,
        )


async def _reserve_fresh_submission(
    *,
    project_name: str,
    ticket_id: str,
    current_facts: H3RepairApprovalFacts,
    provider_id: str,
    provider_model: str,
    provider_request: H3RepairProviderRequestFacts,
):
    async with safe_session_factory() as session:
        return await H3RepairQueueService(session).reserve_provider_submission(
            project_name=project_name,
            ticket_id=ticket_id,
            current_facts=current_facts,
            provider_id=provider_id,
            provider_model=provider_model,
            provider_request=provider_request,
        )


async def _provider_shot_from_fresh_submission(
    *,
    task: dict[str, Any],
    project_name: str,
    ticket_id: str,
    execution_identity: str,
    source,
    current_facts: H3RepairApprovalFacts,
    provider_request: H3RepairProviderRequestFacts,
    project: dict[str, Any],
) -> Path:
    user_id = str(task.get("user_id") or DEFAULT_USER_ID)
    ctx = await _resolve_provider_context(
        project_name=project_name,
        project=project,
        user_id=user_id,
        provider_id=source.provider_id,
        provider_model=source.provider_model,
        provider_request=provider_request,
    )

    reservation_box: dict[str, object] = {}

    async def _before_submit() -> dict[str, object]:
        reservation = await _reserve_fresh_submission(
            project_name=project_name,
            ticket_id=ticket_id,
            current_facts=current_facts,
            provider_id=source.provider_id,
            provider_model=source.provider_model,
            provider_request=provider_request,
        )
        if reservation.disposition is not H3RepairSubmissionDisposition.SUBMIT_ALLOWED:
            raise H3RepairExecutionConflict(
                f"fresh H3 repair submit was not authorized: {reservation.disposition.value}"
            )
        reservation_box["reservation"] = reservation
        return {
            "h3_repair_ticket_id": ticket_id,
            "h3_repair_execution_identity": execution_identity,
            "h3_repair_checkpoint_schema_version": reservation.checkpoint.schema_version,
            "h3_repair_prompt_sha256": provider_request.prompt_sha256,
            "h3_repair_source_media_sha256": source.media_sha256,
            "h3_repair_source_version": source.version,
        }

    async def _persist_job(job_id: str, endpoint: str | None, base_url: str | None) -> None:
        await _strict_job_persistence(
            project_name=project_name,
            ticket_id=ticket_id,
            job_id=job_id,
            endpoint=endpoint,
            base_url=base_url,
        )

    output_path, _version, _video_ref, _video_uri = await ctx.generator.generate_video_async(
        prompt=provider_request.prompt,
        resource_type=H3_REPAIR_SHOT_RESOURCE_TYPE,
        resource_id=execution_identity,
        reference_images=list(source.reference_images) or None,
        reference_audio_files=list(source.reference_audio_files) or None,
        reference_audio_targets=(
            list(source.reference_audio_targets) if source.reference_audio_targets is not None else None
        ),
        aspect_ratio=provider_request.aspect_ratio,
        duration_seconds=provider_request.duration_seconds,
        resolution=provider_request.resolution,
        task_id=str(task["task_id"]),
        before_submit=_before_submit,
        on_provider_job_id=_persist_job,
        formal_output=False,
        generate_audio=provider_request.generate_audio,
        service_tier=provider_request.service_tier,
        seed=provider_request.seed,
        poll_timeout_seconds=int(task.get("video_poll_timeout_seconds") or DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS),
    )
    if "reservation" not in reservation_box:
        raise H3RepairExecutionConflict("provider generation completed without H3 repair reservation")
    return output_path


async def _provider_shot_from_resume(
    *,
    task: dict[str, Any],
    project_name: str,
    ticket_id: str,
    checkpoint: H3RepairSubmissionCheckpoint,
    current_facts: H3RepairApprovalFacts,
    project: dict[str, Any],
) -> Path:
    provider_request = checkpoint.provider_request
    if provider_request is None:
        raise H3RepairExecutionConflict(
            "legacy H3 repair checkpoint has no frozen provider request; automatic resubmit/resume is blocked"
        )

    async with safe_session_factory() as session:
        reservation = await H3RepairQueueService(session).reserve_provider_submission(
            project_name=project_name,
            ticket_id=ticket_id,
            current_facts=current_facts,
            provider_id=checkpoint.provider_id,
            provider_model=checkpoint.provider_model,
            provider_request=provider_request,
        )
    if reservation.disposition is H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID:
        raise H3RepairExecutionConflict(
            "H3 repair checkpoint exists without provider job identity; automatic resubmit is forbidden"
        )
    if reservation.disposition is not H3RepairSubmissionDisposition.RESUME_ONLY:
        raise H3RepairExecutionConflict(
            f"unexpected H3 repair resume disposition: {reservation.disposition.value}"
        )
    job_id = reservation.provider_job_id
    if not job_id:
        raise H3RepairExecutionConflict("H3 repair resume has no provider job identity")

    user_id = str(task.get("user_id") or DEFAULT_USER_ID)
    ctx = await _resolve_provider_context(
        project_name=project_name,
        project=project,
        user_id=user_id,
        provider_id=checkpoint.provider_id,
        provider_model=checkpoint.provider_model,
        provider_request=provider_request,
    )
    output_path, _version, _video_ref, _video_uri = await ctx.generator.resume_video_async(
        job_id=job_id,
        resource_type=H3_REPAIR_SHOT_RESOURCE_TYPE,
        resource_id=checkpoint.execution_identity,
        prompt=provider_request.prompt,
        aspect_ratio=provider_request.aspect_ratio,
        duration_seconds=provider_request.duration_seconds,
        resolution=provider_request.resolution,
        task_id=str(task["task_id"]),
        submitted_base_url=(
            str(task["submitted_base_url"]) if isinstance(task.get("submitted_base_url"), str) else None
        ),
        formal_output=False,
        generate_audio=provider_request.generate_audio,
        service_tier=provider_request.service_tier,
        seed=provider_request.seed,
        h3_repair_ticket_id=ticket_id,
        h3_repair_execution_identity=checkpoint.execution_identity,
        h3_repair_checkpoint_schema_version=checkpoint.schema_version,
        h3_repair_prompt_sha256=provider_request.prompt_sha256,
        h3_repair_source_media_sha256=checkpoint.source_media_sha256,
        poll_timeout_seconds=int(task.get("video_poll_timeout_seconds") or DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS),
    )
    return output_path


def _assemble_completed_provider_shot(
    *,
    ticket,
    approval: H3ProviderRepairApprovalBinding,
    source_media: Path,
    provider_shot: Path,
    output_media: Path,
) -> H3ShotRepairExecutionResult:
    return execute_h3_shot_scoped_provider_repair(
        ticket=ticket,
        approval=approval.to_phase4_approval(),
        source_unit_media=source_media,
        output_unit_media=output_media,
        provider_runner=lambda _request: provider_shot,
        assembly_runner=assemble_h3_shot_window,
    )


async def execute_h3_repair_task(task: dict[str, Any]) -> dict[str, Any]:
    """Execute or safely resume one already-claimed Phase 5 H3 repair task."""

    if task.get("task_type") != H3_REPAIR_TASK_TYPE:
        raise ValueError("execute_h3_repair_task requires h3_provider_repair task")
    project_name = str(task.get("project_name") or "").strip()
    if not project_name:
        raise ValueError("H3 repair task has no project_name")
    ticket_id = _ticket_id_from_task(task)

    latest = await _load_task_snapshot(str(task["task_id"]))
    if latest is not None:
        task = latest

    persisted = await _load_persisted_ticket(project_name, ticket_id)
    if persisted.execution_identity is None:
        raise H3RepairExecutionConflict("H3 repair ticket is missing execution identity")

    if persisted.lifecycle_state in {
        H3RepairTicketLifecycleState.ACCEPTED,
        H3RepairTicketLifecycleState.REJECTED,
        H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
    } and persisted.reqa_outcome is not None:
        return {
            "execution_identity": persisted.execution_identity,
            "lifecycle_state": persisted.lifecycle_state.value,
            "output_media_path": f"repairs/reassembled_units/{persisted.execution_identity}.mp4",
            "provider_shot_path": resource_relative_path(
                H3_REPAIR_SHOT_RESOURCE_TYPE,
                persisted.execution_identity,
            ),
            "reqa": {
                "ticket_id": ticket_id,
                "execution_identity": persisted.execution_identity,
                "reqa_outcome": persisted.reqa_outcome,
                "lifecycle_state": persisted.lifecycle_state.value,
                "selected_current": persisted.lifecycle_state is H3RepairTicketLifecycleState.ACCEPTED,
                "selected_artifact_id": persisted.selected_artifact_id,
                "selected_version_id": persisted.selected_version_id,
            },
            "recovered_terminal_reqa": True,
        }

    if persisted.lifecycle_state is H3RepairTicketLifecycleState.REQA_RUNNING:
        output_media = safe_join(
            get_project_manager().get_project_path(project_name),
            "repairs",
            "reassembled_units",
            f"{persisted.execution_identity}.mp4",
            require_file=True,
        )
        reqa = await execute_h3_repair_reqa(
            project_name=project_name,
            ticket_id=ticket_id,
            candidate_media=output_media,
        )
        return {
            "execution_identity": persisted.execution_identity,
            "lifecycle_state": str(reqa["lifecycle_state"]),
            "output_media_path": f"repairs/reassembled_units/{persisted.execution_identity}.mp4",
            "provider_shot_path": resource_relative_path(
                H3_REPAIR_SHOT_RESOURCE_TYPE,
                persisted.execution_identity,
            ),
            "reqa": reqa,
            "recovered_reqa": True,
        }

    if persisted.lifecycle_state is not H3RepairTicketLifecycleState.RUNNING:
        raise H3RepairExecutionConflict(
            f"H3 repair execution requires running/reqa ticket; got {persisted.lifecycle_state.value}"
        )
    if persisted.approval_json is None:
        raise H3RepairExecutionConflict("running H3 repair ticket is missing approval binding")
    approval = H3ProviderRepairApprovalBinding.from_json(persisted.approval_json)
    shot_request = build_h3_shot_repair_request(persisted.ticket, approval.to_phase4_approval())

    project_manager = get_project_manager()
    project, project_path = await asyncio.to_thread(
        lambda: (
            project_manager.load_project(project_name),
            project_manager.get_project_path(project_name),
        )
    )

    try:
        source = await asyncio.to_thread(
            resolve_h3_repair_source_version,
            project_path=project_path,
            ticket=persisted.ticket,
        )
        current_facts = H3RepairApprovalFacts(
            source_media_sha256=source.media_sha256,
            shot_id=shot_request.shot_id,
            repair_action=shot_request.repair_action.value,
            provider_prompt_sha256=source.provider_prompt_sha256,
            reference_sha256=persisted.ticket.reference_sha256,
        )

        checkpoint_raw = task.get("execution_checkpoint_json")
        provider_job_id = task.get("provider_job_id")
        if checkpoint_raw is not None:
            if not isinstance(checkpoint_raw, str):
                raise H3RepairExecutionConflict("H3 repair execution checkpoint is malformed")
            checkpoint = H3RepairSubmissionCheckpoint.from_json(checkpoint_raw)
            if provider_job_id is None:
                raise H3RepairExecutionConflict(
                    "H3 repair checkpoint exists without provider job identity; automatic resubmit is forbidden"
                )
            provider_shot = await _provider_shot_from_resume(
                task=task,
                project_name=project_name,
                ticket_id=ticket_id,
                checkpoint=checkpoint,
                current_facts=current_facts,
                project=project,
            )
        else:
            repair_prompt = build_h3_shot_repair_prompt(
                source_provider_prompt=source.provider_prompt,
                request=shot_request,
            )
            duration_seconds = _integer_duration(shot_request.duration_seconds)
            provider_request = H3RepairProviderRequestFacts(
                generation_type=source.generation_type,
                backend_model=source.backend_model,
                endpoint_guard=source.endpoint_guard,
                prompt=repair_prompt,
                prompt_sha256=provider_prompt_sha256(repair_prompt),
                duration_seconds=duration_seconds,
                aspect_ratio=source.aspect_ratio,
                resolution=source.resolution,
                generate_audio=source.generate_audio,
                service_tier=source.service_tier,
                seed=source.seed,
            )
            provider_shot = await _provider_shot_from_fresh_submission(
                task=task,
                project_name=project_name,
                ticket_id=ticket_id,
                execution_identity=persisted.execution_identity,
                source=source,
                current_facts=current_facts,
                provider_request=provider_request,
                project=project,
            )

        await _transition_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            reason="approved provider repair completed",
            actor="system:repair-runtime",
        )
        await _transition_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.REASSEMBLING,
            reason="deterministic shot reassembly started",
            actor="system:repair-runtime",
        )

        output_media = safe_join(
            project_path,
            "repairs",
            "reassembled_units",
            f"{persisted.execution_identity}.mp4",
        )
        result = await asyncio.to_thread(
            _assemble_completed_provider_shot,
            ticket=persisted.ticket,
            approval=approval,
            source_media=source.media_path,
            provider_shot=provider_shot,
            output_media=output_media,
        )
        await _transition_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.REQA_RUNNING,
            reason="deterministic shot reassembly complete; awaiting mandatory Re-QA",
            actor="system:repair-runtime",
            repair_output_sha256=result.output_media_sha256,
        )

        reqa = await execute_h3_repair_reqa(
            project_name=project_name,
            ticket_id=ticket_id,
            candidate_media=output_media,
        )
        relative_output = f"repairs/reassembled_units/{persisted.execution_identity}.mp4"
        relative_provider_shot = resource_relative_path(
            H3_REPAIR_SHOT_RESOURCE_TYPE,
            persisted.execution_identity,
        )
        return {
            **result.to_dict(),
            "output_media_path": relative_output,
            "provider_shot_path": relative_provider_shot,
            "source_version": source.version,
            "execution_identity": persisted.execution_identity,
            "lifecycle_state": str(reqa["lifecycle_state"]),
            "reqa": reqa,
        }
    except asyncio.CancelledError:
        await asyncio.shield(
            _record_repair_cancellation(
                project_name=project_name,
                ticket_id=ticket_id,
            )
        )
        raise
    except Exception as exc:
        await _mark_human_review_if_active(
            project_name=project_name,
            ticket_id=ticket_id,
            reason=f"provider repair runtime failed closed: {type(exc).__name__}",
        )
        raise
