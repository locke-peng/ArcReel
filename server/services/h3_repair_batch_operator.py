"""Phase 6 Slice 2 batch coordination over existing Phase 5 operator services.

Each ticket is executed independently. A batch is not a transaction, approval primitive,
queue, or provider submission boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable

from lib.reference_video.h3_repair_batch import H3RepairBatchAction
from server.services.h3_repair_operator import (
    approve_h3_repair,
    cancel_h3_repair,
    enqueue_h3_repair,
    reject_h3_repair,
)


@dataclass(frozen=True, slots=True)
class H3RepairBatchExecutionItem:
    ticket_id: str
    action: H3RepairBatchAction
    success: bool
    result: dict[str, Any] | None
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class H3RepairBatchExecutionResult:
    project_name: str
    action: H3RepairBatchAction
    items: tuple[H3RepairBatchExecutionItem, ...]

    @property
    def success_count(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failure_count(self) -> int:
        return len(self.items) - self.success_count


def _normalize_ticket_ids(ticket_ids: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in ticket_ids:
        ticket_id = raw.strip()
        if not ticket_id:
            raise ValueError("batch ticket_id is required")
        if ticket_id in seen:
            raise ValueError(f"duplicate Repair Ticket in batch: {ticket_id}")
        seen.add(ticket_id)
        normalized.append(ticket_id)
    return tuple(normalized)


async def _execute_one(
    *,
    action: H3RepairBatchAction,
    project_name: str,
    ticket_id: str,
    actor: str,
    reason: str | None,
) -> dict[str, Any]:
    if action is H3RepairBatchAction.APPROVE:
        return await approve_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            approved_by=actor,
            max_provider_calls=1,
        )
    if action is H3RepairBatchAction.REJECT:
        return await reject_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            rejected_by=actor,
            reason=reason,
        )
    if action is H3RepairBatchAction.CANCEL:
        return await cancel_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            cancelled_by=actor,
            reason=reason,
        )
    if action is H3RepairBatchAction.ENQUEUE:
        return await enqueue_h3_repair(
            project_name=project_name,
            ticket_id=ticket_id,
            user_id=actor,
        )
    raise ValueError(f"unsupported batch action: {action}")


async def execute_h3_repair_batch(
    *,
    project_name: str,
    action: H3RepairBatchAction,
    ticket_ids: Iterable[str],
    actor: str,
    reason: str | None = None,
) -> H3RepairBatchExecutionResult:
    """Execute tickets independently and retain per-ticket partial success/failure."""

    normalized_project = project_name.strip()
    normalized_actor = actor.strip()
    if not normalized_project:
        raise ValueError("project_name is required")
    if not normalized_actor:
        raise ValueError("batch actor is required")

    ids = _normalize_ticket_ids(ticket_ids)
    items: list[H3RepairBatchExecutionItem] = []

    for ticket_id in ids:
        try:
            result = await _execute_one(
                action=action,
                project_name=normalized_project,
                ticket_id=ticket_id,
                actor=normalized_actor,
                reason=reason,
            )
        except (KeyError, ValueError, RuntimeError) as exc:
            items.append(
                H3RepairBatchExecutionItem(
                    ticket_id=ticket_id,
                    action=action,
                    success=False,
                    result=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
        else:
            items.append(
                H3RepairBatchExecutionItem(
                    ticket_id=ticket_id,
                    action=action,
                    success=True,
                    result=result,
                    error_type=None,
                    error_message=None,
                )
            )

    return H3RepairBatchExecutionResult(
        project_name=normalized_project,
        action=action,
        items=tuple(items),
    )
