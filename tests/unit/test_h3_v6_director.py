from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.video_prompt_compilers.h3_director_compiler import (
    H3DirectorCompileError,
    compile_h3_director_prompt,
)
from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3PromptCompileError,
    compile_h3_ref2va_prompt,
)


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
                "CHAR-A": {"name": "甲"},
                "CHAR-B": {"name": "乙"},
                "CHAR-C": {"name": "丙"},
            },
            "scenes": {"SC-ROOM": "室内"},
        },
        "units": [unit],
    }


def _shot(
    shot_id: str,
    start: float,
    end: float,
    *,
    action: str,
    dialogue: list[dict] | None = None,
) -> dict:
    return {
        "shot_id": shot_id,
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "lens_mm": 50,
        "camera_position_code": "CAM-EYE",
        "camera_motion": {
            "type": "static",
            "direction": "none",
            "amplitude": "none",
            "speed": "static",
        },
        "emotion_motion": "",
        "action": action,
        "dialogue": dialogue or [],
        "screen_text": [],
    }


def test_auto_h3_without_references_compiles_t2va_from_canonical() -> None:
    unit = {
        "unit_id": "E01-U01",
        "duration_sec": 8,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-A"],
        "shots": [
            _shot(
                "E01-U01-S01",
                0,
                4,
                action="甲抬头。",
                dialogue=[{"speaker_id": "CHAR-A", "text": "你好，"}],
            ),
            _shot(
                "E01-U01-S02",
                4,
                8,
                action="甲继续。",
                dialogue=[{"speaker_id": "CHAR-A", "text": "继续说。"}],
            ),
        ],
        "cross_shot_dialogue": [
            {
                "dialogue_group_id": "D1",
                "speaker_id": "CHAR-A",
                "shot_ids": ["E01-U01-S01", "E01-U01-S02"],
                "continuous": True,
            }
        ],
        "director_notes": {"ambience": "室内底噪。", "music": "无配乐。"},
    }
    result = compile_reference_video_provider_prompt(
        source_prompt="legacy",
        fallback_prompt="legacy rendered",
        model_name="MiniMax-H3",
        duration_seconds=8,
        request_assets=[],
        payload={"canonical_director": _bundle(unit)},
        unit_id="E01-U01",
    )
    assert result.compiler_applied is True
    assert result.generation_mode == "t2va"
    assert "<Picture 1>" not in result.provider_prompt
    assert "[Shot 2] At 00:04.000" in result.provider_prompt
    assert "<scenetrans>" in result.provider_prompt
    assert "<d>[Chinese] 你好，</d>" in result.provider_prompt
    assert "，。</d>" not in result.provider_prompt
    assert "overall_soundscape:\n室内底噪。" in result.provider_prompt
    assert "non_diegetic_music:\n无配乐。" in result.provider_prompt


def test_canonical_dialogue_stays_in_its_shot() -> None:
    unit = {
        "unit_id": "E01-U04",
        "duration_sec": 9,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A", "CHAR-B"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-A", "CHAR-B"],
        "shots": [
            _shot("E01-U04-S01", 0, 3, action="开门。"),
            _shot(
                "E01-U04-S02",
                3,
                6,
                action="乙抬头。",
                dialogue=[
                    {"speaker_id": "CHAR-A", "text": "乙。"},
                    {"speaker_id": "CHAR-B", "text": "甲！"},
                ],
            ),
            _shot(
                "E01-U04-S03",
                6,
                9,
                action="乙低头。",
                dialogue=[{"speaker_id": "CHAR-B", "text": "别打断我。"}],
            ),
        ],
        "cross_shot_dialogue": [],
        "director_notes": {},
    }
    prompt, mode = compile_h3_director_prompt(
        canonical_director=_bundle(unit),
        unit_id="E01-U04",
        duration_seconds=9,
    )
    assert mode == "t2va"
    shot2 = prompt.index("[Shot 2]")
    a_line = prompt.index("甲 (S1) says")
    b_line = prompt.index("乙 (S2) says")
    shot3 = prompt.index("[Shot 3]")
    b2 = prompt.index("别打断我")
    assert shot2 < a_line < b_line < shot3 < b2


def test_depicted_and_referenced_entities_never_promoted_to_live() -> None:
    unit = {
        "unit_id": "E01-U10",
        "duration_sec": 8,
        "scene_id": "SC-ROOM",
        "continuity_level": "locked",
        "active_subject_ids": ["CHAR-A"],
        "depicted_subject_ids": ["CHAR-B"],
        "referenced_entity_ids": ["CHAR-C"],
        "speaker_semantic_order": [],
        "shots": [_shot("E01-U10-S01", 0, 8, action="甲看着墙上的照片。")],
        "cross_shot_dialogue": [],
        "director_notes": {},
    }
    prompt, _ = compile_h3_director_prompt(
        canonical_director=_bundle(unit),
        unit_id="E01-U10",
        duration_seconds=8,
    )
    assert "Embedded-media-only subjects: 乙." in prompt
    assert "do not render them as live people" in prompt
    assert "Referenced-only entities: 丙." in prompt
    assert "do not visually spawn them" in prompt


def test_ref2va_uses_only_actual_provider_references() -> None:
    unit = {
        "unit_id": "E01-U04",
        "duration_sec": 8,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A", "CHAR-B"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-A", "CHAR-B"],
        "shots": [
            _shot(
                "E01-U04-S01",
                0,
                8,
                action="两人对话。",
                dialogue=[{"speaker_id": "CHAR-A", "text": "你好。"}],
            )
        ],
        "cross_shot_dialogue": [],
        "director_notes": {},
    }
    result = compile_reference_video_provider_prompt(
        source_prompt="legacy",
        fallback_prompt="legacy rendered",
        model_name="MiniMax-H3",
        duration_seconds=8,
        request_assets=[Entry(Ref("character", "甲"))],
        payload={"canonical_director": _bundle(unit)},
        unit_id="E01-U04",
    )
    assert result.generation_mode == "ref2va"
    assert "<Picture 1>" in result.provider_prompt
    assert "<Subject 1> (S1) says" in result.provider_prompt
    assert "<Picture 2>" not in result.provider_prompt


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


def test_legacy_ref2va_keeps_dialogue_in_authored_shots_and_verbatim_punctuation() -> None:
    source = (
        "[Shot 1] @[甲]抬头。\n"
        "@[甲]：{第一句，}\n"
        "[Shot 2] At 00:03.000\n"
        "@[乙]转身。@[乙]：{第二句。}"
    )
    prompt = compile_h3_ref2va_prompt(
        source_prompt=source,
        duration_seconds=8,
        reference_count=2,
        reference_source_names=["甲", "乙"],
        options={"reference_kinds": {"甲": "character", "乙": "character"}},
    )
    shot1 = prompt.index("[Shot 1]")
    first = prompt.index("<d>[Chinese] 第一句，</d>")
    shot2 = prompt.index("[Shot 2] At 00:03.000")
    second = prompt.index("<d>[Chinese] 第二句。</d>")
    assert shot1 < first < shot2 < second
    assert "，。</d>" not in prompt

def test_rich_canonical_director_fields_render_without_replacing_core_contract() -> None:
    canonical = {
        "unit": {
            "unit_id": "E13-U03",
            "duration_sec": 5,
            "scene_id": "S14",
            "active_subject_ids": ["C01"],
            "depicted_subject_ids": [],
            "referenced_entity_ids": [],
            "continuity_level": "hard",
            "speaker_semantic_order": ["C01"],
            "cross_shot_dialogue": [],
            "sound_design": {
                "ambience": "summit room tone",
                "sfx": ["system confirmation tone"],
                "diegetic_music": [],
                "music": "N/A",
            },
            "shots": [
                {
                    "shot_id": "E13-U03-S01",
                    "start_sec": 0,
                    "duration_sec": 5,
                    "framing": {"id": "SS-03", "label": "medium shot"},
                    "angle": {"id": "AN-01", "label": "eye level"},
                    "composition": {
                        "id": "CP-02",
                        "label": "centered composition",
                    },
                    "lens_mm": 50,
                    "lens_family": "standard",
                    "depth_of_field": "moderate depth of field",
                    "camera_position_code": "CAM-EYE",
                    "camera_motion": {
                        "type": "push_in",
                        "direction": "forward",
                        "amplitude": "small",
                        "speed": "slow",
                    },
                    "lighting": {
                        "direction": {"id": "LT-02", "label": "side light"},
                        "ratio": {"id": "LR-02", "label": "medium contrast"},
                        "color_temperature": {
                            "id": "CTM-01",
                            "label": "neutral",
                        },
                        "notes": "controlled keynote lighting",
                    },
                    "color_grade": {
                        "id": "CG-17",
                        "label": "silver gray low saturation",
                    },
                    "environment": {
                        "scene_id": "S14",
                        "scene_name": "AI峰会主会场",
                        "time_of_day": "day",
                        "weather": "indoor",
                        "environment_anchors": ["main stage", "giant screen"],
                        "props": ["presentation clicker"],
                    },
                    "subject_states": [
                        {
                            "subject_id": "C01",
                            "name": "沈知意",
                            "position": "foreground",
                            "costume_variant": "W05",
                            "appearance_anchors": [
                                "female lead",
                                "white summit suit",
                            ],
                            "facial_expression": "calm authority",
                            "body_language": "upright controlled posture",
                        }
                    ],
                    "visual_style": "cinematic live-action short drama",
                    "quality_terms": ["cinematic", "high detail"],
                    "action": "沈知意 steps into the public reveal.",
                    "emotion_motion": "calm authority",
                    "screen_text": [],
                    "dialogue_direction": {"C01": "calm and controlled"},
                    "dialogue": [
                        {
                            "speaker_id": "C01",
                            "text": "我是天枢联合创始人。",
                            "offscreen": False,
                            "cutoff": False,
                        }
                    ],
                    "continuity_in": {
                        "previous_shot_id": "E13-U02-S02",
                        "state": {
                            "scene": {"scene_id": "S14"},
                            "subjects": [
                                {
                                    "subject_id": "C01",
                                    "name": "沈知意",
                                    "costume_variant": "W05",
                                }
                            ],
                        },
                    },
                    "transition_to_next": {
                        "name": "match cut",
                        "medium": "stage screen to reaction",
                    },
                    "negative_constraints": {
                        "allow_visible_text": False,
                        "allow_expressionless": False,
                        "allow_flat_lighting": False,
                        "extra_forbid": ["watermark"],
                    },
                }
            ],
        },
        "registries": {
            "characters": {"C01": {"name": "沈知意"}},
            "scenes": {"S14": {"name": "AI峰会主会场"}},
        },
    }

    prompt, mode = compile_h3_director_prompt(
        canonical_director=canonical,
        unit_id="E13-U03",
        duration_seconds=5,
        reference_source_names=["沈知意/W05", "AI峰会主会场"],
        reference_image_labels=["沈知意/W05", "AI峰会主会场"],
        reference_kinds={
            "沈知意/W05": "character",
            "AI峰会主会场": "scene",
        },
        max_prompt_chars=7000,
    )

    assert mode == "ref2va"
    assert "Visual setup: framing medium shot" in prompt
    assert "composition centered composition" in prompt
    assert "Lighting: side light" in prompt
    assert "Color grade: silver gray low saturation" in prompt
    assert "Environment: AI峰会主会场" in prompt
    assert "Subject staging: 沈知意" in prompt
    assert "costume W05" in prompt
    assert "Continuity: enter from E13-U02-S02" in prompt
    assert "Transition after shot: match cut" in prompt
    assert "SFX: system confirmation tone" in prompt
    assert "Constraints: no readable text" in prompt
    assert "<Subject 1> (S1) says" in prompt
    detailed = prompt.split("detailed_description:", 1)[1].split(
        "overall_soundscape:",
        1,
    )[0]
    assert "<Subject 1>" in detailed
    assert "<Subject 2>" in detailed

def test_canonical_t2va_uses_official_three_field_native_shape() -> None:
    unit = {
        "unit_id": "E01-U20",
        "duration_sec": 8,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-A"],
        "shots": [
            _shot(
                "E01-U20-S01",
                0,
                4,
                action="Character A raises their eyes toward the doorway.",
                dialogue=[{"speaker_id": "CHAR-A", "text": "你好，"}],
            ),
            _shot(
                "E01-U20-S02",
                4,
                8,
                action="Character A turns slightly and continues speaking.",
                dialogue=[{"speaker_id": "CHAR-A", "text": "继续说。"}],
            ),
        ],
        "cross_shot_dialogue": [
            {
                "dialogue_group_id": "D1",
                "speaker_id": "CHAR-A",
                "shot_ids": ["E01-U20-S01", "E01-U20-S02"],
                "continuous": True,
            }
        ],
        "director_notes": {
            "ambience": "Quiet indoor room tone.",
            "music": "N/A",
        },
    }

    prompt, mode = compile_h3_director_prompt(
        canonical_director=_bundle(unit),
        unit_id="E01-U20",
        duration_seconds=8,
    )

    assert mode == "t2va"
    assert prompt.startswith("integrated_multimodal_description:")
    assert "subject_definitions:" not in prompt
    assert "summary:" not in prompt
    assert "retention_analysis:" not in prompt
    assert "detailed_description:" not in prompt
    assert prompt.count("integrated_multimodal_description:") == 1
    assert prompt.count("overall_soundscape:") == 1
    assert prompt.count("non_diegetic_music:") == 1
    assert "[Shot 1] At " not in prompt
    assert "[Shot 2] At 00:04.000" in prompt


def test_speaker_ids_follow_first_actual_vocal_appearance() -> None:
    unit = {
        "unit_id": "E01-U21",
        "duration_sec": 8,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A", "CHAR-B"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-B", "CHAR-A"],
        "shots": [
            _shot(
                "E01-U21-S01",
                0,
                4,
                action="Character A speaks first.",
                dialogue=[{"speaker_id": "CHAR-A", "text": "第一句。"}],
            ),
            _shot(
                "E01-U21-S02",
                4,
                8,
                action="Character B answers.",
                dialogue=[{"speaker_id": "CHAR-B", "text": "第二句。"}],
            ),
        ],
        "cross_shot_dialogue": [],
        "director_notes": {
            "ambience": "Quiet indoor room tone.",
            "music": "N/A",
        },
    }

    prompt, _ = compile_h3_director_prompt(
        canonical_director=_bundle(unit),
        unit_id="E01-U21",
        duration_seconds=8,
    )

    assert "甲 (S1) says" in prompt
    assert "乙 (S2) says" in prompt


def test_ref2va_unused_provider_reference_fails_before_submission() -> None:
    unit = {
        "unit_id": "E01-U22",
        "duration_sec": 8,
        "scene_id": "SC-ROOM",
        "continuity_level": "hard",
        "active_subject_ids": ["CHAR-A"],
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "speaker_semantic_order": ["CHAR-A"],
        "shots": [
            _shot(
                "E01-U22-S01",
                0,
                8,
                action="Character A waits alone.",
            )
        ],
        "cross_shot_dialogue": [],
        "director_notes": {
            "ambience": "Quiet indoor room tone.",
            "music": "N/A",
        },
    }

    with pytest.raises(
        H3DirectorCompileError,
        match="not bound to any target shot or unit fact",
    ):
        compile_h3_director_prompt(
            canonical_director=_bundle(unit),
            unit_id="E01-U22",
            duration_seconds=8,
            reference_source_names=["乙"],
            reference_image_labels=["乙"],
            reference_kinds={"乙": "character"},
        )

