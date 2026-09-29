from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.reference_video.prompt_compiler_options import (
    normalize_prompt_compiler,
    resolve_reference_image_labels,
)
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from lib.video_prompt_compilers.h3_director_compiler import compile_h3_text_t2va_prompt
from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3PromptCompileError,
    compile_h3_ref2va_prompt,
    validate_h3_native_ref2va_structure,
    validate_h3_native_t2va_structure,
)


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def test_six_sections_reference_order_and_dialogue() -> None:
    prompt = (
        "@[沈家新房] 中景，50mm，固定镜头。"
        "@[姜采苓] 红色喜服，递酒给 @[沈延/被附身]。"
        "@[姜采苓]：{相公，交杯酒还没喝。}"
    )
    result = compile_h3_ref2va_prompt(
        source_prompt=prompt,
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
    for section in (
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ):
        assert section in result
    assert "<Subject 1>" in result
    assert "<Subject 2>" in result
    assert "<Subject 3>" in result
    # Replacement uses ArcReel source name even when display label differs.
    assert "[Shot 1] <Subject 1>" in result
    assert "<Subject 2> (S1) says" in result
    assert "<d>[Chinese] 相公，交杯酒还没喝。</d>" in result


def test_existing_h3_prompt_is_idempotent() -> None:
    first = compile_h3_ref2va_prompt(
        source_prompt="@[A] action",
        duration_seconds=5,
        reference_count=1,
        reference_source_names=["A"],
    )
    second = compile_h3_ref2va_prompt(
        source_prompt=first,
        duration_seconds=5,
        reference_count=1,
        reference_source_names=["A"],
    )
    assert second == first


def test_reference_and_duration_limits_fail_loudly() -> None:
    with pytest.raises(H3PromptCompileError, match="at most 9"):
        compile_h3_ref2va_prompt(
            source_prompt="x",
            duration_seconds=5,
            reference_count=10,
        )
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
    with pytest.raises(ValueError):
        normalize_prompt_compiler("other")


def test_execution_helper_auto_compiles_custom_h3_and_preview_shape() -> None:
    compilation = compile_reference_video_provider_prompt(
        source_prompt="@[沈家新房] 中景。@[姜采苓]{相公，交杯酒还没喝。}",
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

def test_docpack_contract_accepts_15_second_upper_bound_with_stable_labels() -> None:
    result = compile_h3_ref2va_prompt(
        source_prompt="@[Room] wide shot. @[Hero] turns toward camera.",
        duration_seconds=15,
        reference_count=2,
        reference_source_names=["Room", "Hero"],
        reference_image_labels=["locked-room", "locked-hero"],
        options={"reference_kinds": {"Room": "scene", "Hero": "character"}},
    )
    assert "<Subject 1>" in result
    assert "<Subject 2>" in result
    assert "[Shot 1]" in result

def test_freeform_t2va_uses_official_three_field_native_shape() -> None:
    prompt = compile_h3_text_t2va_prompt(
        source_prompt=(
            "[Shot 1] A medium shot shows the character waiting by the window.\n"
            "[Shot 2] At 00:04.000\n"
            "The character turns toward the doorway."
        ),
        duration_seconds=8,
        overall_soundscape="Quiet room tone.",
        non_diegetic_music="N/A",
    )

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

def test_multiple_pictures_can_define_one_logical_subject() -> None:
    prompt = compile_h3_ref2va_prompt(
        source_prompt=(
            "[Shot 1] A close shot shows @[Woman] turning from front view "
            "toward profile."
        ),
        duration_seconds=5,
        reference_count=2,
        reference_source_names=["Woman", "Woman"],
        reference_image_labels=["front-view", "profile-view"],
        options={"reference_kinds": {"Woman": "character"}},
    )

    assert "<Subject 1> is the character defined by <Picture 1> and <Picture 2>" in prompt
    assert "<Subject 2>" not in prompt
    assert validate_h3_native_ref2va_structure(
        prompt,
        duration_seconds=5,
        reference_count=2,
    ) == prompt


def test_native_ref2va_structure_rejects_defined_but_unused_subject() -> None:
    prompt = """subject_definitions:
<Subject 1> is the character defined by <Picture 1>, corresponding to Hero.

summary:
[reference generation] Create one five-second target video.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - preserve identity.

detailed_description:
[Shot 1] A medium shot shows an empty room.

overall_soundscape:
Quiet room tone.

non_diegetic_music:
N/A"""

    with pytest.raises(
        H3PromptCompileError,
        match="defined but never applied",
    ):
        validate_h3_native_ref2va_structure(
            prompt,
            duration_seconds=5,
            reference_count=1,
        )


def test_native_t2va_structure_rejects_full_reference_labels() -> None:
    prompt = """integrated_multimodal_description:
[Shot 1] <Subject 1> waits by the window.

overall_soundscape:
Quiet room tone.

non_diegetic_music:
N/A"""

    with pytest.raises(H3PromptCompileError, match="full-reference labels"):
        validate_h3_native_t2va_structure(
            prompt,
            duration_seconds=5,
        )

def test_existing_native_t2va_prompt_is_idempotent() -> None:
    native = """integrated_multimodal_description:
[Shot 1] A medium shot shows the character waiting by the window.
[Shot 2] At 00:04.000
The character turns toward the doorway.

overall_soundscape:
Quiet room tone.

non_diegetic_music:
N/A"""

    assert compile_h3_text_t2va_prompt(
        source_prompt=native,
        duration_seconds=8,
    ) == native

def test_preview_mapping_tracks_multi_picture_logical_subject() -> None:
    compilation = compile_reference_video_provider_prompt(
        source_prompt="[Shot 1] A close shot shows @[Woman] turning toward profile.",
        fallback_prompt="legacy",
        model_name="MiniMax-H3",
        duration_seconds=5,
        request_assets=[
            Entry(Ref("character", "Woman")),
            Entry(Ref("character", "Woman")),
        ],
        payload={"reference_image_labels": ["front-view", "profile-view"]},
    )
    preview = build_reference_prompt_preview_payload(compilation)

    assert preview["reference_mapping"][0]["subject"] == "<Subject 1>"
    assert preview["reference_mapping"][1]["subject"] == "<Subject 1>"

