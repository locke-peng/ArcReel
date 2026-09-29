"""Phase 6 Slice 4 authoritative H3 repair budget/cost ledger resolver."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from lib.db import safe_session_factory
from lib.db.models.api_call import ApiCall
from lib.db.models.h3_repair_ticket import H3RepairProjectBudget
from lib.reference_video.h3_repair_ledger import (
    H3RepairActualCall,
    H3RepairProjectLedger,
    build_h3_repair_project_ledger,
)
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketStore


async def resolve_h3_repair_project_ledger(
    *,
    project_name: str,
) -> H3RepairProjectLedger:
    normalized = project_name.strip()
    if not normalized:
        raise ValueError("project_name is required")

    async with safe_session_factory() as session:
        tickets = await H3RepairTicketStore(session).list_for_project(
            project_name=normalized,
            limit=500,
        )
        budget = await session.get(H3RepairProjectBudget, normalized)

        task_ids = tuple(
            ticket.execution_task_id
            for ticket in tickets
            if ticket.execution_task_id is not None
        )
        rows: list[ApiCall] = []
        if task_ids:
            result = await session.execute(
                select(ApiCall)
                .where(
                    ApiCall.project_name == normalized,
                    ApiCall.task_id.in_(task_ids),
                )
                .order_by(ApiCall.id)
            )
            rows = list(result.scalars())

    calls_by_task_id: dict[str, list[H3RepairActualCall]] = defaultdict(list)
    for row in rows:
        if row.task_id is None:
            continue
        calls_by_task_id[row.task_id].append(
            H3RepairActualCall(
                call_id=row.id,
                task_id=row.task_id,
                provider=row.provider,
                model=row.model,
                status=row.status,
                cost_amount=float(row.cost_amount or 0.0),
                currency=row.currency,
            )
        )

    return build_h3_repair_project_ledger(
        project_name=normalized,
        tickets=tickets,
        calls_by_task_id=calls_by_task_id,
        provider_call_ceiling=budget.provider_call_ceiling if budget is not None else None,
        project_budget_provider_call_count=(
            budget.provider_call_count if budget is not None else None
        ),
    )
