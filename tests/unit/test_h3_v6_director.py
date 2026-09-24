from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.video_prompt_compilers.h3_director_compiler import (
    H3DirectorCompileError,
    compile_h3_director_prompt,
)
from lib.video_prompt_compilers.h3_prompt_compiler import H3PromptCompileError


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def _bundle(unit: dict) -> dict:
    return {
        "registries": {
            "characters": {
                "CHAR-A": {"name": "甲", "name_en": "Character A"},
                "CHAR-B": {"name": "乙", "name_en": "Character B"},
                "CHAR-C": {"name": "丙", "name_en": "Character C"},
            },
            "scenes": {"SC-ROOM": {"name": "室内", "name_en": "interior room"}},
        },
        "units": [unit],
    }


def _shot(
    shot_id: str,
    start: float,
    end: float,
    *,
    action_en: str,
    subjects: list[str] | None = None,
    dialogue: list[dict] | None = None,
) -> dict:
    return {
        "shot_id": shot_id,
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "subject_ids": subjects or [],
        "active_subject_ids": subjects or [],
        "shot_size_en": "a medium shot",
        "composition_en": "a balanced centered composition",
        "lighting_en": "soft natural side light",
        "color_grade_en": "a restrained neutral grade",
        "lens_mm": 50,
        "camera_position_code": "CAM-EYE",
        "camera_motion": {
            "type": "static",
            "direction": "none",
            "amplitude": "none",
            "speed": "static",
        },
        "emotion_motion_en": "a restrained visible reaction",
        "action_en": action_en,
        "dialogue": dialogue or [],
        "screen_text": [],
        "sound_en": "quiet room tone and subtle clothing movement",
    }


def _unit(unit_id: str, duration: int, shots: list[dict], **extra) -> dict:
    value = {
        "unit_id": unit_id,
        "duration_sec": duration,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A", "CHAR-B"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-B", "CHAR-A"],
        "shots": shots,
        "cross_shot_dialogue": [],
        "sound_design": {
            "ambience_en": "Quiet indoor room tone continues beneath subtle physical movement.",
            "music": "无配乐",
        },
    }
    value.update(extra)
    return value


def test_auto_h3_without_references_uses_official_t2va_three_fields() -> None:
    shots = [
        _shot(
            "E01-U01-S01",
            0,
            4,
            action_en="Character A raises their eyes toward the doorway",
            subjects=["CHAR-A"],
            dialogue=[{"speaker_id": "CHAR-A", "text": "你好，"}],
        ),
        _shot(
            "E01-U01-S02",
            4,
            8,
            action_en="Character A keeps speaking while turning slightly",
            subjects=["CHAR-A"],
            dialogue=[{"speaker_id": "CHAR-A", "text": "继续说。"}],
        ),
    ]
    unit = _unit(
        "E01-U01",
        8,
        shots,
        active_subject_ids=["CHAR-A"],
        cross_shot_dialogue=[
            {
                "dialogue_group_id": "D1",
                "speaker_id": "CHAR-A",
                "shot_ids": ["E01-U01-S01", "E01-U01-S02"],
                "continuous": True,
            }
        ],
    )
    result = compile_reference_video_provider_prompt(
        source_prompt="legacy",
        fallback_prompt="legacy rendered",
        model_name="MiniMax-H3",
        duration_seconds=8,
        request_assets=[],
        payload={"canonical_director": _bundle(unit)},
        unit_id="E01-U01",
    )
    prompt = result.provider_prompt
    assert result.compiler_applied is True
    assert result.generation_mode == "t2va"
    assert prompt.startswith("integrated_multimodal_description:")
    assert "subject_definitions:" not in prompt
    assert "summary:" not in prompt
    assert "retention_analysis:" not in prompt
    assert "[Shot 1] At " not in prompt
    assert "[Shot 2] At 00:04.000" in prompt
    assert "<d>[Chinese] 你好，<scenetrans></d>" in prompt
    assert "<d>[Chinese] <scenetrans>继续说。</d>" in prompt
    assert "continues seamlessly across the cut" in prompt
    assert "overall_soundscape: Quiet indoor room tone" in prompt
    assert "non_diegetic_music: N/A" in prompt


def test_speaker_ids_follow_actual_vocal_order_not_semantic_order() -> None:
    unit = _unit(
        "E01-U04",
        9,
        [
            _shot("S1", 0, 3, action_en="The door opens", subjects=["CHAR-A", "CHAR-B"]),
            _shot(
                "S2",
                3,
                6,
                action_en="Character B raises their head",
                subjects=["CHAR-A", "CHAR-B"],
                dialogue=[
                    {"speaker_id": "CHAR-A", "text": "乙。"},
                    {"speaker_id": "CHAR-B", "text": "甲！"},
                ],
            ),
            _shot(
                "S3",
                6,
                9,
                action_en="Character B looks down again",
                subjects=["CHAR-B"],
                dialogue=[{"speaker_id": "CHAR-B", "text": "别打断我。"}],
            ),
        ],
    )
    prompt, mode = compile_h3_director_prompt(
        canonical_director=_bundle(unit), unit_id="E01-U04", duration_seconds=9
    )
    assert mode == "t2va"
    # speaker_semantic_order is intentionally reversed in _unit; actual vocal order wins.
    assert "The on-screen speaker (S1) says" in prompt
    assert "The on-screen speaker (S2) says" in prompt
    assert prompt.index("<d>[Chinese] 乙。</d>") < prompt.index("<d>[Chinese] 甲！</d>")


def test_ref2va_uses_only_actual_provider_references_and_binds_them_in_shots() -> None:
    unit = _unit(
        "E01-U04",
        8,
        [
            _shot(
                "S1",
                0,
                8,
                action_en="Character A addresses Character B across the room",
                subjects=["CHAR-A", "CHAR-B"],
                dialogue=[{"speaker_id": "CHAR-A", "text": "你好。"}],
            )
        ],
    )
    result = compile_reference_video_provider_prompt(
        source_prompt="legacy",
        fallback_prompt="legacy rendered",
        model_name="MiniMax-H3",
        duration_seconds=8,
        request_assets=[Entry(Ref("character", "甲"))],
        payload={"canonical_director": _bundle(unit)},
        unit_id="E01-U04",
    )
    prompt = result.provider_prompt
    assert result.generation_mode == "ref2va"
    assert prompt.startswith("subject_definitions:")
    assert "<Subject 1> is the character defined by <Picture 1>" in prompt
    assert "<Subject 1> is visibly present in this shot" in prompt
    assert "<Subject 1> (S1) says" in prompt
    assert "<Picture 2>" not in prompt
    assert "[reference generation]" in prompt


def test_v33_visual_director_dimensions_survive_as_natural_english() -> None:
    shot1 = _shot(
        "S1",
        0,
        5,
        action_en="Character A remains still beside the control console",
        subjects=["CHAR-A"],
    )
    shot1.update(
        {
            "shot_size_en": "an extreme close-up",
            "composition_en": "a centered symmetrical composition",
            "lighting_en": "cool overhead key light with restrained side fill",
            "color_grade_en": "a cool desaturated technology-conference grade",
            "scene_anchors_en": "the main screen and the control console remain fixed in their established positions",
            "transition_out": "dissolve",
        }
    )
    shot2 = _shot(
        "S2",
        5,
        10,
        action_en="Character A turns from the console toward the main screen",
        subjects=["CHAR-A"],
    )
    shot2["transition_in"] = "dissolve"
    unit = _unit(
        "E13-U01",
        10,
        [shot1, shot2],
        active_subject_ids=["CHAR-A"],
        scene_anchors_en="the main screen, control console, side-stage door, and VIP front row",
        continuity_in_en="Character A begins beside the control console with the main screen dark",
        continuity_out_en="Character A faces the illuminated main screen at the end",
    )
    prompt, _ = compile_h3_director_prompt(
        canonical_director=_bundle(unit), unit_id="E13-U01", duration_seconds=10
    )
    for expected in (
        "an extreme close-up",
        "a centered symmetrical composition",
        "cool overhead key light with restrained side fill",
        "a cool desaturated technology-conference grade",
        "the main screen and the control console remain fixed",
        "the shot cross-dissolves into the next view",
        "Stable spatial anchors across the unit are",
        "At the opening, preserve the incoming continuity state",
        "By the end, establish the outgoing continuity state",
    ):
        assert expected in prompt


def test_exact_original_language_screen_text_is_allowed_only_as_visible_text() -> None:
    shot = _shot(
        "S1",
        0,
        8,
        action_en="Character A looks toward the conference screen",
        subjects=["CHAR-A"],
    )
    shot["screen_text"] = [
        {
            "kind": "identity title",
            "legibility": "exact",
            "text": "沈知意 / 天枢联合创始人·原始架构师",
        }
    ]
    unit = _unit("E13-U02", 8, [shot], active_subject_ids=["CHAR-A"])
    prompt, _ = compile_h3_director_prompt(
        canonical_director=_bundle(unit), unit_id="E13-U02", duration_seconds=8
    )
    assert 'reads "沈知意 / 天枢联合创始人·原始架构师" clearly' in prompt


def test_non_english_semantic_director_prose_fails_before_provider() -> None:
    shot = _shot("S1", 0, 8, action_en="", subjects=["CHAR-A"])
    shot["action"] = "她缓慢抬头。"
    unit = _unit("BAD", 8, [shot], active_subject_ids=["CHAR-A"])
    with pytest.raises(H3DirectorCompileError, match="action_en"):
        compile_h3_director_prompt(
            canonical_director=_bundle(unit), unit_id="BAD", duration_seconds=8
        )


def test_unused_provider_reference_fails_closed() -> None:
    unit = _unit(
        "U",
        8,
        [_shot("S1", 0, 8, action_en="Character A waits alone", subjects=["CHAR-A"])],
        active_subject_ids=["CHAR-A"],
    )
    with pytest.raises(H3DirectorCompileError, match="not bound to any target shot"):
        compile_h3_director_prompt(
            canonical_director=_bundle(unit),
            unit_id="U",
            duration_seconds=8,
            reference_source_names=["乙"],
            reference_image_labels=["乙"],
            reference_kinds={"乙": "character"},
        )


def test_forced_ref2va_without_reference_still_fails() -> None:
    with pytest.raises(H3PromptCompileError, match="at least one"):
        compile_reference_video_provider_prompt(
            source_prompt="x",
            fallback_prompt="legacy",
            model_name="MiniMax-H3",
            duration_seconds=5,
            request_assets=[],
            payload={"prompt_compiler": "h3_ref2va"},
        )