from __future__ import annotations

import json
import os
from pathlib import Path

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

_PROJECT_A = "project-a"
_PROJECT_B = "project-b"
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
    (directory / "e2e05-project-isolation.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


async def test_phase5_project_isolation_e2e(session_factory) -> None:
    ticket = _ticket()
    facts = _facts(ticket)

    async with session_factory() as session:
        store = H3RepairTicketStore(session)
        first = await store.persist(project_name=_PROJECT_A, ticket=ticket)
        second = await store.persist(project_name=_PROJECT_B, ticket=ticket)
        await session.commit()
        assert first.ticket.ticket_id == second.ticket.ticket_id == ticket.ticket_id

        approval_a = await H3RepairApprovalService(session).approve(
            project_name=_PROJECT_A,
            ticket_id=ticket.ticket_id,
            approved_by="operator:a",
            current_facts=facts,
        )
        approval_b = await H3RepairApprovalService(session).approve(
            project_name=_PROJECT_B,
            ticket_id=ticket.ticket_id,
            approved_by="operator:b",
            current_facts=facts,
        )
        assert approval_a.ticket.approval_identity == "operator:a"
        assert approval_b.ticket.approval_identity == "operator:b"

        queue = H3RepairQueueService(session)
        queued_a = await queue.enqueue_approved_ticket(
            project_name=_PROJECT_A,
            ticket_id=ticket.ticket_id,
            user_id="operator:a",
        )
        queued_b = await queue.enqueue_approved_ticket(
            project_name=_PROJECT_B,
            ticket_id=ticket.ticket_id,
            user_id="operator:b",
        )

        assert queued_a.task_id != queued_b.task_id
        assert queued_a.execution_identity != queued_b.execution_identity

        first_claim = await queue.claim_next()
        second_claim = await queue.claim_next()
        assert first_claim is not None
        assert second_claim is not None
        claims = {
            first_claim.project_name: first_claim,
            second_claim.project_name: second_claim,
        }
        assert set(claims) == {_PROJECT_A, _PROJECT_B}
        assert claims[_PROJECT_A].execution_identity == queued_a.execution_identity
        assert claims[_PROJECT_B].execution_identity == queued_b.execution_identity

        reservation_a = await queue.reserve_provider_submission(
            project_name=_PROJECT_A,
            ticket_id=ticket.ticket_id,
            current_facts=facts,
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert reservation_a.disposition is H3RepairSubmissionDisposition.SUBMIT_ALLOWED

    async with session_factory() as session:
        store = H3RepairTicketStore(session)
        final_a = await store.load(project_name=_PROJECT_A, ticket_id=ticket.ticket_id)
        final_b = await store.load(project_name=_PROJECT_B, ticket_id=ticket.ticket_id)
        missing = await store.load(project_name="project-c", ticket_id=ticket.ticket_id)
        assert final_a is not None
        assert final_b is not None
        assert missing is None

        task_a = await session.get(Task, final_a.execution_task_id)
        task_b = await session.get(Task, final_b.execution_task_id)
        assert task_a is not None
        assert task_b is not None

    assert final_a.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
    assert final_b.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
    assert final_a.approval_identity == "operator:a"
    assert final_b.approval_identity == "operator:b"
    assert final_a.execution_identity == queued_a.execution_identity
    assert final_b.execution_identity == queued_b.execution_identity
    assert final_a.execution_identity != final_b.execution_identity
    assert final_a.provider_call_count == 1
    assert final_b.provider_call_count == 0
    assert task_a.execution_checkpoint_json is not None
    assert task_b.execution_checkpoint_json is None
    assert task_a.provider_job_id is None
    assert task_b.provider_job_id is None

    payload: dict[str, object] = {
        "schema_version": 1,
        "scenario": "E2E-05 Multi Project Isolation",
        "tested_sha": os.environ.get("H3_PHASE5_TESTED_SHA"),
        "shared_ticket_id": ticket.ticket_id,
        "project_a": {
            "project_name": _PROJECT_A,
            "approval_identity": final_a.approval_identity,
            "task_id": task_a.task_id,
            "execution_identity": final_a.execution_identity,
            "provider_call_count": final_a.provider_call_count,
            "checkpoint_present": task_a.execution_checkpoint_json is not None,
        },
        "project_b": {
            "project_name": _PROJECT_B,
            "approval_identity": final_b.approval_identity,
            "task_id": task_b.task_id,
            "execution_identity": final_b.execution_identity,
            "provider_call_count": final_b.provider_call_count,
            "checkpoint_present": task_b.execution_checkpoint_json is not None,
        },
        "isolation": {
            "same_ticket_id_allowed_across_projects": final_a.ticket.ticket_id == final_b.ticket.ticket_id,
            "different_task_ids": task_a.task_id != task_b.task_id,
            "different_execution_identities": final_a.execution_identity != final_b.execution_identity,
            "project_a_reservation_did_not_spend_project_b_allowance": final_b.provider_call_count == 0,
            "project_a_reservation_did_not_create_project_b_checkpoint": task_b.execution_checkpoint_json is None,
            "third_project_lookup_is_none": missing is None,
        },
        "provider": {
            "paid_minimax_calls": 0,
        },
    }
    _write_evidence(payload)
