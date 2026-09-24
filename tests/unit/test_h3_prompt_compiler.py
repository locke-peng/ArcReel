from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.reference_video.prompt_compiler_options import (
    normalize_prompt_compiler,
    resolve_reference_image_labels,
)
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3PromptCompileError,
    compile_h3_ref2va_prompt,
    validate_h3_native_ref2va_prompt,
)


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def _english_ref_source() -> str:
    return """[Shot 1] A medium shot establishes @[沈家新房] under warm practical light. @[姜采苓] stands beside the table and turns toward @[沈延/被附身].
@[姜采苓]：{相公，交杯酒还没喝。}
Sound: Quiet indoor room tone and a soft fabric rustle.
[Shot 2] At 00:05.000
The shot cuts to a close view of @[姜采苓] lowering the cup while @[沈延/被附身] remains still.
Sound: A ceramic cup touches the table softly."""


def test_ref2va_uses_official_six_sections_and_native_dialogue() -> None:
    result = compile_h3_ref2va_prompt(
        source_prompt=_english_ref_source(),
        duration_seconds=10,
        reference_count=3,
        reference_source_names=["沈家新房", "姜采苓", "沈延/被附身"],
        reference_image_labels=["scene-room", "heroine", "possessed-hero"],
        options={
            "reference_kinds": {
                "沈家新房": "scene",
                "姜采苓": "character",
                "沈延/被附身": "character",
            }
        },
    )
    expected_order = [
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ]
    offsets = [result.index(section) for section in expected_order]
    assert offsets == sorted(offsets)
    assert "ARCREEL_H3_VISUAL_FRAME_POLICY" not in result
    assert "Visual-frame note:" not in result
    assert "[reference generation]" in result
    assert "<Subject 2> (S1) says" in result
    assert "<d>[Chinese] 相公，交杯酒还没喝。</d>" in result
    assert "closes their lips and stops speaking" in result
    assert "[Shot 1] At " not in result
    assert "[Shot 2] At 00:05.000" in result


def test_legacy_chinese_execution_prose_fails_closed() -> None:
    source = "@[沈家新房] 中景，50mm，固定镜头。@[姜采苓]：{相公，交杯酒还没喝。}"
    with pytest.raises(H3PromptCompileError, match="non-English execution prose"):
        compile_h3_ref2va_prompt(
            source_prompt=source,
            duration_seconds=10,
            reference_count=2,
            reference_source_names=["沈家新房", "姜采苓"],
        )


def test_existing_native_ref2va_prompt_is_idempotent() -> None:
    first = compile_h3_ref2va_prompt(
        source_prompt=_english_ref_source(),
        duration_seconds=10,
        reference_count=3,
        reference_source_names=["沈家新房", "姜采苓", "沈延/被附身"],
        options={
            "reference_kinds": {
                "沈家新房": "scene",
                "姜采苓": "character",
                "沈延/被附身": "character",
            }
        },
    )
    second = compile_h3_ref2va_prompt(
        source_prompt=first,
        duration_seconds=10,
        reference_count=3,
        reference_source_names=["沈家新房", "姜采苓", "沈延/被附身"],
    )
    assert second == first


def test_multiple_pictures_can_define_one_subject_without_fake_picture_entities() -> None:
    prompt = compile_h3_ref2va_prompt(
        source_prompt="""[Shot 1] A close shot shows @[Woman] turning her head from front view toward profile.
Sound: Quiet room tone.""",
        duration_seconds=5,
        reference_count=2,
        reference_source_names=["Woman", "Woman"],
        reference_image_labels=["front-view", "profile-view"],
        options={"reference_kinds": {"Woman": "character"}},
    )
    assert "<Subject 1> is the character defined by <Picture 1> and <Picture 2>" in prompt
    assert "<Subject 2>" not in prompt
    assert "\n<Picture 1> is " not in prompt
    assert "\n<Picture 2> is " not in prompt


def test_native_validator_rejects_unbound_subject_and_picture_misuse() -> None:
    prompt = """subject_definitions:
<Subject 1> is the character defined by <Picture 1>; preserve identity.

summary:
[reference generation] The target video uses <Subject 1>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity is retained.

detailed_description:
Live-action drama with natural lighting.
[Shot 1] A medium shot shows an empty room.

overall_soundscape:
Quiet room tone continues throughout.

non_diegetic_music:
N/A"""
    with pytest.raises(H3PromptCompileError, match="defined but never applied"):
        validate_h3_native_ref2va_prompt(prompt, duration_seconds=5, reference_count=1)


def test_reference_and_duration_limits_fail_loudly() -> None:
    with pytest.raises(H3PromptCompileError, match="at most 9"):
        compile_h3_ref2va_prompt(source_prompt="x", duration_seconds=5, reference_count=10)
    with pytest.raises(H3PromptCompileError, match="4-15"):
        compile_h3_ref2va_prompt(
            source_prompt="@[A] x",
            duration_seconds=16,
            reference_count=1,
            reference_source_names=["A"],
        )


def test_manual_labels_must_match_actual_provider_order_count() -> None:
    with pytest.raises(ValueError, match="actual reference image count"):
        resolve_reference_image_labels(["A"], derived=["A", "B"])


def test_prompt_compiler_modes() -> None:
    assert normalize_prompt_compiler(None) == "auto"
    assert normalize_prompt_compiler(" H3_REF2VA ") == "h3_ref2va"
    assert normalize_prompt_compiler("raw") == "raw"
    with pytest.raises(ValueError, match="prompt_compiler must be one of"):
        normalize_prompt_compiler("other")


def test_execution_helper_compiles_custom_h3_and_preview_mapping() -> None:
    source = """[Shot 1] A medium shot establishes @[沈家新房]. @[姜采苓] raises a cup and speaks.
@[姜采苓]：{相公，交杯酒还没喝。}
Sound: Quiet indoor room tone."""
    compilation = compile_reference_video_provider_prompt(
        source_prompt=source,
        fallback_prompt="legacy rendered prompt",
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=[
            Entry(Ref("scene", "沈家新房")),
            Entry(Ref("character", "姜采苓")),
        ],
        payload={},
        max_prompt_chars=500000,
    )
    assert compilation.compiler_applied is True
    assert compilation.generation_mode == "ref2va"
    assert compilation.provider_prompt.startswith("subject_definitions:")
    assert compilation.reference_image_labels == ("沈家新房", "姜采苓")
    preview = build_reference_prompt_preview_payload(compilation)
    assert preview["max_prompt_chars"] == 500000
    assert preview["reference_mapping"][0] == {
        "index": 1,
        "picture": "<Picture 1>",
        "subject": "<Subject 1>",
        "label": "沈家新房",
        "source_name": "沈家新房",
    }


def test_raw_keeps_legacy_prompt() -> None:
    compilation = compile_reference_video_provider_prompt(
        source_prompt="@[A] action",
        fallback_prompt="legacy",
        model_name="minimax_h3_zm_u24",
        duration_seconds=5,
        request_assets=[Entry(Ref("character", "A"))],
        payload={"prompt_compiler": "raw"},
    )
    assert compilation.compiler_applied is False
    assert compilation.provider_prompt == "legacy"


def test_force_h3_without_reference_fails() -> None:
    with pytest.raises(H3PromptCompileError, match="requires at least one"):
        compile_reference_video_provider_prompt(
            source_prompt="plain",
            fallback_prompt="legacy",
            model_name="minimax_h3_zm_u24",
            duration_seconds=5,
            request_assets=[],
            payload={"prompt_compiler": "h3_ref2va"},
        )