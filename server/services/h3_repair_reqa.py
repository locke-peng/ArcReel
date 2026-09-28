"""Phase 5 Slice 5 Re-QA and formal selection for repaired H3 Units.

This service reuses the trusted Phase 4 runtime gate and ArcReel's existing paid-video
artifact-selection boundary.  It does not classify failures, choose repair actions, or
submit provider work.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from lib.db import safe_session_factory
from lib.db.repositories.task_repo import TaskRepository
from lib.path_safety import safe_join
from lib.project_manager import get_project_manager
from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_provider_repair_runtime import resolve_h3_repair_source_version
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import (
    H3RepairScopeKind,
    H3RepairTicket,
    H3RepairTicketContext,
    H3RepairTicketStatus,
)
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
    PersistedH3RepairTicket,
)
from lib.reference_video.h3_runtime_gate import (
    H3DeterministicRepairHandler,
    H3MediaQAEvaluator,
    H3RuntimeSelectionError,
    run_h3_runtime_selection_gate,
)
from lib.resource_paths import resource_relative_path
from lib.version_manager import PaidVersionCommit, VersionManager
from lib.video_artifact_facts import VideoArtifactCurrencyFacts
from lib.video_prompt_compilers.h3_prompt_compiler import is_h3_model
from server.services.reference_video_tasks import resolve_trusted_h3_runtime_bundle
from server.services.video_artifact_currency import VideoArtifactCommitter

_REQA_METADATA_KEY = "h3_reqa"
_REPAIR_TICKET_METADATA_KEY = "h3_repair_ticket_id"
_REPAIR_EXECUTION_METADATA_KEY = "h3_repair_execution_identity"
_REPAIR_SOURCE_VERSION_METADATA_KEY = "h3_repair_source_version"
_REPAIR_SOURCE = "h3_provider_repair"
_VERSION_RECORD_RESERVED = frozenset(
    {
        "version",
        "file",
        "prompt",
        "created_at",
        "is_current",
        "file_url",
    }
)


def _ticket_from_dict(value: object) -> H3RepairTicket:
    if not isinstance(value, Mapping):
        raise ValueError("Re-QA repair ticket payload must be an object")
    return H3RepairTicket(
        schema_version=int(value["schema_version"]),
        ticket_id=str(value["ticket_id"]),
        ticket_sha256=str(value["ticket_sha256"]),
        status=H3RepairTicketStatus(str(value["status"])),
        approval_eligible=bool(value["approval_eligible"]),
        unit_id=str(value["unit_id"]),
        shot_id=str(value["shot_id"]) if value.get("shot_id") is not None else None,
        scope_kind=H3RepairScopeKind(str(value["scope_kind"])),
        start_seconds=float(value["start_seconds"]) if value.get("start_seconds") is not None else None,
        end_seconds=float(value["end_seconds"]) if value.get("end_seconds") is not None else None,
        region=str(value["region"]) if value.get("region") is not None else None,
        failure_class=str(value["failure_class"]),
        repair_action=str(value["repair_action"]),
        provider_recall_required=bool(value["provider_recall_required"]),
        canonical_violation=str(value["canonical_violation"]),
        planner_reason=str(value["planner_reason"]),
        source_media_sha256=str(value["source_media_sha256"]),
        provider_prompt_sha256=(
            str(value["provider_prompt_sha256"])
            if value.get("provider_prompt_sha256") is not None
            else None
        ),
        reference_sha256=tuple(str(item) for item in value.get("reference_sha256", ())),
        evidence_frames=tuple(int(item) for item in value.get("evidence_frames", ())),
        tags=tuple(str(item) for item in value.get("tags", ())),
        provider_task_id=(
            str(value["provider_task_id"]) if value.get("provider_task_id") is not None else None
        ),
        provider_run_id=(
            int(value["provider_run_id"]) if value.get("provider_run_id") is not None else None
        ),
        provider_artifact_id=(
            int(value["provider_artifact_id"])
            if value.get("provider_artifact_id") is not None
            else None
        ),
    )


async def _load_ticket(project_name: str, ticket_id: str) -> PersistedH3RepairTicket:
    async with safe_session_factory() as session:
        persisted = await H3RepairTicketStore(session).load(
            project_name=project_name,
            ticket_id=ticket_id,
        )
    if persisted is None:
        raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
    return persisted


async def _load_origin_task(ticket: H3RepairTicket) -> dict[str, Any]:
    if not ticket.provider_task_id:
        raise RuntimeError("H3 Re-QA requires the trusted originating generation task identity")
    async with safe_session_factory() as session:
        task = await TaskRepository(session).get(ticket.provider_task_id)
    if task is None:
        raise RuntimeError("originating H3 generation task is no longer available for trusted Re-QA")
    return task


async def _resolve_reqa_runtime_bundle(
    *,
    persisted: PersistedH3RepairTicket,
    project_path: Path,
    provider_model: str,
    evaluator: H3MediaQAEvaluator | None,
    repair_handlers: Mapping[H3RepairAction, H3DeterministicRepairHandler] | None,
) -> tuple[H3MediaQAEvaluator, Mapping[H3RepairAction, H3DeterministicRepairHandler]]:
    if evaluator is not None:
        return evaluator, repair_handlers or {}

    if not is_h3_model(provider_model):
        raise RuntimeError("H3 Re-QA source provider model is not an H3 model")

    origin = await _load_origin_task(persisted.ticket)
    payload = origin.get("payload")
    if not isinstance(payload, Mapping):
        raise RuntimeError("originating H3 generation task payload is missing")
    canonical_director = payload.get("canonical_director")
    if not isinstance(canonical_director, Mapping):
        raise RuntimeError("originating H3 generation task has no trusted Canonical Director payload")
    expected_prompt_sha = payload.get("expected_provider_prompt_sha256")
    if (
        not isinstance(expected_prompt_sha, str)
        or not persisted.ticket.provider_prompt_sha256
        or expected_prompt_sha.strip() != persisted.ticket.provider_prompt_sha256
    ):
        raise RuntimeError("originating H3 prompt lock no longer matches Repair Ticket provenance")

    resolved_evaluator, resolved_handlers = resolve_trusted_h3_runtime_bundle(
        canonical_director=canonical_director,
        unit_id=persisted.ticket.unit_id,
        project_path=project_path,
        prompt_lock_verified=True,
        h3_compiler_applied=True,
        evaluator=None,
        repair_handlers=repair_handlers,
    )
    if resolved_evaluator is None:
        raise RuntimeError("trusted Phase 4 H3 runtime evaluator could not be reconstructed")
    return resolved_evaluator, resolved_handlers or {}


def _source_version_record(
    versions: VersionManager,
    *,
    unit_id: str,
    version: int,
) -> dict[str, Any]:
    info = versions.get_versions("reference_videos", unit_id)
    record = next(
        (
            item
            for item in info.get("versions", ())
            if isinstance(item, dict) and item.get("version") == version
        ),
        None,
    )
    if record is None:
        raise RuntimeError("accepted H3 source version record is missing")
    return dict(record)


def _selection_metadata(
    *,
    source_record: Mapping[str, Any],
    source_version: int,
    ticket_id: str,
    execution_identity: str,
    gate_report: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = {
        key: value
        for key, value in source_record.items()
        if key not in _VERSION_RECORD_RESERVED and not key.startswith("_")
    }
    raw_currency = metadata.get("artifact_video_currency")
    try:
        currency = VideoArtifactCurrencyFacts.from_dict(raw_currency)
    except (TypeError, ValueError):
        currency = None
    if currency is not None:
        metadata["artifact_video_currency"] = replace(
            currency,
            parent_version=source_version,
        ).to_dict()
    metadata.update(
        {
            "source": _REPAIR_SOURCE,
            _REPAIR_TICKET_METADATA_KEY: ticket_id,
            _REPAIR_EXECUTION_METADATA_KEY: execution_identity,
            _REPAIR_SOURCE_VERSION_METADATA_KEY: source_version,
            _REQA_METADATA_KEY: dict(gate_report),
        }
    )
    return metadata


def _existing_reqa_record(
    versions: VersionManager,
    *,
    unit_id: str,
    ticket_id: str,
    execution_identity: str,
) -> dict[str, Any] | None:
    info = versions.get_versions("reference_videos", unit_id)
    matches = [
        item
        for item in info.get("versions", ())
        if isinstance(item, dict)
        and item.get(_REPAIR_TICKET_METADATA_KEY) == ticket_id
        and item.get(_REPAIR_EXECUTION_METADATA_KEY) == execution_identity
    ]
    if len(matches) > 1:
        raise RuntimeError("multiple Re-QA version records exist for one repair execution")
    return dict(matches[0]) if matches else None


async def _persist_followup_tickets(
    *,
    project_name: str,
    parent_ticket_id: str,
    report: Mapping[str, Any],
    max_followup_tickets: int,
) -> tuple[str, ...]:
    raw = report.get("repair_tickets")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("provider-required Re-QA report contains no follow-up Repair Ticket")
    if len(raw) > max_followup_tickets:
        raise RuntimeError("provider-required Re-QA exceeded the bounded follow-up ticket limit")

    tickets = tuple(_ticket_from_dict(item) for item in raw)
    ids = tuple(ticket.ticket_id for ticket in tickets)
    if len(set(ids)) != len(ids):
        raise RuntimeError("provider-required Re-QA emitted duplicate follow-up Repair Tickets")
    if parent_ticket_id in ids:
        raise RuntimeError("provider-required Re-QA attempted to recreate the same Repair Ticket")
    if any(
        not ticket.provider_recall_required
        or not ticket.approval_eligible
        or ticket.status is not H3RepairTicketStatus.AWAITING_APPROVAL
        for ticket in tickets
    ):
        raise RuntimeError("provider-required Re-QA emitted a non-approvable follow-up ticket")

    async with safe_session_factory() as session:
        store = H3RepairTicketStore(session)
        persisted_rows = [
            await store.persist(project_name=project_name, ticket=ticket)
            for ticket in tickets
        ]
        if any(
            row.approval_json is not None
            or row.approval_identity is not None
            or row.max_provider_calls is not None
            for row in persisted_rows
        ):
            raise RuntimeError("follow-up Repair Ticket unexpectedly inherited approval state")
        await session.commit()
    return ids


async def _complete_ticket(
    *,
    project_name: str,
    ticket_id: str,
    target: H3RepairTicketLifecycleState,
    reqa_outcome: str,
    reason: str,
    selected_artifact_id: str | None = None,
    selected_version_id: str | None = None,
) -> PersistedH3RepairTicket:
    async with safe_session_factory() as session:
        result = await H3RepairTicketStore(session).complete_reqa(
            project_name=project_name,
            ticket_id=ticket_id,
            target=target,
            reqa_outcome=reqa_outcome,
            reason=reason,
            selected_artifact_id=selected_artifact_id,
            selected_version_id=selected_version_id,
        )
        await session.commit()
        return result


def _history_result(
    *,
    persisted: PersistedH3RepairTicket,
    version_record: Mapping[str, Any],
    lifecycle_state: H3RepairTicketLifecycleState,
    followup_ticket_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    report = version_record.get(_REQA_METADATA_KEY)
    status = report.get("status") if isinstance(report, Mapping) else None
    return {
        "ticket_id": persisted.ticket.ticket_id,
        "execution_identity": persisted.execution_identity,
        "reqa_outcome": str(status or persisted.reqa_outcome or "UNKNOWN"),
        "lifecycle_state": lifecycle_state.value,
        "history_version": int(version_record["version"]),
        "selected_current": bool(version_record.get("is_current")),
        "followup_ticket_ids": list(followup_ticket_ids),
    }


async def execute_h3_repair_reqa(
    *,
    project_name: str,
    ticket_id: str,
    candidate_media: Path,
    evaluator: H3MediaQAEvaluator | None = None,
    repair_handlers: Mapping[H3RepairAction, H3DeterministicRepairHandler] | None = None,
    max_followup_tickets: int = 8,
) -> dict[str, Any]:
    """Re-QA one reassembled repair and select it formally only on trusted PASS."""

    if max_followup_tickets < 1:
        raise ValueError("max_followup_tickets must be >= 1")

    persisted = await _load_ticket(project_name, ticket_id)
    if persisted.lifecycle_state is not H3RepairTicketLifecycleState.REQA_RUNNING:
        raise RuntimeError(
            f"H3 repair Re-QA requires reqa_running ticket; got {persisted.lifecycle_state.value}"
        )
    if not persisted.execution_identity:
        raise RuntimeError("H3 repair Re-QA requires execution identity")
    if not persisted.repair_output_sha256:
        raise RuntimeError("H3 repair Re-QA requires persisted repair output SHA")

    project_manager = get_project_manager()
    project_path = await asyncio.to_thread(project_manager.get_project_path, project_name)
    project_path = Path(project_path)
    versions = VersionManager(project_path)
    existing = _existing_reqa_record(
        versions,
        unit_id=persisted.ticket.unit_id,
        ticket_id=ticket_id,
        execution_identity=persisted.execution_identity,
    )
    if existing is not None:
        report = existing.get(_REQA_METADATA_KEY)
        status = report.get("status") if isinstance(report, Mapping) else None
        if status == "PASS" and existing.get("is_current"):
            selected_artifact_id = resource_relative_path("reference_videos", persisted.ticket.unit_id)
            selected_version_id = (
                f"reference_videos:{persisted.ticket.unit_id}:v{int(existing['version'])}"
            )
            completed = await _complete_ticket(
                project_name=project_name,
                ticket_id=ticket_id,
                target=H3RepairTicketLifecycleState.ACCEPTED,
                reqa_outcome="PASS",
                reason="recovered formal selection from persisted Re-QA version",
                selected_artifact_id=selected_artifact_id,
                selected_version_id=selected_version_id,
            )
            return _history_result(
                persisted=completed,
                version_record=existing,
                lifecycle_state=completed.lifecycle_state,
            )
        if status == "PROVIDER_REPAIR_REQUIRED" and isinstance(report, Mapping):
            followups = await _persist_followup_tickets(
                project_name=project_name,
                parent_ticket_id=ticket_id,
                report=report,
                max_followup_tickets=max_followup_tickets,
            )
            completed = await _complete_ticket(
                project_name=project_name,
                ticket_id=ticket_id,
                target=H3RepairTicketLifecycleState.REJECTED,
                reqa_outcome="PROVIDER_REPAIR_REQUIRED",
                reason="Re-QA rejected repaired candidate and emitted new approval-bound ticket(s)",
            )
            return _history_result(
                persisted=completed,
                version_record=existing,
                lifecycle_state=completed.lifecycle_state,
                followup_ticket_ids=followups,
            )

        completed = await _complete_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            reqa_outcome=str(status or "REQA_RECOVERY_UNRESOLVED"),
            reason="persisted Re-QA history could not be accepted automatically",
        )
        return _history_result(
            persisted=completed,
            version_record=existing,
            lifecycle_state=completed.lifecycle_state,
        )

    candidate_media = Path(candidate_media)
    if not candidate_media.is_file():
        raise FileNotFoundError(candidate_media)
    candidate_sha = await asyncio.to_thread(sha256_file, candidate_media)
    if candidate_sha != persisted.repair_output_sha256:
        raise RuntimeError("reassembled repair bytes no longer match persisted repair output SHA")

    source = await asyncio.to_thread(
        resolve_h3_repair_source_version,
        project_path=project_path,
        ticket=persisted.ticket,
    )
    source_record = _source_version_record(
        versions,
        unit_id=persisted.ticket.unit_id,
        version=source.version,
    )
    trusted_evaluator, trusted_handlers = await _resolve_reqa_runtime_bundle(
        persisted=persisted,
        project_path=project_path,
        provider_model=source.provider_model,
        evaluator=evaluator,
        repair_handlers=repair_handlers,
    )

    work_file = safe_join(
        project_path,
        "repairs",
        "reqa_work",
        f"{persisted.execution_identity}.mp4",
    )
    await asyncio.to_thread(work_file.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(shutil.copy2, candidate_media, work_file)

    context = H3RepairTicketContext(
        provider_prompt_sha256=persisted.ticket.provider_prompt_sha256,
        reference_sha256=persisted.ticket.reference_sha256,
        provider_task_id=persisted.ticket.provider_task_id,
        provider_run_id=persisted.ticket.provider_run_id,
        provider_artifact_id=persisted.ticket.provider_artifact_id,
    )

    try:
        gate_result = await run_h3_runtime_selection_gate(
            work_file,
            evaluator=trusted_evaluator,
            repair_handlers=trusted_handlers,
            repair_ticket_context=context,
        )
    except H3RuntimeSelectionError as exc:
        report = dict(exc.report)
        metadata = _selection_metadata(
            source_record=source_record,
            source_version=source.version,
            ticket_id=ticket_id,
            execution_identity=persisted.execution_identity,
            gate_report=report,
        )
        commit = await asyncio.to_thread(
            versions.commit_staged_paid_version,
            "reference_videos",
            persisted.ticket.unit_id,
            source.provider_prompt,
            staged_file=work_file,
            current_file=project_path / resource_relative_path("reference_videos", persisted.ticket.unit_id),
            select_current=False,
            **metadata,
        )

        status = str(report.get("status") or exc.code)
        if status == "PROVIDER_REPAIR_REQUIRED":
            try:
                followups = await _persist_followup_tickets(
                    project_name=project_name,
                    parent_ticket_id=ticket_id,
                    report=report,
                    max_followup_tickets=max_followup_tickets,
                )
            except Exception:
                completed = await _complete_ticket(
                    project_name=project_name,
                    ticket_id=ticket_id,
                    target=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
                    reqa_outcome="PROVIDER_REPAIR_FOLLOWUP_BLOCKED",
                    reason="Re-QA follow-up ticket creation failed closed",
                )
                return {
                    "ticket_id": ticket_id,
                    "execution_identity": persisted.execution_identity,
                    "reqa_outcome": completed.reqa_outcome,
                    "lifecycle_state": completed.lifecycle_state.value,
                    "history_version": commit.version,
                    "selected_current": False,
                    "followup_ticket_ids": [],
                }
            completed = await _complete_ticket(
                project_name=project_name,
                ticket_id=ticket_id,
                target=H3RepairTicketLifecycleState.REJECTED,
                reqa_outcome=status,
                reason="Re-QA rejected repaired candidate and emitted new approval-bound ticket(s)",
            )
            return {
                "ticket_id": ticket_id,
                "execution_identity": persisted.execution_identity,
                "reqa_outcome": status,
                "lifecycle_state": completed.lifecycle_state.value,
                "history_version": commit.version,
                "selected_current": False,
                "followup_ticket_ids": list(followups),
            }

        completed = await _complete_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            reqa_outcome=status,
            reason="Re-QA did not pass; repaired candidate retained history-only",
        )
        return {
            "ticket_id": ticket_id,
            "execution_identity": persisted.execution_identity,
            "reqa_outcome": status,
            "lifecycle_state": completed.lifecycle_state.value,
            "history_version": commit.version,
            "selected_current": False,
            "followup_ticket_ids": [],
        }

    except Exception as exc:
        report = {
            "status": "REQA_RUNTIME_ERROR",
            "error_type": type(exc).__name__,
        }
        metadata = _selection_metadata(
            source_record=source_record,
            source_version=source.version,
            ticket_id=ticket_id,
            execution_identity=persisted.execution_identity,
            gate_report=report,
        )
        commit = await asyncio.to_thread(
            versions.commit_staged_paid_version,
            "reference_videos",
            persisted.ticket.unit_id,
            source.provider_prompt,
            staged_file=work_file,
            current_file=project_path / resource_relative_path("reference_videos", persisted.ticket.unit_id),
            select_current=False,
            **metadata,
        )
        completed = await _complete_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            reqa_outcome="REQA_RUNTIME_ERROR",
            reason=f"trusted Re-QA failed closed before formal selection: {type(exc).__name__}",
        )
        return {
            "ticket_id": ticket_id,
            "execution_identity": persisted.execution_identity,
            "reqa_outcome": completed.reqa_outcome,
            "lifecycle_state": completed.lifecycle_state.value,
            "history_version": commit.version,
            "selected_current": False,
            "followup_ticket_ids": [],
        }

    gate_report = gate_result.to_dict()
    metadata = _selection_metadata(
        source_record=source_record,
        source_version=source.version,
        ticket_id=ticket_id,
        execution_identity=persisted.execution_identity,
        gate_report=gate_report,
    )
    raw_duration = metadata.get("execution_duration_seconds")
    if not isinstance(raw_duration, int) or isinstance(raw_duration, bool) or raw_duration <= 0:
        raise RuntimeError("accepted H3 source version has invalid execution duration")

    committer = VideoArtifactCommitter(
        project_manager=project_manager,
        project_name=project_name,
        project_path=project_path,
        versions=versions,
        resource_type="reference_videos",
        resource_id=persisted.ticket.unit_id,
        prompt=source.provider_prompt,
    )
    current_file = project_path / resource_relative_path("reference_videos", persisted.ticket.unit_id)
    commit: PaidVersionCommit
    try:
        await committer.prepare_selection(work_file, raw_duration, metadata)
        commit = await asyncio.to_thread(
            committer,
            work_file,
            current_file,
            raw_duration,
            metadata,
        )
    finally:
        await committer.release_admission_guard()

    if not commit.selected:
        completed = await _complete_ticket(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            reqa_outcome="PASS_SELECTION_BLOCKED",
            reason="Re-QA passed but formal selection was blocked by current artifact state",
        )
        return {
            "ticket_id": ticket_id,
            "execution_identity": persisted.execution_identity,
            "reqa_outcome": completed.reqa_outcome,
            "lifecycle_state": completed.lifecycle_state.value,
            "history_version": commit.version,
            "selected_current": False,
            "followup_ticket_ids": [],
        }

    selected_artifact_id = resource_relative_path("reference_videos", persisted.ticket.unit_id)
    selected_version_id = f"reference_videos:{persisted.ticket.unit_id}:v{commit.version}"
    completed = await _complete_ticket(
        project_name=project_name,
        ticket_id=ticket_id,
        target=H3RepairTicketLifecycleState.ACCEPTED,
        reqa_outcome="PASS",
        reason="trusted Phase 4 Re-QA passed and repaired Unit was selected formally",
        selected_artifact_id=selected_artifact_id,
        selected_version_id=selected_version_id,
    )
    return {
        "ticket_id": ticket_id,
        "execution_identity": persisted.execution_identity,
        "reqa_outcome": "PASS",
        "lifecycle_state": completed.lifecycle_state.value,
        "history_version": commit.version,
        "selected_current": True,
        "selected_artifact_id": selected_artifact_id,
        "selected_version_id": selected_version_id,
        "followup_ticket_ids": [],
    }
