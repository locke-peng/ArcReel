"""Explicit Phase 5 approval boundary for persisted H3 provider repair tickets.

This service does not choose repair actions and does not submit provider work. It binds a
human approval to the immutable Phase 4 Repair Ticket plus the current execution facts,
then persists that approval before Slice 3 is allowed to enqueue anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.base import utc_now
from lib.db.repositories.h3_repair_ticket_repo import H3RepairTicketRepository
from lib.reference_video.h3_repair_ticket import (
    H3ProviderRepairApproval,
    H3RepairScopeKind,
    validate_provider_repair_approval,
)
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
    PersistedH3RepairTicket,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class H3RepairApprovalStaleError(RuntimeError):
    """The current execution facts no longer match the immutable ticket approval scope."""


class H3RepairApprovalConflictError(RuntimeError):
    """An already-approved ticket received a materially different approval request."""


@dataclass(frozen=True)
class H3RepairApprovalFacts:
    """Current execution facts that must still match the immutable Repair Ticket."""

    source_media_sha256: str
    shot_id: str
    repair_action: str
    provider_prompt_sha256: str | None
    reference_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_sha(self.source_media_sha256, "source_media_sha256")
        _validate_sha(self.provider_prompt_sha256, "provider_prompt_sha256")
        for index, value in enumerate(self.reference_sha256):
            _validate_sha(value, f"reference_sha256[{index}]")
        if not self.shot_id.strip():
            raise ValueError("shot_id is required")
        if not self.repair_action.strip():
            raise ValueError("repair_action is required")


@dataclass(frozen=True)
class H3ProviderRepairApprovalBinding:
    """Persisted approval snapshot, explicitly binding every Phase 5 approval fact."""

    ticket_id: str
    ticket_sha256: str
    source_media_sha256: str
    shot_id: str
    repair_action: str
    provider_prompt_sha256: str | None
    reference_sha256: tuple[str, ...]
    approved_by: str
    approved_at: str
    max_provider_calls: int = 1

    def __post_init__(self) -> None:
        _validate_sha(self.ticket_sha256, "ticket_sha256")
        _validate_sha(self.source_media_sha256, "source_media_sha256")
        _validate_sha(self.provider_prompt_sha256, "provider_prompt_sha256")
        for index, value in enumerate(self.reference_sha256):
            _validate_sha(value, f"reference_sha256[{index}]")
        if not self.ticket_id.startswith("h3rt_"):
            raise ValueError("ticket_id must start with h3rt_")
        if not self.shot_id.strip():
            raise ValueError("shot_id is required")
        if not self.repair_action.strip():
            raise ValueError("repair_action is required")
        if not self.approved_by.strip():
            raise ValueError("approved_by is required")
        if not self.approved_at.strip():
            raise ValueError("approved_at is required")
        if self.max_provider_calls != 1:
            raise ValueError("Phase 5 provider repair approval allows exactly one provider call")

    def to_phase4_approval(self) -> H3ProviderRepairApproval:
        return H3ProviderRepairApproval(
            ticket_id=self.ticket_id,
            ticket_sha256=self.ticket_sha256,
            source_media_sha256=self.source_media_sha256,
            shot_id=self.shot_id,
            approved_by=self.approved_by,
            approved_at=self.approved_at,
            max_provider_calls=self.max_provider_calls,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ticket_id": self.ticket_id,
            "ticket_sha256": self.ticket_sha256,
            "source_media_sha256": self.source_media_sha256,
            "shot_id": self.shot_id,
            "repair_action": self.repair_action,
            "provider_prompt_sha256": self.provider_prompt_sha256,
            "reference_sha256": list(self.reference_sha256),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "max_provider_calls": self.max_provider_calls,
        }

    @classmethod
    def from_json(cls, payload: str) -> H3ProviderRepairApprovalBinding:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise RuntimeError("persisted H3 approval snapshot must be an object")
        return cls(
            ticket_id=str(data["ticket_id"]),
            ticket_sha256=str(data["ticket_sha256"]),
            source_media_sha256=str(data["source_media_sha256"]),
            shot_id=str(data["shot_id"]),
            repair_action=str(data["repair_action"]),
            provider_prompt_sha256=(
                str(data["provider_prompt_sha256"]) if data.get("provider_prompt_sha256") is not None else None
            ),
            reference_sha256=tuple(str(value) for value in data.get("reference_sha256", [])),
            approved_by=str(data["approved_by"]),
            approved_at=str(data["approved_at"]),
            max_provider_calls=int(data["max_provider_calls"]),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class H3RepairApprovalResult:
    ticket: PersistedH3RepairTicket
    approval: H3ProviderRepairApprovalBinding


def _validate_sha(value: str | None, field_name: str) -> None:
    if value is not None and not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _facts_from_ticket(ticket: PersistedH3RepairTicket) -> H3RepairApprovalFacts:
    if ticket.ticket.shot_id is None:
        raise RuntimeError("provider repair approval requires a shot-scoped Repair Ticket")
    return H3RepairApprovalFacts(
        source_media_sha256=ticket.ticket.source_media_sha256,
        shot_id=ticket.ticket.shot_id,
        repair_action=ticket.ticket.repair_action,
        provider_prompt_sha256=ticket.ticket.provider_prompt_sha256,
        reference_sha256=ticket.ticket.reference_sha256,
    )


def _stale_fields(ticket: PersistedH3RepairTicket, current: H3RepairApprovalFacts) -> tuple[str, ...]:
    expected = _facts_from_ticket(ticket)
    fields: list[str] = []
    if current.source_media_sha256 != expected.source_media_sha256:
        fields.append("source_media_sha256")
    if current.shot_id != expected.shot_id:
        fields.append("shot_id")
    if current.repair_action != expected.repair_action:
        fields.append("repair_action")
    if current.provider_prompt_sha256 != expected.provider_prompt_sha256:
        fields.append("provider_prompt_sha256")
    if current.reference_sha256 != expected.reference_sha256:
        fields.append("reference_sha256")
    return tuple(fields)


def _validate_binding_matches_ticket(
    ticket: PersistedH3RepairTicket,
    binding: H3ProviderRepairApprovalBinding,
) -> None:
    """Verify the persisted approval snapshot still binds to the immutable ticket."""

    validate_provider_repair_approval(ticket.ticket, binding.to_phase4_approval())
    expected = _facts_from_ticket(ticket)
    if binding.repair_action != expected.repair_action:
        raise RuntimeError("persisted approval repair action does not match immutable Repair Ticket")
    if binding.provider_prompt_sha256 != expected.provider_prompt_sha256:
        raise RuntimeError("persisted approval Prompt SHA does not match immutable Repair Ticket")
    if binding.reference_sha256 != expected.reference_sha256:
        raise RuntimeError("persisted approval Reference SHA values do not match immutable Repair Ticket")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class H3RepairApprovalService:
    """Atomic approve/reject/cancel/revalidate operations for persisted tickets."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = H3RepairTicketRepository(session)
        self.store = H3RepairTicketStore(session)

    async def _load_required(self, *, project_name: str, ticket_id: str) -> PersistedH3RepairTicket:
        ticket = await self.store.load(project_name=project_name, ticket_id=ticket_id)
        if ticket is None:
            raise KeyError(f"H3 Repair Ticket not found: {project_name}/{ticket_id}")
        return ticket

    async def _expire_stale(
        self,
        *,
        ticket: PersistedH3RepairTicket,
        actor: str,
        stale_fields: tuple[str, ...],
        at: datetime,
    ) -> None:
        reason = "stale approval binding: " + ",".join(stale_fields)
        await self.store.transition(
            project_name=ticket.project_name,
            ticket_id=ticket.ticket.ticket_id,
            target=H3RepairTicketLifecycleState.EXPIRED,
            reason=reason,
        )
        record = await self.repository.get(project_name=ticket.project_name, ticket_id=ticket.ticket.ticket_id)
        if record is None:
            raise RuntimeError("repair ticket disappeared during stale-approval invalidation")
        record.lifecycle_actor = actor
        record.lifecycle_at = at
        record.approval_json = None
        record.approval_identity = None
        record.approval_at = None
        record.max_provider_calls = None
        await self.session.commit()

    async def approve(
        self,
        *,
        project_name: str,
        ticket_id: str,
        approved_by: str,
        current_facts: H3RepairApprovalFacts,
        max_provider_calls: int = 1,
        approved_at: datetime | None = None,
    ) -> H3RepairApprovalResult:
        approved_by = approved_by.strip()
        if not approved_by:
            raise ValueError("approved_by is required")
        if max_provider_calls != 1:
            raise ValueError("Phase 5 provider repair approval allows exactly one provider call")

        now = approved_at or utc_now()
        _validate_aware_datetime(now, "approved_at")
        persisted = await self._load_required(project_name=project_name, ticket_id=ticket_id)
        stale = _stale_fields(persisted, current_facts)
        if stale:
            if persisted.lifecycle_state not in {
                H3RepairTicketLifecycleState.AWAITING_APPROVAL,
                H3RepairTicketLifecycleState.APPROVED,
                H3RepairTicketLifecycleState.QUEUED,
            }:
                raise RuntimeError(
                    f"cannot invalidate stale approval from lifecycle state {persisted.lifecycle_state.value}"
                )
            await self._expire_stale(ticket=persisted, actor=approved_by, stale_fields=stale, at=now)
            raise H3RepairApprovalStaleError("repair approval blocked because current facts changed: " + ",".join(stale))

        if not persisted.ticket.approval_eligible:
            raise RuntimeError("repair ticket is not eligible for provider approval")
        if persisted.ticket.scope_kind is not H3RepairScopeKind.SHOT or persisted.ticket.shot_id is None:
            raise RuntimeError("provider repair approval requires a shot-scoped Repair Ticket")

        if persisted.lifecycle_state is H3RepairTicketLifecycleState.APPROVED:
            if persisted.approval_json is None:
                raise RuntimeError("approved repair ticket is missing its persisted approval snapshot")
            existing = H3ProviderRepairApprovalBinding.from_json(persisted.approval_json)
            _validate_binding_matches_ticket(persisted, existing)
            if existing.approved_by != approved_by or existing.max_provider_calls != max_provider_calls:
                raise H3RepairApprovalConflictError("repair ticket is already approved by a different approval identity")
            return H3RepairApprovalResult(ticket=persisted, approval=existing)

        if persisted.lifecycle_state is not H3RepairTicketLifecycleState.AWAITING_APPROVAL:
            raise RuntimeError(f"repair ticket is not approval-pending: {persisted.lifecycle_state.value}")

        binding = H3ProviderRepairApprovalBinding(
            ticket_id=persisted.ticket.ticket_id,
            ticket_sha256=persisted.ticket.ticket_sha256,
            source_media_sha256=current_facts.source_media_sha256,
            shot_id=current_facts.shot_id,
            repair_action=current_facts.repair_action,
            provider_prompt_sha256=current_facts.provider_prompt_sha256,
            reference_sha256=current_facts.reference_sha256,
            approved_by=approved_by,
            approved_at=now.isoformat(),
            max_provider_calls=max_provider_calls,
        )
        _validate_binding_matches_ticket(persisted, binding)

        await self.store.transition(
            project_name=project_name,
            ticket_id=ticket_id,
            target=H3RepairTicketLifecycleState.APPROVED,
            reason="explicit provider repair approval",
        )
        record = await self.repository.get(project_name=project_name, ticket_id=ticket_id)
        if record is None:
            raise RuntimeError("repair ticket disappeared during approval")
        record.approval_json = binding.to_json()
        record.approval_identity = binding.approved_by
        record.approval_at = now
        record.max_provider_calls = binding.max_provider_calls
        record.lifecycle_actor = binding.approved_by
        record.lifecycle_at = now
        await self.session.commit()

        approved_ticket = await self._load_required(project_name=project_name, ticket_id=ticket_id)
        return H3RepairApprovalResult(ticket=approved_ticket, approval=binding)

    async def validate_for_execution(
        self,
        *,
        project_name: str,
        ticket_id: str,
        current_facts: H3RepairApprovalFacts,
        validation_actor: str = "system:approval-revalidation",
        validated_at: datetime | None = None,
    ) -> H3RepairApprovalResult:
        """Revalidate a persisted approval before Slice 3/4 is allowed to spend."""

        persisted = await self._load_required(project_name=project_name, ticket_id=ticket_id)
        if persisted.lifecycle_state not in {
            H3RepairTicketLifecycleState.APPROVED,
            H3RepairTicketLifecycleState.QUEUED,
        }:
            raise RuntimeError(f"repair ticket is not execution-eligible: {persisted.lifecycle_state.value}")
        if persisted.approval_json is None:
            raise RuntimeError("repair ticket has no persisted approval snapshot")

        binding = H3ProviderRepairApprovalBinding.from_json(persisted.approval_json)
        _validate_binding_matches_ticket(persisted, binding)
        stale = _stale_fields(persisted, current_facts)
        if stale:
            validation_actor = validation_actor.strip()
            if not validation_actor:
                raise ValueError("validation_actor is required")
            now = validated_at or utc_now()
            _validate_aware_datetime(now, "validated_at")
            await self._expire_stale(
                ticket=persisted,
                actor=validation_actor,
                stale_fields=stale,
                at=now,
            )
            raise H3RepairApprovalStaleError(
                "persisted repair approval became stale before execution: " + ",".join(stale)
            )

        if binding.repair_action != current_facts.repair_action:
            raise RuntimeError("persisted approval repair action does not match current facts")
        if binding.provider_prompt_sha256 != current_facts.provider_prompt_sha256:
            raise RuntimeError("persisted approval Prompt SHA does not match current facts")
        if binding.reference_sha256 != current_facts.reference_sha256:
            raise RuntimeError("persisted approval Reference SHA values do not match current facts")
        return H3RepairApprovalResult(ticket=persisted, approval=binding)

    async def reject(
        self,
        *,
        project_name: str,
        ticket_id: str,
        rejected_by: str,
        reason: str | None = None,
        rejected_at: datetime | None = None,
    ) -> PersistedH3RepairTicket:
        return await self._terminal_decision(
            project_name=project_name,
            ticket_id=ticket_id,
            actor=rejected_by,
            target=H3RepairTicketLifecycleState.REJECTED,
            reason=reason or "provider repair rejected",
            at=rejected_at,
        )

    async def cancel(
        self,
        *,
        project_name: str,
        ticket_id: str,
        cancelled_by: str,
        reason: str | None = None,
        cancelled_at: datetime | None = None,
    ) -> PersistedH3RepairTicket:
        return await self._terminal_decision(
            project_name=project_name,
            ticket_id=ticket_id,
            actor=cancelled_by,
            target=H3RepairTicketLifecycleState.CANCELLED,
            reason=reason or "provider repair cancelled",
            at=cancelled_at,
        )

    async def _terminal_decision(
        self,
        *,
        project_name: str,
        ticket_id: str,
        actor: str,
        target: H3RepairTicketLifecycleState,
        reason: str,
        at: datetime | None,
    ) -> PersistedH3RepairTicket:
        actor = actor.strip()
        if not actor:
            raise ValueError("decision actor is required")
        persisted = await self._load_required(project_name=project_name, ticket_id=ticket_id)
        if persisted.lifecycle_state is target:
            return persisted

        now = at or utc_now()
        _validate_aware_datetime(now, "decision timestamp")
        await self.store.transition(
            project_name=project_name,
            ticket_id=ticket_id,
            target=target,
            reason=reason,
        )
        record = await self.repository.get(project_name=project_name, ticket_id=ticket_id)
        if record is None:
            raise RuntimeError("repair ticket disappeared during lifecycle decision")
        record.lifecycle_actor = actor
        record.lifecycle_at = now
        await self.session.commit()
        return await self._load_required(project_name=project_name, ticket_id=ticket_id)
