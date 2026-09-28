from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_approval_service import (
    H3ProviderRepairApprovalBinding,
    H3RepairApprovalConflictError,
    H3RepairApprovalFacts,
    H3RepairApprovalService,
    H3RepairApprovalStaleError,
)
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState, H3RepairTicketStore
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)


def _provider_ticket():
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


async def _persist(db_factory, *, project_name: str = "ai-boss"):
    ticket = _provider_ticket()
    async with db_factory() as session:
        await H3RepairTicketStore(session).persist(project_name=project_name, ticket=ticket)
        await session.commit()
    return ticket


async def test_approve_persists_full_binding_and_audit(db_factory) -> None:
    ticket = await _persist(db_factory)
    approved_at = datetime(2026, 9, 28, 4, 0, tzinfo=UTC)

    async with db_factory() as session:
        result = await H3RepairApprovalService(session).approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            approved_at=approved_at,
            current_facts=_facts(ticket),
        )
        assert result.ticket.lifecycle_state is H3RepairTicketLifecycleState.APPROVED
        assert result.ticket.approval_identity == "operator:jane"
        assert result.ticket.approval_at == approved_at
        assert result.ticket.max_provider_calls == 1
        assert result.ticket.lifecycle_actor == "operator:jane"
        assert result.ticket.lifecycle_at == approved_at
        assert result.approval.repair_action == ticket.repair_action
        assert result.approval.provider_prompt_sha256 == ticket.provider_prompt_sha256
        assert result.approval.reference_sha256 == ticket.reference_sha256
        assert result.ticket.approval_json == result.approval.to_json()

        phase4 = result.approval.to_phase4_approval()
        assert phase4.ticket_id == ticket.ticket_id
        assert phase4.ticket_sha256 == ticket.ticket_sha256
        assert phase4.source_media_sha256 == ticket.source_media_sha256
        assert phase4.shot_id == ticket.shot_id


async def test_duplicate_approval_by_same_actor_is_idempotent(db_factory) -> None:
    ticket = await _persist(db_factory)
    first_at = datetime(2026, 9, 28, 4, 0, tzinfo=UTC)
    async with db_factory() as session:
        service = H3RepairApprovalService(session)
        first = await service.approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            approved_at=first_at,
            current_facts=_facts(ticket),
        )
        second = await service.approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            approved_at=datetime(2026, 9, 28, 5, 0, tzinfo=UTC),
            current_facts=_facts(ticket),
        )
        assert second.approval == first.approval
        assert second.ticket.approval_at == first_at


async def test_duplicate_approval_by_different_actor_fails_closed(db_factory) -> None:
    ticket = await _persist(db_factory)
    async with db_factory() as session:
        service = H3RepairApprovalService(session)
        await service.approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            current_facts=_facts(ticket),
        )
        with pytest.raises(H3RepairApprovalConflictError, match="different approval identity"):
            await service.approve(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                approved_by="operator:other",
                current_facts=_facts(ticket),
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_media_sha256", "9" * 64),
        ("shot_id", "E12U06-S01"),
        ("repair_action", "recompile_dialogue_detached"),
        ("provider_prompt_sha256", "8" * 64),
        ("reference_sha256", ("7" * 64,)),
    ],
)
async def test_mutated_binding_expires_before_approval(db_factory, field: str, value) -> None:
    ticket = await _persist(db_factory)
    facts = _facts(ticket)
    mutated = H3RepairApprovalFacts(
        source_media_sha256=value if field == "source_media_sha256" else facts.source_media_sha256,
        shot_id=value if field == "shot_id" else facts.shot_id,
        repair_action=value if field == "repair_action" else facts.repair_action,
        provider_prompt_sha256=value if field == "provider_prompt_sha256" else facts.provider_prompt_sha256,
        reference_sha256=value if field == "reference_sha256" else facts.reference_sha256,
    )

    async with db_factory() as session:
        with pytest.raises(H3RepairApprovalStaleError, match=field):
            await H3RepairApprovalService(session).approve(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                approved_by="operator:jane",
                current_facts=mutated,
            )

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.EXPIRED
        assert persisted.lifecycle_actor == "operator:jane"
        assert persisted.provider_call_count == 0
        assert persisted.approval_json is None


async def test_revalidation_expires_approved_ticket_when_prompt_changes(db_factory) -> None:
    ticket = await _persist(db_factory)
    async with db_factory() as session:
        service = H3RepairApprovalService(session)
        await service.approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            current_facts=_facts(ticket),
        )

    changed = _facts(ticket)
    stale = H3RepairApprovalFacts(
        source_media_sha256=changed.source_media_sha256,
        shot_id=changed.shot_id,
        repair_action=changed.repair_action,
        provider_prompt_sha256="f" * 64,
        reference_sha256=changed.reference_sha256,
    )
    async with db_factory() as session:
        with pytest.raises(H3RepairApprovalStaleError, match="provider_prompt_sha256"):
            await H3RepairApprovalService(session).validate_for_execution(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                current_facts=stale,
            )

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.EXPIRED
        assert persisted.provider_call_count == 0


async def test_reject_and_cancel_persist_actor_timestamp_and_reason(db_factory) -> None:
    reject_ticket = await _persist(db_factory, project_name="reject-project")
    cancel_ticket = await _persist(db_factory, project_name="cancel-project")
    decision_at = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)

    async with db_factory() as session:
        rejected = await H3RepairApprovalService(session).reject(
            project_name="reject-project",
            ticket_id=reject_ticket.ticket_id,
            rejected_by="operator:jane",
            reason="scope not approved",
            rejected_at=decision_at,
        )
        assert rejected.lifecycle_state is H3RepairTicketLifecycleState.REJECTED
        assert rejected.lifecycle_actor == "operator:jane"
        assert rejected.lifecycle_at == decision_at
        assert rejected.lifecycle_reason == "scope not approved"

    async with db_factory() as session:
        cancelled = await H3RepairApprovalService(session).cancel(
            project_name="cancel-project",
            ticket_id=cancel_ticket.ticket_id,
            cancelled_by="operator:jane",
            reason="operator cancelled",
            cancelled_at=decision_at,
        )
        assert cancelled.lifecycle_state is H3RepairTicketLifecycleState.CANCELLED
        assert cancelled.lifecycle_actor == "operator:jane"
        assert cancelled.lifecycle_at == decision_at
        assert cancelled.lifecycle_reason == "operator cancelled"


def test_approval_binding_round_trip_keeps_explicit_action_prompt_and_references() -> None:
    binding = H3ProviderRepairApprovalBinding(
        ticket_id="h3rt_" + "a" * 24,
        ticket_sha256="b" * 64,
        source_media_sha256="c" * 64,
        shot_id="E13U03-S01",
        repair_action="regenerate_with_identity_bridge",
        provider_prompt_sha256="d" * 64,
        reference_sha256=("e" * 64, "f" * 64),
        approved_by="operator:jane",
        approved_at="2026-09-28T06:00:00+00:00",
    )
    assert H3ProviderRepairApprovalBinding.from_json(binding.to_json()) == binding


async def test_tampered_persisted_approval_snapshot_fails_closed(db_factory) -> None:
    ticket = await _persist(db_factory)
    async with db_factory() as session:
        service = H3RepairApprovalService(session)
        result = await service.approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:jane",
            current_facts=_facts(ticket),
        )
        record = await service.repository.get(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert record is not None
        tampered = result.approval.to_dict()
        tampered["repair_action"] = "recompile_dialogue_detached"
        import json

        record.approval_json = json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        await session.commit()

    async with db_factory() as session:
        with pytest.raises(RuntimeError, match="repair action"):
            await H3RepairApprovalService(session).approve(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                approved_by="operator:jane",
                current_facts=_facts(ticket),
            )


async def test_naive_approval_timestamp_is_rejected(db_factory) -> None:
    ticket = await _persist(db_factory)
    async with db_factory() as session:
        with pytest.raises(ValueError, match="timezone-aware"):
            await H3RepairApprovalService(session).approve(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                approved_by="operator:jane",
                current_facts=_facts(ticket),
                approved_at=datetime(2026, 9, 28, 4, 0),
            )
