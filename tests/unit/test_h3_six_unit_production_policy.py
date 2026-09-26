import pytest

from lib.reference_video.h3_production_policy import (
    H3ProductionPolicyError,
    MediaIssueCode,
    RepairAction,
    plan_h3_media_repair,
    validate_h3_canonical_unit,
)


def _shot(
    shot_id: str,
    start: float,
    end: float,
    *,
    screen_text: list[dict] | None = None,
    dialogue: list[dict] | None = None,
) -> dict:
    return {
        "shot_id": shot_id,
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "action": "canonical action",
        "screen_text": screen_text or [],
        "dialogue": dialogue or [],
    }


def _unit(unit_id: str, duration: int, shots: list[dict], **extra: object) -> dict:
    return {
        "unit_id": unit_id,
        "duration_sec": duration,
        "shots": shots,
        "active_subject_ids": extra.get("active_subject_ids", []),
        "depicted_subject_ids": extra.get("depicted_subject_ids", []),
        "referenced_entity_ids": extra.get("referenced_entity_ids", []),
    }


def test_e12u06_semantic_ui_carries_no_invented_literal() -> None:
    unit = _unit(
        "E12U06",
        10,
        [
            _shot(
                "E12U06-S01",
                0,
                5,
                screen_text=[
                    {
                        "kind": "status geometry",
                        "legibility": "semantic_only",
                        "semantic": "four static white geometric blocks",
                    }
                ],
            ),
            _shot("E12U06-S02", 5, 10),
        ],
    )
    facts = validate_h3_canonical_unit(unit, provider_duration_seconds=10)
    assert facts.exact_visible_text == ()


def test_e4u02_visible_text_and_dialogue_are_separate_canonical_channels() -> None:
    unit = _unit(
        "E4U02",
        15,
        [
            _shot(
                "E4U02-S01",
                0,
                5,
                screen_text=[
                    {
                        "kind": "phone UI",
                        "legibility": "exact",
                        "text": "给念念打电话",
                    }
                ],
            ),
            _shot(
                "E4U02-S02",
                5,
                10,
                dialogue=[{"speaker_id": "C03", "text": "妈妈，我想你。"}],
            ),
            _shot(
                "E4U02-S03",
                10,
                15,
                dialogue=[{"speaker_id": "C01", "text": "妈妈，我在忙。"}],
            ),
        ],
        active_subject_ids=["C01"],
        referenced_entity_ids=["C03"],
    )
    facts = validate_h3_canonical_unit(unit, provider_duration_seconds=15)
    assert facts.exact_visible_text == ("给念念打电话",)
    assert facts.dialogue_text == ("妈妈，我想你。", "妈妈，我在忙。")


def test_e13u01_exact_text_failure_routes_to_deterministic_plate() -> None:
    assert plan_h3_media_repair(
        [MediaIssueCode.EXACT_TEXT_MISSING_OR_WRONG]
    ) == RepairAction.DETERMINISTIC_TEXT_PLATE


def test_e13u03_semantic_logs_may_not_smuggle_literal_log_lines() -> None:
    unit = _unit(
        "E13U03",
        15,
        [
            _shot(
                "E13U03-S01",
                0,
                5,
                screen_text=[
                    {
                        "kind": "system logs",
                        "legibility": "semantic_only",
                        "semantic": "system logs scroll",
                    }
                ],
            ),
            _shot("E13U03-S02", 5, 10),
            _shot("E13U03-S03", 10, 15),
        ],
    )
    facts = validate_h3_canonical_unit(unit, provider_duration_seconds=15)
    assert facts.exact_visible_text == ()


def test_e11u02_local_text_pollution_routes_to_pixel_sanitization() -> None:
    assert plan_h3_media_repair(
        [
            MediaIssueCode.NONCANONICAL_VISIBLE_TEXT,
            MediaIssueCode.LOCAL_UI_TEXT_CONTAMINATION,
        ]
    ) == RepairAction.DETERMINISTIC_PIXEL_SANITIZATION


def test_e15u03_timeline_drift_routes_to_av_retime() -> None:
    assert plan_h3_media_repair(
        [
            MediaIssueCode.SHOT_TIMELINE_DRIFT,
            MediaIssueCode.AUDIO_TIMELINE_DRIFT,
        ]
    ) == RepairAction.DETERMINISTIC_AV_RETIME


def test_semantic_failure_routes_to_shot_regeneration() -> None:
    assert plan_h3_media_repair(
        [MediaIssueCode.IDENTITY_DRIFT]
    ) == RepairAction.REGENERATE_SHOT


def test_pre_provider_validator_rejects_timeline_gap() -> None:
    unit = _unit(
        "BAD-GAP",
        10,
        [_shot("S1", 0, 4), _shot("S2", 5, 10)],
    )
    with pytest.raises(H3ProductionPolicyError, match="contiguous"):
        validate_h3_canonical_unit(unit, provider_duration_seconds=10)


def test_pre_provider_validator_rejects_literal_inside_semantic_only_ui() -> None:
    unit = _unit(
        "BAD-TEXT",
        5,
        [
            _shot(
                "S1",
                0,
                5,
                screen_text=[
                    {
                        "legibility": "semantic_only",
                        "semantic": "identity state",
                        "text": "联合创始人",
                    }
                ],
            )
        ],
    )
    with pytest.raises(H3ProductionPolicyError, match="only exact screen text"):
        validate_h3_canonical_unit(unit, provider_duration_seconds=5)


def test_pre_provider_validator_rejects_entity_role_overlap() -> None:
    unit = _unit(
        "BAD-ROLE",
        5,
        [_shot("S1", 0, 5)],
        active_subject_ids=["C03"],
        referenced_entity_ids=["C03"],
    )
    with pytest.raises(H3ProductionPolicyError, match="roles must be disjoint"):
        validate_h3_canonical_unit(unit, provider_duration_seconds=5)
