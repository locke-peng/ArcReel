"""Phase 6 Slice 4 H3 repair budget and actual-cost ledger.

The ledger is a read model over Phase 5 Repair Tickets, project call allowance, shared task
identity, and authoritative api_calls settlements. It never invents provider cost.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from lib.reference_video.h3_repair_ticket_store import PersistedH3RepairTicket


@dataclass(frozen=True, slots=True)
class H3RepairActualCall:
    call_id: int
    task_id: str
    provider: str
    model: str
    status: str
    cost_amount: float
    currency: str


@dataclass(frozen=True, slots=True)
class H3RepairTicketLedger:
    ticket_id: str
    unit_id: str
    shot_id: str | None
    execution_task_id: str | None
    max_provider_calls: int | None
    reserved_provider_calls: int
    actual_calls: tuple[H3RepairActualCall, ...]
    actual_cost_by_currency: Mapping[str, float]
    pricing_state: str


@dataclass(frozen=True, slots=True)
class H3RepairProjectLedger:
    project_name: str
    provider_call_ceiling: int | None
    reserved_provider_calls: int
    remaining_provider_calls: int | None
    budget_counter_reconciled: bool | None
    tickets: tuple[H3RepairTicketLedger, ...]
    actual_cost_by_currency: Mapping[str, float]
    unpriced_call_count: int


def _sum_cost(calls: Iterable[H3RepairActualCall]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for call in calls:
        if call.status == "pending":
            continue
        totals[call.currency] = totals.get(call.currency, 0.0) + float(call.cost_amount)
    return dict(sorted(totals.items()))


def build_h3_repair_project_ledger(
    *,
    project_name: str,
    tickets: Sequence[PersistedH3RepairTicket],
    calls_by_task_id: Mapping[str, Sequence[H3RepairActualCall]],
    provider_call_ceiling: int | None,
    project_budget_provider_call_count: int | None,
) -> H3RepairProjectLedger:
    normalized = project_name.strip()
    if not normalized:
        raise ValueError("project_name is required")
    if provider_call_ceiling is not None and provider_call_ceiling < 1:
        raise ValueError("provider_call_ceiling must be >= 1 or null")
    if project_budget_provider_call_count is not None and project_budget_provider_call_count < 0:
        raise ValueError("project_budget_provider_call_count cannot be negative")

    ticket_reserved_total = sum(ticket.provider_call_count for ticket in tickets)
    if provider_call_ceiling is not None and ticket_reserved_total > provider_call_ceiling:
        raise RuntimeError("ticket reserved provider calls exceed configured project ceiling")
    if (
        project_budget_provider_call_count is not None
        and project_budget_provider_call_count != ticket_reserved_total
    ):
        raise RuntimeError(
            "project budget provider-call counter does not reconcile with Repair Tickets"
        )

    ticket_ledgers: list[H3RepairTicketLedger] = []
    all_calls: list[H3RepairActualCall] = []
    unpriced_call_count = 0

    for ticket in sorted(tickets, key=lambda item: item.ticket.ticket_id):
        if ticket.project_name != normalized:
            raise ValueError("ledger received Repair Ticket from another project")
        task_id = ticket.execution_task_id
        calls = tuple(calls_by_task_id.get(task_id, ())) if task_id is not None else ()
        all_calls.extend(calls)

        actual_cost = _sum_cost(calls)
        if not calls:
            pricing_state = "no_provider_call"
        elif any(call.status == "pending" for call in calls):
            pricing_state = "pending"
        elif any(call.cost_amount == 0.0 and call.status == "success" for call in calls):
            pricing_state = "unpriced_or_zero"
            unpriced_call_count += sum(
                call.cost_amount == 0.0 and call.status == "success"
                for call in calls
            )
        else:
            pricing_state = "settled"

        ticket_ledgers.append(
            H3RepairTicketLedger(
                ticket_id=ticket.ticket.ticket_id,
                unit_id=ticket.ticket.unit_id,
                shot_id=ticket.ticket.shot_id,
                execution_task_id=task_id,
                max_provider_calls=ticket.max_provider_calls,
                reserved_provider_calls=ticket.provider_call_count,
                actual_calls=calls,
                actual_cost_by_currency=actual_cost,
                pricing_state=pricing_state,
            )
        )

    remaining = (
        None
        if provider_call_ceiling is None
        else provider_call_ceiling - ticket_reserved_total
    )
    return H3RepairProjectLedger(
        project_name=normalized,
        provider_call_ceiling=provider_call_ceiling,
        reserved_provider_calls=ticket_reserved_total,
        remaining_provider_calls=remaining,
        budget_counter_reconciled=(
            None
            if project_budget_provider_call_count is None
            else project_budget_provider_call_count == ticket_reserved_total
        ),
        tickets=tuple(ticket_ledgers),
        actual_cost_by_currency=_sum_cost(all_calls),
        unpriced_call_count=unpriced_call_count,
    )
