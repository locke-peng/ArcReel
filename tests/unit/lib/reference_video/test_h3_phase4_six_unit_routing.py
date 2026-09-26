from __future__ import annotations

from pathlib import Path

import pytest

from lib.reference_video.h3_auto_repair_loop import (
    execute_h3_auto_repair,
    plan_h3_auto_repair,
)
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
)


def _finding(
    unit_id: str,
    *,
    tags: tuple[str, ...],
    provider_result_usable: bool,
    audio_is_accepted: bool,
    repairability: MediaQARepairability,
    affected_fraction: float = 1.0,
    exact_visible_text: str | None = None,
) -> MediaQAFinding:
    return MediaQAFinding(
        unit_id=unit_id,
        canonical_violation=f"{unit_id} representative Phase 4 routing fixture",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=provider_result_usable,
        audio_is_accepted=audio_is_accepted,
        repairability=repairability,
        affected_fraction=affected_fraction,
        exact_visible_text=exact_visible_text,
        tags=tags,
    )


@pytest.mark.parametrize(
    (
        "finding",
        "failure_class",
        "repair_action",
        "provider_recall_required",
    ),
    [
        (
            _finding(
                "E12U06",
                tags=("invented_content", "topology_failure"),
                provider_result_usable=False,
                audio_is_accepted=False,
                repairability=MediaQARepairability.PROVIDER,
            ),
            H3FailureClass.LARGE_SEMANTIC_FAILURE,
            H3RepairAction.REGENERATE_SHOT,
            True,
        ),
        (
            _finding(
                "E4U02",
                tags=("dialogue_leakage",),
                provider_result_usable=False,
                audio_is_accepted=False,
                repairability=MediaQARepairability.PROVIDER,
            ),
            H3FailureClass.DIALOGUE_VISUALIZATION,
            H3RepairAction.RECOMPILE_DIALOGUE_DETACHED,
            True,
        ),
        (
            _finding(
                "E4U02",
                tags=("identity_drift",),
                provider_result_usable=False,
                audio_is_accepted=False,
                repairability=MediaQARepairability.PROVIDER,
            ),
            H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
            H3RepairAction.REGENERATE_WITH_IDENTITY_BRIDGE,
            True,
        ),
        (
            _finding(
                "E13U01",
                tags=("exact_text_mismatch",),
                provider_result_usable=True,
                audio_is_accepted=True,
                repairability=MediaQARepairability.DETERMINISTIC,
                exact_visible_text="沈知意\n天枢联合创始人",
            ),
            H3FailureClass.EXACT_TEXT_REQUIRED,
            H3RepairAction.DETERMINISTIC_TEXT_PLATE,
            False,
        ),
        (
            _finding(
                "E13U03",
                tags=("noncanonical_text", "semantic_only_log_state"),
                provider_result_usable=True,
                audio_is_accepted=True,
                repairability=MediaQARepairability.DETERMINISTIC,
                affected_fraction=0.10,
            ),
            H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
            H3RepairAction.DETERMINISTIC_SURFACE_REPAIR,
            False,
        ),
        (
            _finding(
                "E11U02",
                tags=("noncanonical_text", "surface_pollution"),
                provider_result_usable=True,
                audio_is_accepted=True,
                repairability=MediaQARepairability.DETERMINISTIC,
                affected_fraction=0.05,
            ),
            H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
            H3RepairAction.DETERMINISTIC_SURFACE_REPAIR,
            False,
        ),
        (
            _finding(
                "E15U03",
                tags=("cut_timing",),
                provider_result_usable=True,
                audio_is_accepted=True,
                repairability=MediaQARepairability.DETERMINISTIC,
            ),
            H3FailureClass.TIMELINE_ONLY_FAILURE,
            H3RepairAction.DETERMINISTIC_AV_RETIME,
            False,
        ),
    ],
)
def test_six_representative_units_route_through_existing_phase3_policy(
    finding: MediaQAFinding,
    failure_class: H3FailureClass,
    repair_action: H3RepairAction,
    provider_recall_required: bool,
) -> None:
    plan = plan_h3_auto_repair(finding)

    assert plan.failure.failure_class is failure_class
    assert plan.decision.action is repair_action
    assert plan.provider_recall_required is provider_recall_required


@pytest.mark.parametrize(
    "finding",
    [
        _finding(
            "E12U06",
            tags=("invented_content",),
            provider_result_usable=False,
            audio_is_accepted=False,
            repairability=MediaQARepairability.PROVIDER,
        ),
        _finding(
            "E4U02",
            tags=("dialogue_leakage",),
            provider_result_usable=False,
            audio_is_accepted=False,
            repairability=MediaQARepairability.PROVIDER,
        ),
        _finding(
            "E4U02",
            tags=("identity_drift",),
            provider_result_usable=False,
            audio_is_accepted=False,
            repairability=MediaQARepairability.PROVIDER,
        ),
    ],
)
def test_provider_required_routes_fail_closed_by_default(
    finding: MediaQAFinding,
    tmp_path: Path,
) -> None:
    source = tmp_path / "accepted-or-failed-provider-source.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "output.mp4"

    plan = plan_h3_auto_repair(finding)
    assert plan.provider_recall_required is True

    with pytest.raises(RuntimeError, match="provider execution is disabled"):
        execute_h3_auto_repair(
            plan,
            source_media=(source,),
            output_media=output,
        )


def test_e13u03_unknown_semantic_state_does_not_create_a_second_policy() -> None:
    finding = _finding(
        "E13U03",
        tags=("semantic_only_log_state",),
        provider_result_usable=True,
        audio_is_accepted=True,
        repairability=MediaQARepairability.HUMAN_REVIEW,
        affected_fraction=0.10,
    )
    plan = plan_h3_auto_repair(finding)

    assert plan.failure.failure_class is H3FailureClass.UNKNOWN
    assert plan.decision.action is H3RepairAction.ESCALATE
    assert plan.provider_recall_required is False
