from __future__ import annotations

import pytest

from lib.reference_video.h3_repair_batch import H3RepairBatchAction
from server.services import h3_repair_batch_operator


@pytest.mark.asyncio
async def test_batch_execution_preserves_partial_success(monkeypatch) -> None:
    calls: list[str] = []

    async def approve(*, project_name: str, ticket_id: str, approved_by: str, max_provider_calls: int):
        calls.append(ticket_id)
        if ticket_id == "h3rt_bad":
            raise RuntimeError("stale approval")
        return {
            "ticket": {"ticket_id": ticket_id, "lifecycle": {"state": "approved"}},
            "approval": {"approved_by": approved_by},
        }

    monkeypatch.setattr(h3_repair_batch_operator, "approve_h3_repair", approve)

    result = await h3_repair_batch_operator.execute_h3_repair_batch(
        project_name="demo",
        action=H3RepairBatchAction.APPROVE,
        ticket_ids=("h3rt_good", "h3rt_bad", "h3rt_after"),
        actor="operator-1",
    )

    assert calls == ["h3rt_good", "h3rt_bad", "h3rt_after"]
    assert result.success_count == 2
    assert result.failure_count == 1
    assert [item.success for item in result.items] == [True, False, True]
    assert result.items[1].error_type == "RuntimeError"
    assert result.items[1].error_message == "stale approval"


@pytest.mark.asyncio
async def test_batch_approve_does_not_implicitly_enqueue(monkeypatch) -> None:
    approved: list[str] = []
    enqueued: list[str] = []

    async def approve(*, project_name: str, ticket_id: str, approved_by: str, max_provider_calls: int):
        approved.append(ticket_id)
        return {"ticket": {"ticket_id": ticket_id}, "approval": {"approved_by": approved_by}}

    async def enqueue(*, project_name: str, ticket_id: str, user_id: str):
        enqueued.append(ticket_id)
        return {"ticket": {"ticket_id": ticket_id}, "queue": {"deduped": False}}

    monkeypatch.setattr(h3_repair_batch_operator, "approve_h3_repair", approve)
    monkeypatch.setattr(h3_repair_batch_operator, "enqueue_h3_repair", enqueue)

    await h3_repair_batch_operator.execute_h3_repair_batch(
        project_name="demo",
        action=H3RepairBatchAction.APPROVE,
        ticket_ids=("h3rt_a", "h3rt_b"),
        actor="operator-1",
    )

    assert approved == ["h3rt_a", "h3rt_b"]
    assert enqueued == []


@pytest.mark.asyncio
async def test_batch_enqueue_delegates_existing_queue_dedupe(monkeypatch) -> None:
    async def enqueue(*, project_name: str, ticket_id: str, user_id: str):
        return {
            "ticket": {"ticket_id": ticket_id, "lifecycle": {"state": "queued"}},
            "queue": {
                "task_id": "task-existing",
                "execution_identity": "h3rx_existing",
                "task_status": "queued",
                "deduped": True,
            },
        }

    monkeypatch.setattr(h3_repair_batch_operator, "enqueue_h3_repair", enqueue)

    result = await h3_repair_batch_operator.execute_h3_repair_batch(
        project_name="demo",
        action=H3RepairBatchAction.ENQUEUE,
        ticket_ids=("h3rt_a",),
        actor="operator-1",
    )

    assert result.success_count == 1
    assert result.items[0].result is not None
    assert result.items[0].result["queue"]["deduped"] is True
    assert result.items[0].result["queue"]["execution_identity"] == "h3rx_existing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (H3RepairBatchAction.REJECT, "reject"),
        (H3RepairBatchAction.CANCEL, "cancel"),
    ],
)
async def test_batch_decisions_delegate_existing_operator_services(
    monkeypatch,
    action: H3RepairBatchAction,
    expected: str,
) -> None:
    seen: list[tuple[str, str | None]] = []

    async def reject(*, project_name: str, ticket_id: str, rejected_by: str, reason: str | None):
        seen.append(("reject", reason))
        return {"ticket_id": ticket_id}

    async def cancel(*, project_name: str, ticket_id: str, cancelled_by: str, reason: str | None):
        seen.append(("cancel", reason))
        return {"ticket": {"ticket_id": ticket_id}, "task_cancel": None}

    monkeypatch.setattr(h3_repair_batch_operator, "reject_h3_repair", reject)
    monkeypatch.setattr(h3_repair_batch_operator, "cancel_h3_repair", cancel)

    result = await h3_repair_batch_operator.execute_h3_repair_batch(
        project_name="demo",
        action=action,
        ticket_ids=("h3rt_a",),
        actor="operator-1",
        reason="operator batch decision",
    )

    assert result.success_count == 1
    assert seen == [(expected, "operator batch decision")]


@pytest.mark.asyncio
async def test_batch_rejects_duplicate_ids_before_any_write(monkeypatch) -> None:
    called = False

    async def approve(**_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(h3_repair_batch_operator, "approve_h3_repair", approve)

    with pytest.raises(ValueError, match="duplicate Repair Ticket"):
        await h3_repair_batch_operator.execute_h3_repair_batch(
            project_name="demo",
            action=H3RepairBatchAction.APPROVE,
            ticket_ids=("h3rt_a", "h3rt_a"),
            actor="operator-1",
        )

    assert called is False
