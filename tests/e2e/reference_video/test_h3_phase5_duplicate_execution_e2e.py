from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import func, select

from lib.db.models.h3_repair_ticket import H3RepairTicketRecord
from lib.db.models.task import Task
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_approval_service import H3RepairApprovalFacts, H3RepairApprovalService
from lib.reference_video.h3_repair_queue import (
    H3RepairQueueService,
    H3RepairSubmissionDisposition,
)
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


def _facts(ticket) -> H3RepairApprovalFacts:
    assert ticket.shot_id is not None
    return H3RepairApprovalFacts(
        source_media_sha256=ticket.source_media_sha256,
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
    (directory / "e2e04-duplicate-execution.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


async def test_phase5_duplicate_execution_has_single_winner_e2e(
    concurrent_session_factory,
) -> None:
    ticket = _ticket()
    facts = _facts(ticket)

    async with concurrent_session_factory() as session:
        persisted = await H3RepairTicketStore(session).persist(project_name=_PROJECT, ticket=ticket)
        await session.commit()
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.AWAITING_APPROVAL
        approved = await H3RepairApprovalService(session).approve(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
            approved_by="e2e",
            current_facts=facts,
        )
        assert approved.ticket.lifecycle_state is H3RepairTicketLifecycleState.APPROVED

    async def enqueue_once():
        async with concurrent_session_factory() as session:
            return await H3RepairQueueService(session).enqueue_approved_ticket(
                project_name=_PROJECT,
                ticket_id=ticket.ticket_id,
                user_id="e2e",
            )

    first_enqueue, second_enqueue = await asyncio.gather(enqueue_once(), enqueue_once())
    assert first_enqueue.task_id == second_enqueue.task_id
    assert first_enqueue.execution_identity == second_enqueue.execution_identity
    assert {first_enqueue.deduped, second_enqueue.deduped} == {False, True}

    async def claim_once():
        async with concurrent_session_factory() as session:
            return await H3RepairQueueService(session).claim_next()

    first_claim, second_claim = await asyncio.gather(claim_once(), claim_once())
    claims = [claim for claim in (first_claim, second_claim) if claim is not None]
    assert len(claims) == 1
    claim = claims[0]
    assert claim.task_id == first_enqueue.task_id
    assert claim.execution_identity == first_enqueue.execution_identity
    assert claim.attempt_count == 1

    async def reserve_once():
        async with concurrent_session_factory() as session:
            return await H3RepairQueueService(session).reserve_provider_submission(
                project_name=_PROJECT,
                ticket_id=ticket.ticket_id,
                current_facts=facts,
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    first_reservation, second_reservation = await asyncio.gather(reserve_once(), reserve_once())
    dispositions = {
        first_reservation.disposition,
        second_reservation.disposition,
    }
    assert dispositions == {
        H3RepairSubmissionDisposition.SUBMIT_ALLOWED,
        H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID,
    }
    assert first_reservation.provider_call_count == 1
    assert second_reservation.provider_call_count == 1

    async with concurrent_session_factory() as session:
        final_ticket = await H3RepairTicketStore(session).load(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
        )
        assert final_ticket is not None
        task = await session.get(Task, final_ticket.execution_task_id)
        assert task is not None
        task_count = await session.scalar(
            select(func.count()).select_from(Task).where(Task.task_type == "h3_provider_repair")
        )
        ticket_count = await session.scalar(
            select(func.count())
            .select_from(H3RepairTicketRecord)
            .where(H3RepairTicketRecord.project_name == _PROJECT)
        )

    assert final_ticket.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
    assert final_ticket.attempt_count == 1
    assert final_ticket.provider_call_count == 1
    assert final_ticket.execution_identity == claim.execution_identity
    assert task.status == "running"
    assert task.execution_checkpoint_json is not None
    assert task.provider_job_id is None
    assert task_count == 1
    assert ticket_count == 1

    submit_allowed_count = sum(
        reservation.disposition is H3RepairSubmissionDisposition.SUBMIT_ALLOWED
        for reservation in (first_reservation, second_reservation)
    )
    reserved_without_id_count = sum(
        reservation.disposition is H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID
        for reservation in (first_reservation, second_reservation)
    )

    payload: dict[str, object] = {
        "schema_version": 1,
        "scenario": "E2E-04 Duplicate Execution Single Winner",
        "tested_sha": os.environ.get("H3_PHASE5_TESTED_SHA"),
        "project_name": _PROJECT,
        "unit_id": _UNIT,
        "shot_id": _SHOT,
        "ticket": {
            "ticket_id": ticket.ticket_id,
            "ticket_count": ticket_count,
            "lifecycle_state": final_ticket.lifecycle_state.value,
        },
        "enqueue": {
            "task_id_first": first_enqueue.task_id,
            "task_id_second": second_enqueue.task_id,
            "execution_identity_first": first_enqueue.execution_identity,
            "execution_identity_second": second_enqueue.execution_identity,
            "deduped_values": sorted([first_enqueue.deduped, second_enqueue.deduped]),
            "task_count": task_count,
        },
        "claim": {
            "winner_count": len(claims),
            "attempt_count": final_ticket.attempt_count,
            "task_id": claim.task_id,
            "execution_identity": claim.execution_identity,
        },
        "provider_reservation": {
            "submit_allowed_count": submit_allowed_count,
            "reserved_without_provider_id_count": reserved_without_id_count,
            "provider_call_count": final_ticket.provider_call_count,
            "checkpoint_present": task.execution_checkpoint_json is not None,
            "provider_job_id_present": task.provider_job_id is not None,
        },
        "provider": {
            "paid_minimax_calls": 0,
        },
    }
    _write_evidence(payload)
