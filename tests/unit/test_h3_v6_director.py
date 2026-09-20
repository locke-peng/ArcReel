
from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.video_prompt_compilers.h3_director_compiler import compile_h3_director_prompt
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
