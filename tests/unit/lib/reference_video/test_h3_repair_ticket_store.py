from __future__ import annotations

from dataclasses import replace

import pytest

from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
    validate_h3_repair_ticket_transition,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)


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
            provider_task_id="historical-provider-task",
            provider_run_id=36370583579,
            provider_artifact_id=10948993658,
        ),
    )


async def test_ticket_persistence_round_trip_preserves_immutable_identity(db_factory) -> None:
    ticket = _ticket()
    async with db_factory() as session:
        stored = await H3RepairTicketStore(session).persist(project_name="ai-boss", ticket=ticket)
        assert stored.lifecycle_state is H3RepairTicketLifecycleState.AWAITING_APPROVAL
        await session.commit()

    async with db_factory() as session:
        loaded = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert loaded is not None
        assert loaded.ticket == ticket
        assert loaded.ticket.to_dict() == ticket.to_dict()
        assert loaded.project_name == "ai-boss"
        assert loaded.attempt_count == 0
        assert loaded.provider_call_count == 0


async def test_persist_same_ticket_is_idempotent_and_tampering_fails_closed(db_factory) -> None:
    ticket = _ticket()
    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        first = await store.persist(project_name="ai-boss", ticket=ticket)
        second = await store.persist(project_name="ai-boss", ticket=ticket)
        assert second.ticket == first.ticket

        forged = replace(ticket, source_media_sha256="9" * 64)
        with pytest.raises(RuntimeError, match="cryptographic identity"):
            await store.persist(project_name="ai-boss", ticket=forged)


async def test_same_deterministic_ticket_identity_is_isolated_by_project(db_factory) -> None:
    ticket = _ticket()
    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        await store.persist(project_name="project-a", ticket=ticket)
        await store.persist(project_name="project-b", ticket=ticket)
        await session.commit()

    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        a = await store.load(project_name="project-a", ticket_id=ticket.ticket_id)
        b = await store.load(project_name="project-b", ticket_id=ticket.ticket_id)
        assert a is not None
        assert b is not None
        assert a.project_name == "project-a"
        assert b.project_name == "project-b"


async def test_lifecycle_transition_is_persisted_and_skip_fails_closed(db_factory) -> None:
    ticket = _ticket()
    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        await store.persist(project_name="ai-boss", ticket=ticket)
        approved = await store.transition(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            target=H3RepairTicketLifecycleState.APPROVED,
        )
        assert approved.lifecycle_state is H3RepairTicketLifecycleState.APPROVED
        queued = await store.transition(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            target=H3RepairTicketLifecycleState.QUEUED,
        )
        assert queued.lifecycle_state is H3RepairTicketLifecycleState.QUEUED
        with pytest.raises(RuntimeError, match="illegal H3 Repair Ticket lifecycle transition"):
            await store.transition(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                target=H3RepairTicketLifecycleState.ACCEPTED,
            )


def test_lifecycle_validator_allows_idempotent_same_state_and_rejects_backwards() -> None:
    validate_h3_repair_ticket_transition(
        H3RepairTicketLifecycleState.QUEUED,
        H3RepairTicketLifecycleState.QUEUED,
    )
    with pytest.raises(RuntimeError, match="queued -> approved"):
        validate_h3_repair_ticket_transition(
            H3RepairTicketLifecycleState.QUEUED,
            H3RepairTicketLifecycleState.APPROVED,
        )
    with pytest.raises(RuntimeError, match="accepted -> reqa_running"):
        validate_h3_repair_ticket_transition(
            H3RepairTicketLifecycleState.ACCEPTED,
            H3RepairTicketLifecycleState.REQA_RUNNING,
        )
