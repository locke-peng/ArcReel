from __future__ import annotations

import pytest

from lib.ledger import Ledger
from lib.providers import CallStatus
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_approval_service import H3RepairApprovalFacts, H3RepairApprovalService
from lib.reference_video.h3_repair_queue import H3RepairQueueService
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketStore
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)
from server.services import h3_repair_budget_ledger


def _ticket():
    finding = MediaQAFinding(
        unit_id="E12U06",
        shot_id="E12U06-S02",
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


@pytest.mark.asyncio
async def test_repair_ledger_reconciles_allowance_and_actual_api_cost(
    db_factory,
    monkeypatch,
) -> None:
    ticket = _ticket()
    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        await store.persist(project_name="ai-boss", ticket=ticket)
        await session.commit()
        await H3RepairApprovalService(session).approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            current_facts=_facts(ticket),
        )
        queue = H3RepairQueueService(session)
        await queue.configure_project_call_ceiling(project_name="ai-boss", ceiling=2)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        claim = await queue.claim_next()
        assert claim is not None
        reservation = await queue.reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert reservation.provider_call_count == 1

    ledger = Ledger(session_factory=db_factory, publish_change=lambda *_args, **_kwargs: None)
    await ledger.backfill(
        project_name="ai-boss",
        call_type="video",
        model="MiniMax-H3",
        provider="minimax",
        prompt=None,
        user_id="operator:jane",
        status=CallStatus.SUCCESS,
        cost_amount=1.25,
        currency="USD",
        task_id=claim.task_id,
    )

    monkeypatch.setattr(h3_repair_budget_ledger, "safe_session_factory", db_factory)
    result = await h3_repair_budget_ledger.resolve_h3_repair_project_ledger(
        project_name="ai-boss"
    )

    assert result.provider_call_ceiling == 2
    assert result.reserved_provider_calls == 1
    assert result.remaining_provider_calls == 1
    assert result.budget_counter_reconciled is True
    assert result.actual_cost_by_currency == {"USD": 1.25}
    assert result.unpriced_call_count == 0
    assert len(result.tickets) == 1
    item = result.tickets[0]
    assert item.ticket_id == ticket.ticket_id
    assert item.reserved_provider_calls == 1
    assert item.actual_cost_by_currency == {"USD": 1.25}
    assert item.pricing_state == "settled"
    assert item.actual_calls[0].task_id == claim.task_id


@pytest.mark.asyncio
async def test_repair_ledger_fails_loud_on_budget_counter_drift(
    db_factory,
    monkeypatch,
) -> None:
    ticket = _ticket()
    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        await store.persist(project_name="ai-boss", ticket=ticket)
        await session.commit()
        await H3RepairApprovalService(session).approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            current_facts=_facts(ticket),
        )
        queue = H3RepairQueueService(session)
        budget = await queue.configure_project_call_ceiling(project_name="ai-boss", ceiling=2)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        claim = await queue.claim_next()
        assert claim is not None
        await queue.reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        budget.provider_call_count = 0
        await session.commit()

    monkeypatch.setattr(h3_repair_budget_ledger, "safe_session_factory", db_factory)
    with pytest.raises(RuntimeError, match="does not reconcile"):
        await h3_repair_budget_ledger.resolve_h3_repair_project_ledger(
            project_name="ai-boss"
        )
