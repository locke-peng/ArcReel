from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lib.db.models.task import Task
from lib.project_manager import ProjectManager
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_approval_service import (
    H3RepairApprovalFacts,
    H3RepairApprovalService,
    H3RepairApprovalStaleError,
)
from lib.reference_video.h3_repair_batch import H3RepairBatchAction
from lib.reference_video.h3_repair_queue import H3RepairAllowanceExhausted, H3RepairQueueService
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)
from server.services import (
    h3_production_control,
    h3_repair_budget_ledger,
    h3_repair_operator,
    h3_studio_evidence,
)
from server.services.h3_repair_batch_operator import execute_h3_repair_batch

_MAIN = "phase6-main"
_OTHER = "phase6-other"


def _write_project(root: Path, name: str, unit_ids: tuple[str, ...]) -> None:
    project = root / name
    (project / "scripts").mkdir(parents=True)
    (project / "versions").mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "name": name,
                "generation_mode": "reference_video",
                "episodes": [{"episode": 1, "script_file": "episode_1.json"}],
            }
        ),
        encoding="utf-8",
    )
    (project / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "episode": 1,
                "video_units": [
                    {"unit_id": unit_id, "duration_seconds": 5, "shots": []}
                    for unit_id in unit_ids
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "versions" / "versions.json").write_text(
        json.dumps({"reference_videos": {}}),
        encoding="utf-8",
    )


def _ticket(unit_id: str, source_digit: str):
    finding = MediaQAFinding(
        unit_id=unit_id,
        shot_id=f"{unit_id}-S01",
        time_range=MediaQATimeRange(start_seconds=0.0, end_seconds=5.0),
        canonical_violation=f"{unit_id} Phase 6 resilience acceptance",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=1.0,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        evidence_frames=(1,),
        tags=("phase6_slice7",),
    )
    return build_h3_repair_ticket(
        plan_h3_auto_repair(finding),
        source_media_sha256=source_digit * 64,
        context=H3RepairTicketContext(
            provider_prompt_sha256="a" * 64,
            reference_sha256=("b" * 64,),
        ),
    )


def _facts(ticket, *, source_media_sha256: str | None = None) -> H3RepairApprovalFacts:
    assert ticket.shot_id is not None
    return H3RepairApprovalFacts(
        source_media_sha256=source_media_sha256 or ticket.source_media_sha256,
        shot_id=ticket.shot_id,
        repair_action=ticket.repair_action,
        provider_prompt_sha256=ticket.provider_prompt_sha256,
        reference_sha256=ticket.reference_sha256,
    )


async def _persist(session_factory, *, project_name: str, ticket, approve: bool) -> None:
    async with session_factory() as session:
        await H3RepairTicketStore(session).persist(project_name=project_name, ticket=ticket)
        await session.commit()
        if approve:
            await H3RepairApprovalService(session).approve(
                project_name=project_name,
                ticket_id=ticket.ticket_id,
                approved_by="slice7:e2e",
                current_facts=_facts(ticket),
            )


def _write_evidence(payload: dict[str, object]) -> None:
    raw_dir = os.environ.get("H3_PHASE6_EVIDENCE_DIR")
    if not raw_dir:
        return
    directory = Path(raw_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "e2e01-control-plane-resilience.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


async def test_phase6_control_plane_resilience_and_evidence_e2e(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects = tmp_path / "projects"
    _write_project(projects, _MAIN, ("E12U06", "E13U03", "E4U02", "E11U02"))
    _write_project(projects, _OTHER, ("E13U01", "E15U03"))
    manager = ProjectManager(projects)

    tickets = {
        "stale": _ticket("E12U06", "1"),
        "valid": _ticket("E13U03", "2"),
        "pending": _ticket("E4U02", "3"),
        "budget": _ticket("E11U02", "4"),
        "other_a": _ticket("E13U01", "5"),
        "other_b": _ticket("E15U03", "6"),
    }
    for key in ("stale", "valid", "budget"):
        await _persist(session_factory, project_name=_MAIN, ticket=tickets[key], approve=True)
    await _persist(session_factory, project_name=_MAIN, ticket=tickets["pending"], approve=False)
    for key in ("other_a", "other_b"):
        await _persist(session_factory, project_name=_OTHER, ticket=tickets[key], approve=True)

    monkeypatch.setattr(h3_production_control, "safe_session_factory", session_factory)
    monkeypatch.setattr(h3_repair_budget_ledger, "safe_session_factory", session_factory)
    monkeypatch.setattr(h3_studio_evidence, "safe_session_factory", session_factory)
    monkeypatch.setattr(h3_repair_operator, "safe_session_factory", session_factory)

    async def resolve_project_path(project_name: str) -> Path:
        return projects / project_name

    monkeypatch.setattr(h3_repair_operator, "resolve_h3_repair_project_path", resolve_project_path)

    before_restart = await h3_production_control.resolve_h3_production_projection(
        project_name=_MAIN,
        project_manager=manager,
    )
    async with session_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.configure_project_running_cap(project_name=_MAIN, max_running_tasks=2)
        await queue.set_project_paused(project_name=_MAIN, paused=True)
        await queue.configure_project_call_ceiling(project_name=_MAIN, ceiling=1)
        await queue.configure_project_running_cap(project_name=_OTHER, max_running_tasks=1)

    async with session_factory() as session:
        queue = H3RepairQueueService(session)
        control = await queue.get_project_control(project_name=_MAIN)
        assert control is not None
        assert control.paused is True
        assert control.max_running_tasks == 2
        assert await queue.claim_next() is None
        await queue.set_project_paused(project_name=_MAIN, paused=False)

    after_restart = await h3_production_control.resolve_h3_production_projection(
        project_name=_MAIN,
        project_manager=manager,
    )
    assert after_restart == before_restart

    batch = await execute_h3_repair_batch(
        project_name=_MAIN,
        action=H3RepairBatchAction.ENQUEUE,
        ticket_ids=(
            tickets["stale"].ticket_id,
            tickets["pending"].ticket_id,
            tickets["valid"].ticket_id,
        ),
        actor="slice7:e2e",
    )
    assert batch.success_count == 2
    assert batch.failure_count == 1
    failed = [item for item in batch.items if not item.success]
    assert len(failed) == 1
    assert failed[0].ticket_id == tickets["pending"].ticket_id

    async with session_factory() as session:
        queue = H3RepairQueueService(session)
        first_claim = await queue.claim_next()
        second_claim = await queue.claim_next()
        assert first_claim is not None
        assert second_claim is not None
        assert first_claim.project_name == _MAIN
        assert second_claim.project_name == _MAIN
        assert first_claim.ticket_id != second_claim.ticket_id

    stale_ticket = tickets["stale"]
    valid_ticket = tickets["valid"]
    if first_claim.ticket_id == valid_ticket.ticket_id:
        first_claim, second_claim = second_claim, first_claim
    assert first_claim.ticket_id == stale_ticket.ticket_id
    assert second_claim.ticket_id == valid_ticket.ticket_id

    async with session_factory() as session:
        with pytest.raises(H3RepairApprovalStaleError, match="source_media_sha256"):
            await H3RepairQueueService(session).reserve_provider_submission(
                project_name=_MAIN,
                ticket_id=stale_ticket.ticket_id,
                current_facts=_facts(stale_ticket, source_media_sha256="9" * 64),
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    async with session_factory() as session:
        valid_reservation = await H3RepairQueueService(session).reserve_provider_submission(
            project_name=_MAIN,
            ticket_id=valid_ticket.ticket_id,
            current_facts=_facts(valid_ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert valid_reservation.provider_call_count == 1
        assert valid_reservation.project_provider_call_count == 1

    budget_batch = await execute_h3_repair_batch(
        project_name=_MAIN,
        action=H3RepairBatchAction.ENQUEUE,
        ticket_ids=(tickets["budget"].ticket_id,),
        actor="slice7:e2e",
    )
    assert budget_batch.success_count == 1
    async with session_factory() as session:
        budget_claim = await H3RepairQueueService(session).claim_next()
        assert budget_claim is not None
        assert budget_claim.ticket_id == tickets["budget"].ticket_id
        with pytest.raises(H3RepairAllowanceExhausted, match="project H3 repair-call ceiling"):
            await H3RepairQueueService(session).reserve_provider_submission(
                project_name=_MAIN,
                ticket_id=tickets["budget"].ticket_id,
                current_facts=_facts(tickets["budget"]),
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    other_batch = await execute_h3_repair_batch(
        project_name=_OTHER,
        action=H3RepairBatchAction.ENQUEUE,
        ticket_ids=(tickets["other_a"].ticket_id, tickets["other_b"].ticket_id),
        actor="slice7:e2e",
    )
    assert other_batch.success_count == 2
    async with session_factory() as session:
        other_claim = await H3RepairQueueService(session).claim_next()
        assert other_claim is not None
        assert other_claim.project_name == _OTHER
        blocked_by_cap = await H3RepairQueueService(session).claim_next()
        assert blocked_by_cap is None

        main_valid = await H3RepairTicketStore(session).load(
            project_name=_MAIN,
            ticket_id=valid_ticket.ticket_id,
        )
        other_running = await H3RepairTicketStore(session).load(
            project_name=_OTHER,
            ticket_id=other_claim.ticket_id,
        )
        assert main_valid is not None
        assert other_running is not None
        assert main_valid.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
        assert other_running.lifecycle_state is H3RepairTicketLifecycleState.RUNNING

    tested_sha = os.environ.get("H3_PHASE6_TESTED_SHA")
    evidence = await h3_studio_evidence.get_h3_studio_evidence_bundle(
        project_name=_MAIN,
        project_manager=manager,
        tested_sha=tested_sha,
    )
    rebuilt_evidence = await h3_studio_evidence.get_h3_studio_evidence_bundle(
        project_name=_MAIN,
        project_manager=manager,
        tested_sha=tested_sha,
    )
    assert rebuilt_evidence == evidence
    assert evidence["budget_ledger"]["reserved_provider_calls"] == 1
    assert evidence["budget_ledger"]["remaining_provider_calls"] == 0

    encoded_evidence = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert "execution_checkpoint_json" not in encoded_evidence
    evidence_by_ticket = {
        item["repair_ticket"]["ticket_id"]: item for item in evidence["tickets"]
    }
    assert evidence_by_ticket[valid_ticket.ticket_id]["execution"]["checkpoint_sha256"] is not None

    async with session_factory() as session:
        store = H3RepairTicketStore(session)
        stale_final = await store.load(project_name=_MAIN, ticket_id=stale_ticket.ticket_id)
        valid_final = await store.load(project_name=_MAIN, ticket_id=valid_ticket.ticket_id)
        budget_final = await store.load(
            project_name=_MAIN,
            ticket_id=tickets["budget"].ticket_id,
        )
        pending_final = await store.load(
            project_name=_MAIN,
            ticket_id=tickets["pending"].ticket_id,
        )
        assert stale_final is not None
        assert valid_final is not None
        assert budget_final is not None
        assert pending_final is not None
        valid_task = await session.get(Task, valid_final.execution_task_id)
        assert valid_task is not None

    assert stale_final.lifecycle_state is H3RepairTicketLifecycleState.EXPIRED
    assert stale_final.provider_call_count == 0
    assert valid_final.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
    assert valid_final.provider_call_count == 1
    assert budget_final.lifecycle_state is H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED
    assert budget_final.provider_call_count == 0
    assert pending_final.lifecycle_state is H3RepairTicketLifecycleState.AWAITING_APPROVAL
    assert valid_task.execution_checkpoint_json is not None

    payload: dict[str, object] = {
        "schema_version": 1,
        "scenario": "Phase 6 Slice 7 Control Plane Resilience",
        "tested_sha": tested_sha,
        "restart_rebuild": {
            "projection_equal_after_restart": after_restart == before_restart,
            "pause_persisted": True,
            "running_cap_persisted": 2,
        },
        "partial_batch": {
            "success_count": batch.success_count,
            "failure_count": batch.failure_count,
            "failed_ticket_id": failed[0].ticket_id,
        },
        "stale_approval_in_batch": {
            "stale_ticket_state": stale_final.lifecycle_state.value,
            "stale_provider_call_count": stale_final.provider_call_count,
            "valid_sibling_state": valid_final.lifecycle_state.value,
            "valid_sibling_provider_call_count": valid_final.provider_call_count,
        },
        "budget_exhaustion": {
            "blocked_ticket_state": budget_final.lifecycle_state.value,
            "blocked_ticket_provider_call_count": budget_final.provider_call_count,
            "project_reserved_provider_calls": evidence["budget_ledger"]["reserved_provider_calls"],
            "project_remaining_provider_calls": evidence["budget_ledger"]["remaining_provider_calls"],
        },
        "multi_project_multi_unit": {
            "main_running_ticket": valid_final.ticket.ticket_id,
            "other_running_ticket": other_claim.ticket_id,
            "other_second_claim_blocked_by_cap": blocked_by_cap is None,
        },
        "evidence_export": {
            "bundle_sha256": evidence["bundle_sha256"],
            "ticket_count": len(evidence["tickets"]),
            "checkpoint_digest_present": (
                evidence_by_ticket[valid_ticket.ticket_id]["execution"]["checkpoint_sha256"]
                is not None
            ),
            "raw_checkpoint_exported": "execution_checkpoint_json" in encoded_evidence,
        },
        "paid_minimax_calls": 0,
        "status": "PASS",
    }
    _write_evidence(payload)
