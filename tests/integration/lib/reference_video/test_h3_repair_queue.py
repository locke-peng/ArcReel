from __future__ import annotations

import asyncio

import pytest

from lib.db.models.h3_repair_ticket import H3RepairProjectBudget
from lib.db.models.task import Task
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_repair_approval_service import (
    H3RepairApprovalFacts,
    H3RepairApprovalService,
    H3RepairApprovalStaleError,
)
from lib.reference_video.h3_repair_queue import (
    H3_REPAIR_MEDIA_TYPE,
    H3_REPAIR_TASK_TYPE,
    H3RepairAllowanceExhausted,
    H3RepairExecutionConflict,
    H3RepairProviderRequestFacts,
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


def _ticket(*, unit_id: str, source_digit: str):
    shot_id = f"{unit_id}-S02"
    finding = MediaQAFinding(
        unit_id=unit_id,
        shot_id=shot_id,
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
        source_media_sha256=source_digit * 64,
        context=H3RepairTicketContext(
            provider_prompt_sha256="2" * 64,
            reference_sha256=("3" * 64, "4" * 64),
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


async def _persist_approve(session_factory, *, project_name: str, unit_id: str, source_digit: str):
    ticket = _ticket(unit_id=unit_id, source_digit=source_digit)
    async with session_factory() as session:
        await H3RepairTicketStore(session).persist(project_name=project_name, ticket=ticket)
        await session.commit()
        await H3RepairApprovalService(session).approve(
            project_name=project_name,
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            current_facts=_facts(ticket),
        )
    return ticket


async def test_enqueue_approved_ticket_is_idempotent_and_uses_dormant_repair_lane(db_factory) -> None:
    ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )

    async with db_factory() as session:
        service = H3RepairQueueService(session)
        first = await service.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        second = await service.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert first.deduped is False
        assert second.deduped is True
        assert second.task_id == first.task_id
        assert second.execution_identity == first.execution_identity

        task = await session.get(Task, first.task_id)
        assert task is not None
        assert task.task_type == H3_REPAIR_TASK_TYPE
        assert task.media_type == H3_REPAIR_MEDIA_TYPE
        assert task.status == "queued"

        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.QUEUED
        assert persisted.execution_identity == first.execution_identity
        assert persisted.execution_task_id == first.task_id


async def test_concurrent_duplicate_enqueue_resolves_to_one_task(concurrent_session_factory) -> None:
    ticket = await _persist_approve(
        concurrent_session_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )

    async def enqueue_once():
        async with concurrent_session_factory() as session:
            return await H3RepairQueueService(session).enqueue_approved_ticket(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
            )

    first, second = await asyncio.gather(enqueue_once(), enqueue_once())
    assert first.task_id == second.task_id
    assert first.execution_identity == second.execution_identity
    assert {first.deduped, second.deduped} == {False, True}


async def test_atomic_claim_allows_only_one_worker(concurrent_session_factory) -> None:
    ticket = await _persist_approve(
        concurrent_session_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    async with concurrent_session_factory() as session:
        await H3RepairQueueService(session).enqueue_approved_ticket(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
        )

    async def claim_once():
        async with concurrent_session_factory() as session:
            return await H3RepairQueueService(session).claim_next()

    first, second = await asyncio.gather(claim_once(), claim_once())
    claims = [claim for claim in (first, second) if claim is not None]
    assert len(claims) == 1
    assert claims[0].attempt_count == 1

    async with concurrent_session_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
        assert persisted.attempt_count == 1
        assert persisted.execution_task_id == claims[0].task_id
        task = await session.get(Task, claims[0].task_id)
        assert task is not None
        assert task.status == "running"


async def test_submission_checkpoint_consumes_allowance_once_and_then_resumes(db_factory) -> None:
    ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        claim = await queue.claim_next()
        assert claim is not None

    async with db_factory() as session:
        first = await H3RepairQueueService(session).reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert first.disposition is H3RepairSubmissionDisposition.SUBMIT_ALLOWED
        assert first.provider_call_count == 1

    # Simulate process interruption after the checkpoint was committed but before the
    # supplier task identity came back. The resumed process must not submit again.
    async with db_factory() as session:
        interrupted = await H3RepairQueueService(session).reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert interrupted.disposition is H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID
        assert interrupted.provider_call_count == 1
        assert interrupted.checkpoint.provider_id == "minimax"
        assert interrupted.checkpoint.provider_model == "MiniMax-H3"

    async with db_factory() as session:
        with pytest.raises(H3RepairExecutionConflict, match="checkpoint conflicts"):
            await H3RepairQueueService(session).reserve_provider_submission(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                current_facts=_facts(ticket),
                provider_id="other-provider",
                provider_model="Other-Model",
            )

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.persist_provider_job_identity(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            provider_job_id="provider-job-001",
            endpoint="minimax-h3",
            base_url="https://example.invalid",
        )
        await queue.persist_provider_job_identity(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            provider_job_id="provider-job-001",
        )
        with pytest.raises(H3RepairExecutionConflict, match="different provider job"):
            await queue.persist_provider_job_identity(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                provider_job_id="provider-job-002",
            )

    async with db_factory() as session:
        resumed = await H3RepairQueueService(session).reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert resumed.disposition is H3RepairSubmissionDisposition.RESUME_ONLY
        assert resumed.provider_job_id == "provider-job-001"
        assert resumed.provider_call_count == 1


async def test_stale_pre_submit_fails_without_consuming_allowance(db_factory) -> None:
    ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        queued = await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert await queue.claim_next() is not None

    stale = _facts(ticket)
    stale = H3RepairApprovalFacts(
        source_media_sha256="9" * 64,
        shot_id=stale.shot_id,
        repair_action=stale.repair_action,
        provider_prompt_sha256=stale.provider_prompt_sha256,
        reference_sha256=stale.reference_sha256,
    )
    async with db_factory() as session:
        with pytest.raises(H3RepairApprovalStaleError, match="source_media_sha256"):
            await H3RepairQueueService(session).reserve_provider_submission(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                current_facts=stale,
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.EXPIRED
        assert persisted.provider_call_count == 0
        task = await session.get(Task, queued.task_id)
        assert task is not None
        assert task.status == "failed"
        assert task.execution_checkpoint_json is None
        assert task.provider_job_id is None


async def test_project_call_ceiling_is_atomic_and_blocks_second_ticket(db_factory) -> None:
    first_ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    second_ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E13U03",
        source_digit="5",
    )
    facts = {
        first_ticket.ticket_id: _facts(first_ticket),
        second_ticket.ticket_id: _facts(second_ticket),
    }

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        budget = await queue.configure_project_call_ceiling(project_name="ai-boss", ceiling=1)
        assert budget.provider_call_count == 0
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=first_ticket.ticket_id)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=second_ticket.ticket_id)

        first_claim = await queue.claim_next()
        assert first_claim is not None
        first_reservation = await queue.reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=first_claim.ticket_id,
            current_facts=facts[first_claim.ticket_id],
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        assert first_reservation.disposition is H3RepairSubmissionDisposition.SUBMIT_ALLOWED
        assert first_reservation.project_provider_call_count == 1

        second_claim = await queue.claim_next()
        assert second_claim is not None
        with pytest.raises(H3RepairAllowanceExhausted, match="project H3 repair-call ceiling"):
            await queue.reserve_provider_submission(
                project_name="ai-boss",
                ticket_id=second_claim.ticket_id,
                current_facts=facts[second_claim.ticket_id],
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    async with db_factory() as session:
        budget = await session.get(H3RepairProjectBudget, "ai-boss")
        assert budget is not None
        assert budget.provider_call_count == 1
        blocked = await H3RepairTicketStore(session).load(
            project_name="ai-boss",
            ticket_id=second_claim.ticket_id,
        )
        assert blocked is not None
        assert blocked.lifecycle_state is H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED
        assert blocked.provider_call_count == 0
        assert blocked.execution_task_id is not None
        task = await session.get(Task, blocked.execution_task_id)
        assert task is not None
        assert task.status == "failed"
        assert task.provider_job_id is None
        assert task.execution_checkpoint_json is None


async def test_project_ceiling_cannot_be_lowered_below_consumed_reservations(db_factory) -> None:
    first_ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    second_ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E13U03",
        source_digit="5",
    )
    facts = {
        first_ticket.ticket_id: _facts(first_ticket),
        second_ticket.ticket_id: _facts(second_ticket),
    }
    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.configure_project_call_ceiling(project_name="ai-boss", ceiling=2)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=first_ticket.ticket_id)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=second_ticket.ticket_id)

        first_claim = await queue.claim_next()
        assert first_claim is not None
        await queue.reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=first_claim.ticket_id,
            current_facts=facts[first_claim.ticket_id],
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )
        second_claim = await queue.claim_next()
        assert second_claim is not None
        await queue.reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=second_claim.ticket_id,
            current_facts=facts[second_claim.ticket_id],
            provider_id="minimax",
            provider_model="MiniMax-H3",
        )

        with pytest.raises(ValueError, match="already reserved calls"):
            await queue.configure_project_call_ceiling(project_name="ai-boss", ceiling=1)



async def test_concurrent_submission_reservation_consumes_ticket_allowance_once(
    concurrent_session_factory,
) -> None:
    ticket = await _persist_approve(
        concurrent_session_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    async with concurrent_session_factory() as session:
        service = H3RepairQueueService(session)
        await service.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert await service.claim_next() is not None

    async def reserve_once():
        async with concurrent_session_factory() as session:
            return await H3RepairQueueService(session).reserve_provider_submission(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                current_facts=_facts(ticket),
                provider_id="minimax",
                provider_model="MiniMax-H3",
            )

    first, second = await asyncio.gather(reserve_once(), reserve_once())
    assert {first.disposition, second.disposition} == {
        H3RepairSubmissionDisposition.SUBMIT_ALLOWED,
        H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID,
    }
    assert first.provider_call_count == 1
    assert second.provider_call_count == 1

    async with concurrent_session_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.provider_call_count == 1
        assert persisted.execution_task_id is not None
        task = await session.get(Task, persisted.execution_task_id)
        assert task is not None
        assert task.execution_checkpoint_json is not None
        assert task.provider_job_id is None


async def test_concurrent_project_ceiling_allows_only_one_ticket_reservation(
    concurrent_session_factory,
) -> None:
    first_ticket = await _persist_approve(
        concurrent_session_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    second_ticket = await _persist_approve(
        concurrent_session_factory,
        project_name="ai-boss",
        unit_id="E13U03",
        source_digit="5",
    )
    facts = {
        first_ticket.ticket_id: _facts(first_ticket),
        second_ticket.ticket_id: _facts(second_ticket),
    }

    async with concurrent_session_factory() as session:
        service = H3RepairQueueService(session)
        await service.configure_project_call_ceiling(project_name="ai-boss", ceiling=1)
        await service.enqueue_approved_ticket(project_name="ai-boss", ticket_id=first_ticket.ticket_id)
        await service.enqueue_approved_ticket(project_name="ai-boss", ticket_id=second_ticket.ticket_id)
        first_claim = await service.claim_next()
        second_claim = await service.claim_next()
        assert first_claim is not None
        assert second_claim is not None

    async def reserve_or_block(ticket_id: str):
        async with concurrent_session_factory() as session:
            try:
                return await H3RepairQueueService(session).reserve_provider_submission(
                    project_name="ai-boss",
                    ticket_id=ticket_id,
                    current_facts=facts[ticket_id],
                    provider_id="minimax",
                    provider_model="MiniMax-H3",
                )
            except H3RepairAllowanceExhausted:
                return "blocked"

    first_result, second_result = await asyncio.gather(
        reserve_or_block(first_ticket.ticket_id),
        reserve_or_block(second_ticket.ticket_id),
    )
    results = (first_result, second_result)
    assert sum(result == "blocked" for result in results) == 1
    reservations = [result for result in results if result != "blocked"]
    assert len(reservations) == 1
    assert reservations[0].disposition is H3RepairSubmissionDisposition.SUBMIT_ALLOWED

    async with concurrent_session_factory() as session:
        budget = await session.get(H3RepairProjectBudget, "ai-boss")
        assert budget is not None
        assert budget.provider_call_count == 1
        first_persisted = await H3RepairTicketStore(session).load(
            project_name="ai-boss",
            ticket_id=first_ticket.ticket_id,
        )
        second_persisted = await H3RepairTicketStore(session).load(
            project_name="ai-boss",
            ticket_id=second_ticket.ticket_id,
        )
        assert first_persisted is not None
        assert second_persisted is not None
        assert sorted(
            (first_persisted.provider_call_count, second_persisted.provider_call_count)
        ) == [0, 1]
        assert {
            first_persisted.lifecycle_state,
            second_persisted.lifecycle_state,
        } == {
            H3RepairTicketLifecycleState.RUNNING,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
        }



async def test_provider_request_checkpoint_v2_freezes_actual_repair_request(db_factory) -> None:
    ticket = await _persist_approve(
        db_factory,
        project_name="ai-boss",
        unit_id="E12U06",
        source_digit="1",
    )
    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.enqueue_approved_ticket(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert await queue.claim_next() is not None

    repair_prompt = "single approved repair shot"
    provider_request = H3RepairProviderRequestFacts(
        generation_type="r2v",
        backend_model="MiniMax-H3",
        endpoint_guard="minimax-h3",
        prompt=repair_prompt,
        prompt_sha256=provider_prompt_sha256(repair_prompt),
        duration_seconds=5,
        aspect_ratio="16:9",
        resolution="768p",
        generate_audio=True,
        service_tier="default",
        seed=None,
    )
    async with db_factory() as session:
        first = await H3RepairQueueService(session).reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
            provider_request=provider_request,
        )
        assert first.disposition is H3RepairSubmissionDisposition.SUBMIT_ALLOWED
        assert first.checkpoint.schema_version == 2
        assert first.checkpoint.provider_request == provider_request

    async with db_factory() as session:
        repeated = await H3RepairQueueService(session).reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id="minimax",
            provider_model="MiniMax-H3",
            provider_request=provider_request,
        )
        assert repeated.disposition is H3RepairSubmissionDisposition.RESERVED_WITHOUT_PROVIDER_ID
        assert repeated.provider_call_count == 1
        assert repeated.checkpoint.provider_request == provider_request
