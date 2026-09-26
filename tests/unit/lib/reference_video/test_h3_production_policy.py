from __future__ import annotations

import pytest

from lib.reference_video.h3_production_policy import (
    H3FailureClass,
    H3MediaFailure,
    H3RepairAction,
    plan_h3_media_repair,
)


@pytest.mark.parametrize(
    ("failure", "action", "provider_recall"),
    [
        (
            H3MediaFailure(
                H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
                affected_fraction=0.05,
                provider_result_usable=True,
                audio_is_accepted=True,
            ),
            H3RepairAction.DETERMINISTIC_SURFACE_REPAIR,
            False,
        ),
        (
            H3MediaFailure(
                H3FailureClass.EXACT_TEXT_REQUIRED,
                provider_result_usable=True,
                audio_is_accepted=True,
                exact_visible_text="TIANSHU NEXT",
            ),
            H3RepairAction.DETERMINISTIC_TEXT_PLATE,
            False,
        ),
        (
            H3MediaFailure(
                H3FailureClass.TIMELINE_ONLY_FAILURE,
                provider_result_usable=True,
            ),
            H3RepairAction.DETERMINISTIC_AV_RETIME,
            False,
        ),
        (
            H3MediaFailure(H3FailureClass.DIALOGUE_VISUALIZATION),
            H3RepairAction.RECOMPILE_DIALOGUE_DETACHED,
            True,
        ),
        (
            H3MediaFailure(H3FailureClass.IDENTITY_CONTINUITY_FAILURE),
            H3RepairAction.REGENERATE_WITH_IDENTITY_BRIDGE,
            True,
        ),
        (
            H3MediaFailure(H3FailureClass.LARGE_SEMANTIC_FAILURE),
            H3RepairAction.REGENERATE_SHOT,
            True,
        ),
    ],
)
def test_phase3_repair_matrix(
    failure: H3MediaFailure,
    action: H3RepairAction,
    provider_recall: bool,
) -> None:
    decision = plan_h3_media_repair(failure)
    assert decision.action == action
    assert decision.provider_recall_required is provider_recall


def test_e11u02_local_text_pollution_preserves_accepted_audio() -> None:
    decision = plan_h3_media_repair(
        H3MediaFailure(
            H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
            affected_fraction=0.05,
            provider_result_usable=True,
            audio_is_accepted=True,
        )
    )
    assert decision.action == H3RepairAction.DETERMINISTIC_SURFACE_REPAIR
    assert decision.preserve_audio_bitstream is True


def test_e15u03_timeline_repair_never_claims_audio_bitstream_preservation() -> None:
    decision = plan_h3_media_repair(
        H3MediaFailure(
            H3FailureClass.TIMELINE_ONLY_FAILURE,
            provider_result_usable=True,
            audio_is_accepted=True,
        )
    )
    assert decision.action == H3RepairAction.DETERMINISTIC_AV_RETIME
    assert decision.preserve_audio_bitstream is False


def test_broad_surface_failure_regenerates_instead_of_hiding_large_regions() -> None:
    decision = plan_h3_media_repair(
        H3MediaFailure(
            H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
            affected_fraction=0.40,
            provider_result_usable=True,
        )
    )
    assert decision.action == H3RepairAction.REGENERATE_SHOT
    assert decision.provider_recall_required is True


def test_unknown_failure_fails_closed_without_provider_recall() -> None:
    decision = plan_h3_media_repair(H3MediaFailure(H3FailureClass.UNKNOWN))
    assert decision.action == H3RepairAction.ESCALATE
    assert decision.provider_recall_required is False


def test_exact_text_requires_literal_canonical_value() -> None:
    with pytest.raises(ValueError, match="exact_visible_text"):
        H3MediaFailure(H3FailureClass.EXACT_TEXT_REQUIRED)
