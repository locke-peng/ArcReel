from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
from lib.reference_video.h3_repair_approval_service import H3RepairApprovalFacts, H3RepairApprovalService
from lib.reference_video.h3_repair_queue import H3RepairAllowanceExhausted, H3RepairQueueService
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState, H3RepairTicketStore
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)

_PROJECT_BUDGET = "policy-budget"
_PROJECT_MULTI = "policy-multishot"


def _finding(
    *,
    unit_id: str,
    shot_id: str | None,
    start: float | None,
    failure_class: H3FailureClass,
    violation: str,
) -> MediaQAFinding:
    return MediaQAFinding(
        unit_id=unit_id,
        shot_id=shot_id,
        time_range=MediaQATimeRange(start_seconds=start, end_seconds=start + 5.0)
        if start is not None
        else None,
        canonical_violation=violation,
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=False,
        repairability=(
            MediaQARepairability.HUMAN_REVIEW
            if failure_class is H3FailureClass.UNKNOWN
            else MediaQARepairability.PROVIDER
        ),
        affected_fraction=0.5,
        failure_class=failure_class,
        evidence_frames=(120,),
        tags=(failure_class.value,),
    )


def _ticket(
    *,
    unit_id: str,
    shot_id: str | None,
    start: float | None,
    failure_class: H3FailureClass,
    source_digit: str,
):
    finding = _finding(
        unit_id=unit_id,
        shot_id=shot_id,
        start=start,
        failure_class=failure_class,
        violation=f"{failure_class.value} acceptance evidence",
    )
    return build_h3_repair_ticket(
        plan_h3_auto_repair(finding),
        source_media_sha256=source_digit * 64,
        context=H3RepairTicketContext(
            provider_prompt_sha256="a" * 64,
            reference_sha256=("b" * 64,),
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
    (directory / "e2e06-policy-safety-matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


async def test_phase5_policy_safety_matrix_e2e(session_factory) -> None:
    # AC-10: dialogue and identity failures must keep their accepted Phase 3 routes.
    dialogue = _ticket(
        unit_id="E4U02",
        shot_id="E4U02-S02",
        start=5.0,
        failure_class=H3FailureClass.DIALOGUE_VISUALIZATION,
        source_digit="1",
    )
    identity = _ticket(
        unit_id="E13U03",
        shot_id="E13U03-S02",
        start=5.0,
        failure_class=H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
        source_digit="2",
    )
    assert dialogue.repair_action == H3RepairAction.RECOMPILE_DIALOGUE_DETACHED.value
    assert identity.repair_action == H3RepairAction.REGENERATE_WITH_IDENTITY_BRIDGE.value
    assert dialogue.approval_eligible is True
    assert identity.approval_eligible is True

    # AC-11: UNKNOWN is fail-closed and cannot be admitted to provider execution.
    unknown = _ticket(
        unit_id="E99U01",
        shot_id=None,
        start=None,
        failure_class=H3FailureClass.UNKNOWN,
        source_digit="3",
    )
    assert unknown.repair_action == H3RepairAction.ESCALATE.value
    assert unknown.approval_eligible is False
    async with session_factory() as session:
        persisted_unknown = await H3RepairTicketStore(session).persist(
            project_name="policy-unknown",
            ticket=unknown,
        )
        await session.commit()
        assert persisted_unknown.lifecycle_state is H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED
        with pytest.raises(RuntimeError, match="shot-scoped Repair Ticket"):
            await H3RepairApprovalService(session).approve(
                project_name="policy-unknown",
                ticket_id=unknown.ticket_id,
                approved_by="e2e",
                current_facts=H3RepairApprovalFacts(
                    source_media_sha256=unknown.source_media_sha256,
                    shot_id="unresolved",
                    repair_action=unknown.repair_action,
                    provider_prompt_sha256=unknown.provider_prompt_sha256,
                    reference_sha256=unknown.reference_sha256,
                ),
            )

    # AC-12: a project call ceiling must stop a second approved ticket before spend.
    budget_a = _ticket(
        unit_id="E12U06",
        shot_id="E12U06-S01",
        start=0.0,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        source_digit="4",
    )
    budget_b = _ticket(
        unit_id="E12U06",
        shot_id="E12U06-S02",
        start=5.0,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        source_digit="5",
    )
    budget_facts = {budget_a.ticket_id: _facts(budget_a), budget_b.ticket_id: _facts(budget_b)}
    async with session_factory() as session:
        store = H3RepairTicketStore(session)
        for ticket in (budget_a, budget_b):
            await store.persist(project_name=_PROJECT_BUDGET, ticket=ticket)
        await session.commit()
        for ticket in (budget_a, budget_b):
            await H3RepairApprovalService(session).approve(
                project_name=_PROJECT_BUDGET,
                ticket_id=ticket.ticket_id,
                approved_by="e2e",
                current_facts=budget_facts[ticket.ticket_id],
            )

        queue = H3RepairQueueService(session)
        await queue.configure_project_call_ceiling(project_name=_PROJECT_BUDGET, ceiling=1)
        await queue.enqueue_approved_ticket(project_name=_PROJECT_BUDGET, ticket_id=budget_a.ticket_id)
        await queue.enqueue_approved_ticket(project_name=_PROJECT_BUDGET, ticket_id=budget_b.ticket_id)
        claim_a = await queue.claim_next()
        claim_b = await queue.claim_next()
        assert claim_a is not None and claim_b is not None

        await queue.reserve_provider_submission(
            project_name=_PROJECT_BUDGET,
            ticket_id=claim_a.ticket_id,
            current_facts=budget_facts[claim_a.ticket_id],
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        with pytest.raises(H3RepairAllowanceExhausted, match="project H3 repair-call ceiling"):
            await queue.reserve_provider_submission(
                project_name=_PROJECT_BUDGET,
                ticket_id=claim_b.ticket_id,
                current_facts=budget_facts[claim_b.ticket_id],
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    async with session_factory() as session:
        budget_first = await H3RepairTicketStore(session).load(
            project_name=_PROJECT_BUDGET,
            ticket_id=claim_a.ticket_id,
        )
        budget_second = await H3RepairTicketStore(session).load(
            project_name=_PROJECT_BUDGET,
            ticket_id=claim_b.ticket_id,
        )
        assert budget_first is not None and budget_second is not None
    assert budget_first.provider_call_count == 1
    assert budget_second.provider_call_count == 0
    assert budget_second.lifecycle_state is H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED

    # AC-09: two shot-scoped failures in one Unit remain independent tickets/executions.
    shot_a = _ticket(
        unit_id="E13U03",
        shot_id="E13U03-S01",
        start=0.0,
        failure_class=H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
        source_digit="6",
    )
    shot_b = _ticket(
        unit_id="E13U03",
        shot_id="E13U03-S02",
        start=5.0,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        source_digit="6",
    )
    async with session_factory() as session:
        store = H3RepairTicketStore(session)
        await store.persist(project_name=_PROJECT_MULTI, ticket=shot_a)
        await store.persist(project_name=_PROJECT_MULTI, ticket=shot_b)
        await session.commit()
        for ticket in (shot_a, shot_b):
            await H3RepairApprovalService(session).approve(
                project_name=_PROJECT_MULTI,
                ticket_id=ticket.ticket_id,
                approved_by="e2e",
                current_facts=_facts(ticket),
            )
        queue = H3RepairQueueService(session)
        queued_a = await queue.enqueue_approved_ticket(
            project_name=_PROJECT_MULTI,
            ticket_id=shot_a.ticket_id,
        )
        queued_b = await queue.enqueue_approved_ticket(
            project_name=_PROJECT_MULTI,
            ticket_id=shot_b.ticket_id,
        )

    assert shot_a.ticket_id != shot_b.ticket_id
    assert queued_a.task_id != queued_b.task_id
    assert queued_a.execution_identity != queued_b.execution_identity

    payload: dict[str, object] = {
        "schema_version": 1,
        "scenario": "E2E-06 Policy Safety Matrix",
        "tested_sha": os.environ.get("H3_PHASE5_TESTED_SHA"),
        "multi_shot": {
            "ticket_ids_independent": shot_a.ticket_id != shot_b.ticket_id,
            "task_ids_independent": queued_a.task_id != queued_b.task_id,
            "execution_identities_independent": queued_a.execution_identity != queued_b.execution_identity,
        },
        "routing": {
            "dialogue_action": dialogue.repair_action,
            "identity_action": identity.repair_action,
            "dialogue_approval_eligible": dialogue.approval_eligible,
            "identity_approval_eligible": identity.approval_eligible,
        },
        "unknown": {
            "repair_action": unknown.repair_action,
            "approval_eligible": unknown.approval_eligible,
            "lifecycle_state": persisted_unknown.lifecycle_state.value,
        },
        "budget": {
            "ceiling": 1,
            "first_provider_call_count": budget_first.provider_call_count,
            "second_provider_call_count": budget_second.provider_call_count,
            "second_lifecycle_state": budget_second.lifecycle_state.value,
        },
        "provider": {
            "paid_minimax_calls": 0,
        },
    }
    _write_evidence(payload)
