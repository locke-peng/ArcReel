"""Phase 6 deterministic production-state projection for H3 reference-video projects.

This module is a read model only. It derives project/episode/Unit state from authoritative
project/script inventory, current VersionManager selections, and persisted Phase 5 Repair
Tickets. It owns no repair policy and persists no shadow lifecycle state.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping, Sequence

from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    PersistedH3RepairTicket,
)


class H3ProductionUnitState(StrEnum):
    NOT_STARTED = "not_started"
    READY = "ready"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    ACCEPTED = "accepted"
    FAILED_HISTORY_ONLY = "failed_history_only"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class H3ProductionUnitInventory:
    episode: int
    unit_id: str
    current_version: int


@dataclass(frozen=True, slots=True)
class H3ProductionUnitProjection:
    episode: int
    unit_id: str
    state: H3ProductionUnitState
    current_version: int
    ticket_ids: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    active_execution_count: int
    provider_call_count: int


@dataclass(frozen=True, slots=True)
class H3ProductionEpisodeProjection:
    episode: int
    state_counts: Mapping[str, int]
    units: tuple[H3ProductionUnitProjection, ...]


@dataclass(frozen=True, slots=True)
class H3ProductionProjectProjection:
    project_name: str
    state_counts: Mapping[str, int]
    episodes: tuple[H3ProductionEpisodeProjection, ...]


_ACTIVE_RUNNING = frozenset(
    {
        H3RepairTicketLifecycleState.RUNNING,
        H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
        H3RepairTicketLifecycleState.REASSEMBLING,
        H3RepairTicketLifecycleState.REQA_RUNNING,
    }
)
_BLOCKED_TERMINAL = frozenset(
    {
        H3RepairTicketLifecycleState.EXPIRED,
        H3RepairTicketLifecycleState.CANCELLED,
    }
)


def _derive_unit_state(
    *,
    current_version: int,
    tickets: Sequence[PersistedH3RepairTicket],
) -> tuple[H3ProductionUnitState, tuple[str, ...]]:
    states = {ticket.lifecycle_state for ticket in tickets}

    if H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED in states:
        return H3ProductionUnitState.HUMAN_REVIEW_REQUIRED, ("human_review_required",)

    if states & _ACTIVE_RUNNING:
        return H3ProductionUnitState.RUNNING, ()

    if H3RepairTicketLifecycleState.QUEUED in states:
        return H3ProductionUnitState.QUEUED, ()

    if H3RepairTicketLifecycleState.APPROVED in states:
        return H3ProductionUnitState.READY, ()

    if H3RepairTicketLifecycleState.AWAITING_APPROVAL in states:
        return H3ProductionUnitState.AWAITING_APPROVAL, ("approval_required",)

    if H3RepairTicketLifecycleState.REJECTED in states:
        return H3ProductionUnitState.FAILED_HISTORY_ONLY, ("repair_rejected",)

    if states & _BLOCKED_TERMINAL:
        return H3ProductionUnitState.BLOCKED, tuple(sorted(state.value for state in states & _BLOCKED_TERMINAL))

    if H3RepairTicketLifecycleState.ACCEPTED in states:
        return H3ProductionUnitState.ACCEPTED, ()

    if current_version > 0:
        return H3ProductionUnitState.COMPLETE, ()

    return H3ProductionUnitState.NOT_STARTED, ("no_current_reference_video",)


def build_h3_production_projection(
    *,
    project_name: str,
    inventory: Iterable[H3ProductionUnitInventory],
    tickets: Iterable[PersistedH3RepairTicket],
) -> H3ProductionProjectProjection:
    """Build one deterministic project projection without mutating authoritative state."""

    normalized_project = project_name.strip()
    if not normalized_project:
        raise ValueError("project_name is required")

    ticket_by_unit: dict[str, list[PersistedH3RepairTicket]] = {}
    for ticket in tickets:
        if ticket.project_name != normalized_project:
            raise ValueError("projection received a Repair Ticket from another project")
        ticket_by_unit.setdefault(ticket.ticket.unit_id, []).append(ticket)

    seen_units: set[str] = set()
    episode_units: dict[int, list[H3ProductionUnitProjection]] = {}
    for item in sorted(inventory, key=lambda value: (value.episode, value.unit_id)):
        if item.episode <= 0:
            raise ValueError("episode must be positive")
        if not item.unit_id.strip():
            raise ValueError("unit_id is required")
        if item.current_version < 0:
            raise ValueError("current_version cannot be negative")
        if item.unit_id in seen_units:
            raise ValueError(f"duplicate Unit inventory entry: {item.unit_id}")
        seen_units.add(item.unit_id)

        unit_tickets = tuple(
            sorted(
                ticket_by_unit.pop(item.unit_id, []),
                key=lambda ticket: (ticket.created_at, ticket.ticket.ticket_id),
            )
        )
        state, blockers = _derive_unit_state(current_version=item.current_version, tickets=unit_tickets)
        projected = H3ProductionUnitProjection(
            episode=item.episode,
            unit_id=item.unit_id,
            state=state,
            current_version=item.current_version,
            ticket_ids=tuple(ticket.ticket.ticket_id for ticket in unit_tickets),
            blocker_codes=blockers,
            active_execution_count=sum(ticket.lifecycle_state in _ACTIVE_RUNNING for ticket in unit_tickets),
            provider_call_count=sum(ticket.provider_call_count for ticket in unit_tickets),
        )
        episode_units.setdefault(item.episode, []).append(projected)

    if ticket_by_unit:
        unknown = ", ".join(sorted(ticket_by_unit))
        raise RuntimeError(f"Repair Ticket references Unit missing from project inventory: {unknown}")

    episodes: list[H3ProductionEpisodeProjection] = []
    project_counts: Counter[str] = Counter()
    for episode, units in sorted(episode_units.items()):
        counts = Counter(unit.state.value for unit in units)
        project_counts.update(counts)
        episodes.append(
            H3ProductionEpisodeProjection(
                episode=episode,
                state_counts=dict(sorted(counts.items())),
                units=tuple(units),
            )
        )

    return H3ProductionProjectProjection(
        project_name=normalized_project,
        state_counts=dict(sorted(project_counts.items())),
        episodes=tuple(episodes),
    )
