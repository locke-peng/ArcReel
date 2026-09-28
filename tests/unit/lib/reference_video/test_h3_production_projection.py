from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from lib.reference_video.h3_production_projection import (
    H3ProductionUnitInventory,
    H3ProductionUnitState,
    build_h3_production_projection,
)
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState


def _ticket(
    *,
    project: str,
    unit_id: str,
    ticket_id: str,
    state: H3RepairTicketLifecycleState,
    provider_calls: int = 0,
):
    return SimpleNamespace(
        project_name=project,
        ticket=SimpleNamespace(unit_id=unit_id, ticket_id=ticket_id),
        lifecycle_state=state,
        created_at=datetime(2026, 9, 28, 1, 0, tzinfo=UTC),
        provider_call_count=provider_calls,
    )


def test_projection_derives_unit_and_episode_states_from_authoritative_inputs() -> None:
    projection = build_h3_production_projection(
        project_name="demo",
        inventory=(
            H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=0),
            H3ProductionUnitInventory(episode=1, unit_id="E1U02", current_version=1),
            H3ProductionUnitInventory(episode=2, unit_id="E2U01", current_version=2),
            H3ProductionUnitInventory(episode=2, unit_id="E2U02", current_version=3),
        ),
        tickets=(
            _ticket(
                project="demo",
                unit_id="E1U02",
                ticket_id="h3rt_approval",
                state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            ),
            _ticket(
                project="demo",
                unit_id="E2U01",
                ticket_id="h3rt_running",
                state=H3RepairTicketLifecycleState.REQA_RUNNING,
                provider_calls=1,
            ),
            _ticket(
                project="demo",
                unit_id="E2U02",
                ticket_id="h3rt_accepted",
                state=H3RepairTicketLifecycleState.ACCEPTED,
                provider_calls=1,
            ),
        ),
    )

    by_unit = {
        unit.unit_id: unit
        for episode in projection.episodes
        for unit in episode.units
    }
    assert by_unit["E1U01"].state is H3ProductionUnitState.NOT_STARTED
    assert by_unit["E1U01"].blocker_codes == ("no_current_reference_video",)
    assert by_unit["E1U02"].state is H3ProductionUnitState.AWAITING_APPROVAL
    assert by_unit["E1U02"].blocker_codes == ("approval_required",)
    assert by_unit["E2U01"].state is H3ProductionUnitState.RUNNING
    assert by_unit["E2U01"].active_execution_count == 1
    assert by_unit["E2U01"].provider_call_count == 1
    assert by_unit["E2U02"].state is H3ProductionUnitState.ACCEPTED

    assert projection.state_counts == {
        "accepted": 1,
        "awaiting_approval": 1,
        "not_started": 1,
        "running": 1,
    }


def test_human_review_has_fail_closed_priority_over_other_ticket_states() -> None:
    projection = build_h3_production_projection(
        project_name="demo",
        inventory=(H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=2),),
        tickets=(
            _ticket(
                project="demo",
                unit_id="E1U01",
                ticket_id="h3rt_running",
                state=H3RepairTicketLifecycleState.RUNNING,
            ),
            _ticket(
                project="demo",
                unit_id="E1U01",
                ticket_id="h3rt_human",
                state=H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            ),
        ),
    )

    unit = projection.episodes[0].units[0]
    assert unit.state is H3ProductionUnitState.HUMAN_REVIEW_REQUIRED
    assert unit.blocker_codes == ("human_review_required",)


def test_projection_rejects_cross_project_or_orphan_ticket_input() -> None:
    inventory = (H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=1),)

    with pytest.raises(ValueError, match="another project"):
        build_h3_production_projection(
            project_name="demo",
            inventory=inventory,
            tickets=(
                _ticket(
                    project="other",
                    unit_id="E1U01",
                    ticket_id="h3rt_other",
                    state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
                ),
            ),
        )

    with pytest.raises(RuntimeError, match="missing from project inventory"):
        build_h3_production_projection(
            project_name="demo",
            inventory=inventory,
            tickets=(
                _ticket(
                    project="demo",
                    unit_id="E9U09",
                    ticket_id="h3rt_orphan",
                    state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
                ),
            ),
        )


def test_projection_is_deterministic_and_rejects_duplicate_inventory() -> None:
    inventory = (
        H3ProductionUnitInventory(episode=2, unit_id="E2U02", current_version=1),
        H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=1),
    )
    one = build_h3_production_projection(project_name="demo", inventory=inventory, tickets=())
    two = build_h3_production_projection(project_name="demo", inventory=reversed(inventory), tickets=())

    assert one == two
    assert [episode.episode for episode in one.episodes] == [1, 2]
    assert all(episode.units[0].state is H3ProductionUnitState.COMPLETE for episode in one.episodes)

    with pytest.raises(ValueError, match="duplicate Unit inventory"):
        build_h3_production_projection(
            project_name="demo",
            inventory=(
                H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=1),
                H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=1),
            ),
            tickets=(),
        )


@pytest.mark.parametrize(
    ("lifecycle", "expected_state", "expected_blockers"),
    [
        (
            H3RepairTicketLifecycleState.AWAITING_APPROVAL,
            H3ProductionUnitState.AWAITING_APPROVAL,
            ("approval_required",),
        ),
        (
            H3RepairTicketLifecycleState.APPROVED,
            H3ProductionUnitState.READY,
            (),
        ),
        (
            H3RepairTicketLifecycleState.QUEUED,
            H3ProductionUnitState.QUEUED,
            (),
        ),
        (
            H3RepairTicketLifecycleState.RUNNING,
            H3ProductionUnitState.RUNNING,
            (),
        ),
        (
            H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            H3ProductionUnitState.RUNNING,
            (),
        ),
        (
            H3RepairTicketLifecycleState.REASSEMBLING,
            H3ProductionUnitState.RUNNING,
            (),
        ),
        (
            H3RepairTicketLifecycleState.REQA_RUNNING,
            H3ProductionUnitState.RUNNING,
            (),
        ),
        (
            H3RepairTicketLifecycleState.ACCEPTED,
            H3ProductionUnitState.ACCEPTED,
            (),
        ),
        (
            H3RepairTicketLifecycleState.REJECTED,
            H3ProductionUnitState.FAILED_HISTORY_ONLY,
            ("repair_rejected",),
        ),
        (
            H3RepairTicketLifecycleState.CANCELLED,
            H3ProductionUnitState.BLOCKED,
            ("cancelled",),
        ),
        (
            H3RepairTicketLifecycleState.EXPIRED,
            H3ProductionUnitState.BLOCKED,
            ("expired",),
        ),
        (
            H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED,
            H3ProductionUnitState.HUMAN_REVIEW_REQUIRED,
            ("human_review_required",),
        ),
    ],
)
def test_projection_maps_every_phase5_lifecycle_to_readiness(
    lifecycle: H3RepairTicketLifecycleState,
    expected_state: H3ProductionUnitState,
    expected_blockers: tuple[str, ...],
) -> None:
    projection = build_h3_production_projection(
        project_name="demo",
        inventory=(H3ProductionUnitInventory(episode=1, unit_id="E1U01", current_version=1),),
        tickets=(
            _ticket(
                project="demo",
                unit_id="E1U01",
                ticket_id=f"h3rt_{lifecycle.value}",
                state=lifecycle,
            ),
        ),
    )

    unit = projection.episodes[0].units[0]
    assert unit.state is expected_state
    assert unit.blocker_codes == expected_blockers
