"""Repository for persisted H3 Repair Ticket lifecycle rows."""

from __future__ import annotations

from sqlalchemy import select

from lib.db.models.h3_repair_ticket import H3RepairTicketRecord
from lib.db.repositories.base import BaseRepository


class H3RepairTicketRepository(BaseRepository):
    """Project-scoped CRUD used by the Phase 5 Repair Ticket store.

    The repository intentionally exposes no generic update method for immutable ticket
    fields. Lifecycle mutation is owned by the domain store/state machine.
    """

    async def add(self, record: H3RepairTicketRecord) -> H3RepairTicketRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, *, project_name: str, ticket_id: str) -> H3RepairTicketRecord | None:
        stmt = select(H3RepairTicketRecord).where(
            H3RepairTicketRecord.project_name == project_name,
            H3RepairTicketRecord.ticket_id == ticket_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        *,
        project_name: str,
        lifecycle_state: str | None = None,
        unit_id: str | None = None,
        limit: int = 100,
    ) -> list[H3RepairTicketRecord]:
        stmt = select(H3RepairTicketRecord).where(H3RepairTicketRecord.project_name == project_name)
        if lifecycle_state is not None:
            stmt = stmt.where(H3RepairTicketRecord.lifecycle_state == lifecycle_state)
        if unit_id is not None:
            stmt = stmt.where(H3RepairTicketRecord.unit_id == unit_id)
        stmt = stmt.order_by(H3RepairTicketRecord.updated_at.desc()).limit(max(1, min(limit, 500)))
        result = await self.session.execute(stmt)
        return list(result.scalars())
