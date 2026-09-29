from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from lib.reference_video.h3_repair_batch import (
    H3RepairBatchAction,
    build_h3_repair_batch_preview,
)
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState


def _ticket(
    *,
    ticket_id: str,
    state: H3RepairTicketLifecycleState,
    approval_eligible: bool = True,
    task_id: str | None = None,
    project: str = "demo",
):
    return SimpleNamespace(
        project_name=project,
        ticket=SimpleNamespace(
            ticket_id=ticket_id,
            unit_id="E1U01",
            shot_id="E1U01-S01",
            approval_eligible=approval_eligible,
        ),
        lifecycle_state=state,
        execution_task_id=task_id,
        created_at=datetime(2026, 9, 28, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("action", "state", "approval_eligible", "task_id", "eligible", "reason"),
    [
        (
            H3RepairBatchAction.APPROVE,
            H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            True,
            None,
            True,
            "approval_pending",
        ),
        (
            H3RepairBatchAction.APPROVE,
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            False,
            None,
            False,
            "ticket_not_approval_eligible",
        ),
        (
            H3RepairBatchAction.REJECT,
            H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            True,
            None,
            True,
            "approval_pending",
        ),
        (
            H3RepairBatchAction.REJECT,
            H3RepairTicketLifecycleState.APPROVED,
            True,
            None,
            False,
            "lifecycle_not_rejectable:approved",
        ),
        (
            H3RepairBatchAction.CANCEL,
            H3RepairTicketLifecycleState.RUNNING,
            True,
            "task-1",
            True,
            "cancelable",
        ),
        (
            H3RepairBatchAction.CANCEL,
            H3RepairTicketLifecycleState.ACCEPTED,
            True,
            "task-1",
            False,
            "lifecycle_not_cancelable:accepted",
        ),
        (
            H3RepairBatchAction.ENQUEUE,
            H3RepairTicketLifecycleState.APPROVED,
            True,
            None,
            True,
            "approved_and_queueable",
        ),
        (
            H3RepairBatchAction.ENQUEUE,
            H3RepairTicketLifecycleState.QUEUED,
            True,
            "task-1",
            True,
            "existing_execution_will_dedupe",
        ),
        (
            H3RepairBatchAction.ENQUEUE,
            H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            True,
            None,
            False,
            "lifecycle_not_queueable:awaiting_approval",
        ),
    ],
)
def test_batch_preview_is_per_ticket_and_descriptive(
    action: H3RepairBatchAction,
    state: H3RepairTicketLifecycleState,
    approval_eligible: bool,
    task_id: str | None,
    eligible: bool,
    reason: str,
) -> None:
    preview = build_h3_repair_batch_preview(
        project_name="demo",
        action=action,
        tickets=(
            _ticket(
                ticket_id="h3rt_a",
                state=state,
                approval_eligible=approval_eligible,
                task_id=task_id,
            ),
        ),
    )

    assert preview.eligible_count == int(eligible)
    assert preview.blocked_count == int(not eligible)
    item = preview.items[0]
    assert item.eligible is eligible
    assert item.reason == reason
    assert item.action is action


def test_batch_preview_preserves_partial_eligibility_and_stable_order() -> None:
    preview = build_h3_repair_batch_preview(
        project_name="demo",
        action=H3RepairBatchAction.APPROVE,
        tickets=(
            _ticket(
                ticket_id="h3rt_b",
                state=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
                approval_eligible=False,
            ),
            _ticket(
                ticket_id="h3rt_a",
                state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            ),
        ),
    )

    assert [item.ticket_id for item in preview.items] == ["h3rt_a", "h3rt_b"]
    assert preview.eligible_count == 1
    assert preview.blocked_count == 1
    assert preview.items[0].eligible is True
    assert preview.items[1].eligible is False


def test_batch_preview_rejects_duplicate_or_cross_project_tickets() -> None:
    ticket = _ticket(
        ticket_id="h3rt_a",
        state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
    )
    with pytest.raises(ValueError, match="duplicate Repair Ticket"):
        build_h3_repair_batch_preview(
            project_name="demo",
            action=H3RepairBatchAction.APPROVE,
            tickets=(ticket, ticket),
        )

    with pytest.raises(ValueError, match="another project"):
        build_h3_repair_batch_preview(
            project_name="demo",
            action=H3RepairBatchAction.APPROVE,
            tickets=(
                _ticket(
                    ticket_id="h3rt_x",
                    state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
                    project="other",
                ),
            ),
        )
