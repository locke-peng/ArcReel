from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lib.reference_video.h3_repair_ticket import (
    H3RepairScopeKind,
    H3RepairTicket,
    H3RepairTicketStatus,
)
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    PersistedH3RepairTicket,
)
from server.services import h3_repair_operator


def _persisted(
    *,
    lifecycle_state: H3RepairTicketLifecycleState = H3RepairTicketLifecycleState.AWAITING_APPROVAL,
    execution_task_id: str | None = None,
    max_provider_calls: int | None = None,
    provider_call_count: int = 0,
) -> PersistedH3RepairTicket:
    now = datetime(2026, 9, 28, 11, 0, tzinfo=UTC)
    ticket = H3RepairTicket(
        schema_version=1,
        ticket_id="h3rt_test",
        ticket_sha256="a" * 64,
        status=H3RepairTicketStatus.AWAITING_APPROVAL,
        approval_eligible=True,
        unit_id="E13U03",
        shot_id="E13U03-S02",
        scope_kind=H3RepairScopeKind.SHOT,
        start_seconds=5.0,
        end_seconds=10.0,
        region=None,
        failure_class="large_semantic_failure",
        repair_action="shot_scoped_regeneration",
        provider_recall_required=True,
        canonical_violation="invented non-canonical content",
        planner_reason="provider repair required",
        source_media_sha256="b" * 64,
        provider_prompt_sha256="c" * 64,
        reference_sha256=("d" * 64,),
        evidence_frames=(120,),
        tags=("semantic_failure",),
    )
    return PersistedH3RepairTicket(
        project_name="demo",
        ticket=ticket,
        lifecycle_state=lifecycle_state,
        lifecycle_reason=None,
        lifecycle_actor=None,
        lifecycle_at=now,
        approval_json=None,
        approval_identity=None,
        approval_at=None,
        max_provider_calls=max_provider_calls,
        execution_identity="h3exec_test" if execution_task_id else None,
        execution_task_id=execution_task_id,
        attempt_count=1 if execution_task_id else 0,
        provider_call_count=provider_call_count,
        repair_output_sha256=None,
        reqa_outcome=None,
        selected_artifact_id=None,
        selected_version_id=None,
        created_at=now,
        updated_at=now,
    )


def test_ticket_view_exposes_operator_required_fields() -> None:
    view = h3_repair_operator._ticket_view(
        _persisted(max_provider_calls=1, provider_call_count=0),
    )

    assert view["unit_id"] == "E13U03"
    assert view["shot_id"] == "E13U03-S02"
    assert view["failure_class"] == "large_semantic_failure"
    assert view["repair_action"] == "shot_scoped_regeneration"
    assert view["time_range"] == {"start_seconds": 5.0, "end_seconds": 10.0}
    assert view["provenance"]["provider_prompt_sha256"] == "c" * 64
    assert view["provenance"]["reference_sha256"] == ["d" * 64]
    assert view["provider_call_allowance"] == {
        "max_provider_calls": 1,
        "provider_call_count": 0,
        "remaining_provider_calls": 1,
    }
    assert view["lifecycle"]["state"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_approve_operator_reuses_approval_service_then_enqueues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _persisted()
    queued = _persisted(
        lifecycle_state=H3RepairTicketLifecycleState.QUEUED,
        execution_task_id="task-1",
        max_provider_calls=1,
    )
    store = SimpleNamespace(load=AsyncMock(side_effect=[initial, queued]))
    approval_binding = SimpleNamespace(to_dict=lambda: {"ticket_id": initial.ticket.ticket_id})
    approval_service = SimpleNamespace(
        approve=AsyncMock(return_value=SimpleNamespace(approval=approval_binding)),
    )
    queue_service = SimpleNamespace(
        enqueue_approved_ticket=AsyncMock(
            return_value=SimpleNamespace(
                task_id="task-1",
                execution_identity="h3exec_test",
                task_status="queued",
                deduped=False,
            )
        ),
    )

    class _SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(h3_repair_operator, "_project_path", AsyncMock(return_value=Path("/tmp/demo")))
    monkeypatch.setattr(h3_repair_operator, "safe_session_factory", lambda: _SessionContext())
    monkeypatch.setattr(h3_repair_operator, "H3RepairTicketStore", lambda _session: store)
    monkeypatch.setattr(h3_repair_operator, "H3RepairApprovalService", lambda _session: approval_service)
    monkeypatch.setattr(h3_repair_operator, "H3RepairQueueService", lambda _session: queue_service)
    monkeypatch.setattr(
        h3_repair_operator,
        "resolve_h3_repair_source_version",
        lambda **_kwargs: SimpleNamespace(
            media_sha256="b" * 64,
            provider_prompt_sha256="c" * 64,
        ),
    )

    result = await h3_repair_operator.approve_and_enqueue_h3_repair(
        project_name="demo",
        ticket_id=initial.ticket.ticket_id,
        approved_by="operator:alice",
    )

    current_facts = approval_service.approve.await_args.kwargs["current_facts"]
    assert current_facts.source_media_sha256 == "b" * 64
    assert current_facts.shot_id == "E13U03-S02"
    assert current_facts.repair_action == "shot_scoped_regeneration"
    assert current_facts.provider_prompt_sha256 == "c" * 64
    approval_service.approve.assert_awaited_once()
    queue_service.enqueue_approved_ticket.assert_awaited_once_with(
        project_name="demo",
        ticket_id="h3rt_test",
    )
    assert result["queue"] == {
        "task_id": "task-1",
        "execution_identity": "h3exec_test",
        "task_status": "queued",
        "deduped": False,
    }
    assert result["ticket"]["lifecycle"]["state"] == "queued"


@pytest.mark.asyncio
async def test_execution_status_does_not_expose_internal_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = _persisted(
        lifecycle_state=H3RepairTicketLifecycleState.RUNNING,
        execution_task_id="task-1",
        max_provider_calls=1,
        provider_call_count=1,
    )
    monkeypatch.setattr(h3_repair_operator, "_load_required", AsyncMock(return_value=persisted))
    queue = SimpleNamespace(
        get_task=AsyncMock(
            return_value={
                "task_id": "task-1",
                "status": "running",
                "provider_id": "minimax",
                "provider_job_id": "job-1",
                "provider_endpoint": "video_generation",
                "execution_checkpoint_json": "secret-internal-checkpoint",
            }
        )
    )
    monkeypatch.setattr(h3_repair_operator, "get_generation_queue", lambda: queue)

    result = await h3_repair_operator.get_h3_repair_execution_status(
        project_name="demo",
        ticket_id="h3rt_test",
    )

    assert result["task"]["provider_job_id"] == "job-1"
    assert "execution_checkpoint_json" not in result["task"]
    assert result["provider_call_count"] == 1
