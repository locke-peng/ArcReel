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


async def test_project_pause_skips_queued_repairs_without_mutating_them(db_factory) -> None:
    paused_ticket = await _persist_approve(
        db_factory,
        project_name="project-a",
        unit_id="E1U01",
        source_digit="5",
    )
    active_ticket = await _persist_approve(
        db_factory,
        project_name="project-b",
        unit_id="E2U01",
        source_digit="6",
    )

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.enqueue_approved_ticket(
            project_name="project-a",
            ticket_id=paused_ticket.ticket_id,
        )
        await queue.enqueue_approved_ticket(
            project_name="project-b",
            ticket_id=active_ticket.ticket_id,
        )
        control = await queue.set_project_paused(project_name="project-a", paused=True)
        assert control.paused is True

    async with db_factory() as session:
        claim = await H3RepairQueueService(session).claim_next()
        assert claim is not None
        assert claim.project_name == "project-b"
        assert claim.ticket_id == active_ticket.ticket_id

        paused = await H3RepairTicketStore(session).load(
            project_name="project-a",
            ticket_id=paused_ticket.ticket_id,
        )
        assert paused is not None
        assert paused.lifecycle_state is H3RepairTicketLifecycleState.QUEUED
        paused_task = await session.get(Task, paused.execution_task_id)
        assert paused_task is not None
        assert paused_task.status == "queued"


async def test_project_running_cap_blocks_second_claim_until_capacity_is_released(db_factory) -> None:
    first_ticket = await _persist_approve(
        db_factory,
        project_name="project-cap",
        unit_id="E3U01",
        source_digit="7",
    )
    second_ticket = await _persist_approve(
        db_factory,
        project_name="project-cap",
        unit_id="E3U02",
        source_digit="8",
    )

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.enqueue_approved_ticket(
            project_name="project-cap",
            ticket_id=first_ticket.ticket_id,
        )
        await queue.enqueue_approved_ticket(
            project_name="project-cap",
            ticket_id=second_ticket.ticket_id,
        )
        control = await queue.configure_project_running_cap(
            project_name="project-cap",
            max_running_tasks=1,
        )
        assert control.max_running_tasks == 1

    async with db_factory() as session:
        first_claim = await H3RepairQueueService(session).claim_next()
        assert first_claim is not None
        assert first_claim.project_name == "project-cap"

    async with db_factory() as session:
        blocked = await H3RepairQueueService(session).claim_next()
        assert blocked is None

        tickets = await H3RepairTicketStore(session).list_for_project(
            project_name="project-cap",
            limit=10,
        )
        states = {ticket.ticket.ticket_id: ticket.lifecycle_state for ticket in tickets}
        queued_ids = [
            ticket_id
            for ticket_id, state in states.items()
            if state is H3RepairTicketLifecycleState.QUEUED
        ]
        assert len(queued_ids) == 1

    async with db_factory() as session:
        first = await H3RepairTicketStore(session).load(
            project_name="project-cap",
            ticket_id=first_claim.ticket_id,
        )
        assert first is not None
        task = await session.get(Task, first.execution_task_id)
        assert task is not None
        task.status = "succeeded"
        for state in (
            H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            H3RepairTicketLifecycleState.REASSEMBLING,
            H3RepairTicketLifecycleState.REQA_RUNNING,
            H3RepairTicketLifecycleState.ACCEPTED,
        ):
            await H3RepairTicketStore(session).transition(
                project_name="project-cap",
                ticket_id=first_claim.ticket_id,
                target=state,
                reason="release project capacity in test",
            )
        await session.commit()

    async with db_factory() as session:
        second_claim = await H3RepairQueueService(session).claim_next()
        assert second_claim is not None
        assert second_claim.project_name == "project-cap"
        assert second_claim.ticket_id != first_claim.ticket_id


async def test_project_control_defaults_to_unpaused_and_unlimited(db_factory) -> None:
    ticket = await _persist_approve(
        db_factory,
        project_name="project-default",
        unit_id="E4U01",
        source_digit="9",
    )
    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        assert await queue.get_project_control(project_name="project-default") is None
        await queue.enqueue_approved_ticket(
            project_name="project-default",
            ticket_id=ticket.ticket_id,
        )
        claim = await queue.claim_next()
        assert claim is not None
        assert claim.project_name == "project-default"


async def test_project_running_cap_rejects_zero(db_factory) -> None:
    async with db_factory() as session:
        with pytest.raises(ValueError, match="must be >= 1 or null"):
            await H3RepairQueueService(session).configure_project_running_cap(
                project_name="project-cap",
                max_running_tasks=0,
            )


async def test_project_fairness_prefers_project_with_fewer_running_repairs(db_factory) -> None:
    a1 = await _persist_approve(
        db_factory,
        project_name="project-a",
        unit_id="E5U01",
        source_digit="a",
    )
    a2 = await _persist_approve(
        db_factory,
        project_name="project-a",
        unit_id="E5U02",
        source_digit="b",
    )
    b1 = await _persist_approve(
        db_factory,
        project_name="project-b",
        unit_id="E6U01",
        source_digit="c",
    )

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.enqueue_approved_ticket(project_name="project-a", ticket_id=a1.ticket_id)
        await queue.enqueue_approved_ticket(project_name="project-a", ticket_id=a2.ticket_id)
        await queue.enqueue_approved_ticket(project_name="project-b", ticket_id=b1.ticket_id)

    async with db_factory() as session:
        first = await H3RepairQueueService(session).claim_next()
        assert first is not None
        assert first.project_name == "project-a"

    async with db_factory() as session:
        second = await H3RepairQueueService(session).claim_next()
        assert second is not None
        assert second.project_name == "project-b"


async def test_project_pause_resume_and_cap_survive_new_sessions(db_factory) -> None:
    ticket = await _persist_approve(
        db_factory,
        project_name="project-persisted-control",
        unit_id="E7U01",
        source_digit="d",
    )

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        await queue.enqueue_approved_ticket(
            project_name="project-persisted-control",
            ticket_id=ticket.ticket_id,
        )
        await queue.configure_project_running_cap(
            project_name="project-persisted-control",
            max_running_tasks=1,
        )
        await queue.set_project_paused(
            project_name="project-persisted-control",
            paused=True,
        )

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        control = await queue.get_project_control(project_name="project-persisted-control")
        assert control is not None
        assert control.paused is True
        assert control.max_running_tasks == 1
        assert await queue.claim_next() is None

    async with db_factory() as session:
        queue = H3RepairQueueService(session)
        resumed = await queue.set_project_paused(
            project_name="project-persisted-control",
            paused=False,
        )
        assert resumed.paused is False

    async with db_factory() as session:
        claim = await H3RepairQueueService(session).claim_next()
        assert claim is not None
        assert claim.project_name == "project-persisted-control"
