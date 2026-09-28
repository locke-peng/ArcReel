"""Phase 6 Slice 2 batch coordination preview contract.

A batch is only a coordination envelope around existing Phase 5 Repair Tickets. This
module does not create approvals, queue identities, repair policy, or provider calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    PersistedH3RepairTicket,
)


class H3RepairBatchAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"
    ENQUEUE = "enqueue"


@dataclass(frozen=True, slots=True)
class H3RepairBatchPreviewItem:
    ticket_id: str
    unit_id: str
    shot_id: str | None
    lifecycle_state: str
    action: H3RepairBatchAction
    eligible: bool
    reason: str
    existing_execution_task_id: str | None


@dataclass(frozen=True, slots=True)
class H3RepairBatchPreview:
    project_name: str
    action: H3RepairBatchAction
    items: tuple[H3RepairBatchPreviewItem, ...]

    @property
    def eligible_count(self) -> int:
        return sum(item.eligible for item in self.items)

    @property
    def blocked_count(self) -> int:
        return len(self.items) - self.eligible_count


_CANCELABLE = frozenset(
    {
        H3RepairTicketLifecycleState.AWAITING_APPROVAL,
        H3RepairTicketLifecycleState.APPROVED,
        H3RepairTicketLifecycleState.QUEUED,
        H3RepairTicketLifecycleState.RUNNING,
    }
)


def _preview_ticket(
    ticket: PersistedH3RepairTicket,
    action: H3RepairBatchAction,
) -> H3RepairBatchPreviewItem:
    state = ticket.lifecycle_state
    eligible = False
    reason = ""

    if action is H3RepairBatchAction.APPROVE:
        eligible = (
            state is H3RepairTicketLifecycleState.AWAITING_APPROVAL
            and ticket.ticket.approval_eligible
        )
        reason = (
            "approval_pending"
            if eligible
            else (
                "ticket_not_approval_eligible"
                if not ticket.ticket.approval_eligible
                else f"lifecycle_not_approval_pending:{state.value}"
            )
        )
    elif action is H3RepairBatchAction.REJECT:
        eligible = state is H3RepairTicketLifecycleState.AWAITING_APPROVAL
        reason = "approval_pending" if eligible else f"lifecycle_not_rejectable:{state.value}"
    elif action is H3RepairBatchAction.CANCEL:
        eligible = state in _CANCELABLE
        reason = "cancelable" if eligible else f"lifecycle_not_cancelable:{state.value}"
    elif action is H3RepairBatchAction.ENQUEUE:
        if ticket.execution_task_id is not None:
            eligible = True
            reason = "existing_execution_will_dedupe"
        else:
            eligible = state is H3RepairTicketLifecycleState.APPROVED
            reason = "approved_and_queueable" if eligible else f"lifecycle_not_queueable:{state.value}"

    return H3RepairBatchPreviewItem(
        ticket_id=ticket.ticket.ticket_id,
        unit_id=ticket.ticket.unit_id,
        shot_id=ticket.ticket.shot_id,
        lifecycle_state=state.value,
        action=action,
        eligible=eligible,
        reason=reason,
        existing_execution_task_id=ticket.execution_task_id,
    )


def build_h3_repair_batch_preview(
    *,
    project_name: str,
    action: H3RepairBatchAction,
    tickets: Iterable[PersistedH3RepairTicket],
) -> H3RepairBatchPreview:
    """Return a deterministic per-ticket preview without mutating any state."""

    normalized = project_name.strip()
    if not normalized:
        raise ValueError("project_name is required")

    seen: set[str] = set()
    items: list[H3RepairBatchPreviewItem] = []
    for ticket in tickets:
        if ticket.project_name != normalized:
            raise ValueError("batch preview received a Repair Ticket from another project")
        ticket_id = ticket.ticket.ticket_id
        if ticket_id in seen:
            raise ValueError(f"duplicate Repair Ticket in batch: {ticket_id}")
        seen.add(ticket_id)
        items.append(_preview_ticket(ticket, action))

    items.sort(key=lambda item: item.ticket_id)
    return H3RepairBatchPreview(
        project_name=normalized,
        action=action,
        items=tuple(items),
    )
