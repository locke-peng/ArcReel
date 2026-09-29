from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lib.db.models.task import Task
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_approval_service import (
    H3RepairApprovalFacts,
    H3RepairApprovalService,
    H3RepairApprovalStaleError,
)
from lib.reference_video.h3_repair_queue import H3RepairQueueService
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState, H3RepairTicketStore
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)

_PROJECT = "ai-boss"
_UNIT = "E12U06"
_SHOT = "E12U06-S02"


def _ticket():
    finding = MediaQAFinding(
        unit_id=_UNIT,
        shot_id=_SHOT,
        time_range=MediaQATimeRange(start_seconds=5.0, end_seconds=10.0),
        canonical_violation="provider invented non-canonical semantic content",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=0.5,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        evidence_frames=(180,),
        tags=("semantic_failure",),
    )
    return build_h3_repair_ticket(
        plan_h3_auto_repair(finding),
        source_media_sha256="1" * 64,
        context=H3RepairTicketContext(
            provider_prompt_sha256="2" * 64,
            reference_sha256=("3" * 64,),
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


def _write_evidence(payload: dict[str, object]) -> None:
    raw_dir = os.environ.get("H3_PHASE5_EVIDENCE_DIR")
    if not raw_dir:
        return
    directory = Path(raw_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "e2e03-stale-approval.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


async def test_phase5_stale_approval_rejected_before_provider_spend_e2e(
    session_factory,
) -> None:
    ticket = _ticket()
    approved_facts = _facts(ticket)
    stale_source_sha = "9" * 64

    async with session_factory() as session:
        persisted = await H3RepairTicketStore(session).persist(project_name=_PROJECT, ticket=ticket)
        await session.commit()
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.AWAITING_APPROVAL

        approved = await H3RepairApprovalService(session).approve(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
            approved_by="e2e",
            current_facts=approved_facts,
        )
        assert approved.ticket.lifecycle_state is H3RepairTicketLifecycleState.APPROVED

        queue = H3RepairQueueService(session)
        queued = await queue.enqueue_approved_ticket(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
            user_id="e2e",
        )
        claim = await queue.claim_next()
        assert claim is not None
        assert claim.task_id == queued.task_id

    stale_facts = _facts(ticket, source_media_sha256=stale_source_sha)
    async with session_factory() as session:
        with pytest.raises(H3RepairApprovalStaleError, match="source_media_sha256"):
            await H3RepairQueueService(session).reserve_provider_submission(
                project_name=_PROJECT,
                ticket_id=ticket.ticket_id,
                current_facts=stale_facts,
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    async with session_factory() as session:
        final_ticket = await H3RepairTicketStore(session).load(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
        )
        assert final_ticket is not None
        task = await session.get(Task, queued.task_id)
        assert task is not None

    assert final_ticket.lifecycle_state is H3RepairTicketLifecycleState.EXPIRED
    assert final_ticket.provider_call_count == 0
    assert final_ticket.execution_identity == queued.execution_identity == claim.execution_identity
    assert task.status == "failed"
    assert task.execution_checkpoint_json is None
    assert task.provider_job_id is None
    assert task.error_message == "h3_repair_stale_approval_pre_submit"

    payload: dict[str, object] = {
        "schema_version": 1,
        "scenario": "E2E-03 Stale Approval Rejection",
        "tested_sha": os.environ.get("H3_PHASE5_TESTED_SHA"),
        "project_name": _PROJECT,
        "unit_id": _UNIT,
        "shot_id": _SHOT,
        "ticket": {
            "ticket_id": ticket.ticket_id,
            "ticket_sha256": ticket.ticket_sha256,
            "lifecycle_state": final_ticket.lifecycle_state.value,
        },
        "approval": {
            "approved_source_media_sha256": approved_facts.source_media_sha256,
            "current_source_media_sha256": stale_source_sha,
            "stale_field": "source_media_sha256",
        },
        "execution": {
            "task_id": queued.task_id,
            "execution_identity": queued.execution_identity,
            "task_status": task.status,
            "task_error_message": task.error_message,
            "provider_call_count": final_ticket.provider_call_count,
            "checkpoint_present": task.execution_checkpoint_json is not None,
            "provider_job_id_present": task.provider_job_id is not None,
        },
        "provider": {
            "submit_calls": 0,
            "resume_calls": 0,
            "paid_minimax_calls": 0,
        },
        "fail_closed": True,
    }
    _write_evidence(payload)
