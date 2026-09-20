from pathlib import Path

import pytest

from lib.video_backends.base import VideoGenerationRequest
from lib.video_prompt_compilers import compile_video_request_prompt
from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3PromptCompileError,
    compile_h3_ref2va_prompt,
)


def _request(prompt: str, *, refs: int = 3, model_refs: bool = True) -> VideoGenerationRequest:
    return VideoGenerationRequest(
        prompt=prompt,
        output_path=Path("/tmp/out.mp4"),
        duration_seconds=10,
        reference_images=[Path(f"/tmp/ref-{i}.png") for i in range(refs)] if model_refs else None,
        reference_image_labels=["沈家新房", "姜采苓", "沈延/被附身"][:refs] if refs else None,
    )


def test_compile_six_sections_and_preserve_reference_order() -> None:
    prompt = (
        "@[沈家新房] 中景，50mm，固定镜头。"
        "@[姜采苓] 红色喜服，递酒给 @[沈延/被附身]。"
    )
    result = compile_h3_ref2va_prompt(
        source_prompt=prompt,
        duration_seconds=10,
        reference_count=3,
        reference_image_labels=["沈家新房", "姜采苓", "沈延/被附身"],
        options={
            "reference_kinds": {
                "沈家新房": "scene",
                "姜采苓": "character",
                "沈延/被附身": "character",
            }
        },
    )

    assert result.index("<Subject 1>") < result.index("<Subject 2>") < result.index("<Subject 3>")
    assert "<Subject 1> is the environment derived from <Picture 1>" in result
    assert "<Subject 2> is the character derived from <Picture 2>" in result
    assert "[Shot 1]" in result
    for section in (
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ):
        assert section in result


def test_canonical_arcreel_dialogue_becomes_h3_dialogue() -> None:
    prompt = """@[沈家新房] 固定中景。
@[姜采苓] 递出交杯酒。
@[沈延/被附身] 略显迟滞。
@[姜采苓]：{相公，交杯酒还没喝。}
"""
    result = compile_h3_ref2va_prompt(
        source_prompt=prompt,
        duration_seconds=10,
        reference_count=3,
        reference_image_labels=["沈家新房", "姜采苓", "沈延/被附身"],
        options={"voice_styles": {"姜采苓": "a soft youthful female voice with a shy gentle delivery"}},
    )

    assert "<Subject 2> (S1) says" in result
    assert "<d>[Chinese] 相公，交杯酒还没喝。</d>" in result
    # Authoring syntax must not leak into the provider prompt.
    assert "@[姜采苓]：{" not in result


def test_existing_h3_dialogue_tag_is_preserved_and_bound_to_nearest_speaker() -> None:
    prompt = (
        "@[姜采苓] 红色喜服。"
        "身着红色喜服的@[姜采苓]轻声说："
        "<d>[Chinese] 相公，交杯酒还没喝。</d>"
    )
    result = compile_h3_ref2va_prompt(
        source_prompt=prompt,
        duration_seconds=8,
        reference_count=1,
        reference_image_labels=["姜采苓"],
    )
    assert "<Subject 1> (S1) says" in result
    assert "<d>[Chinese] 相公，交杯酒还没喝。</d>" in result


def test_dispatcher_auto_compiles_minimax_h3_and_preserves_other_fields() -> None:
    request = _request("@[沈家新房] 内 @[姜采苓] 面向 @[沈延/被附身]。")
    result = compile_video_request_prompt(request, model="MiniMax-H3")

    assert result is not request
    assert result.output_path == request.output_path
    assert result.reference_images == request.reference_images
    assert result.duration_seconds == request.duration_seconds
    assert result.prompt.startswith("subject_definitions:")


def test_dispatcher_recognizes_custom_autodl_h3_model_alias() -> None:
    request = _request("@[沈家新房] 内 @[姜采苓] 面向 @[沈延/被附身]。")
    result = compile_video_request_prompt(request, model="minimax_h3_zm_u24")
    assert result.prompt.startswith("subject_definitions:")


def test_raw_override_disables_compilation() -> None:
    request = _request("@[沈家新房] test")
    request.prompt_compiler = "raw"
    result = compile_video_request_prompt(request, model="MiniMax-H3")
    assert result is request


def test_non_h3_model_is_unchanged() -> None:
    request = _request("@[沈家新房] test")
    result = compile_video_request_prompt(request, model="seedance-2.5-pro")
    assert result is request


def test_reference_label_count_must_match_reference_images() -> None:
    with pytest.raises(H3PromptCompileError, match="same length and order"):
        compile_h3_ref2va_prompt(
            source_prompt="@[A] @[B]",
            duration_seconds=5,
            reference_count=2,
            reference_image_labels=["A"],
        )


def test_h3_reference_limit_is_fail_loud() -> None:
    with pytest.raises(H3PromptCompileError, match="at most 9"):
        compile_h3_ref2va_prompt(
            source_prompt="test",
            duration_seconds=5,
            reference_count=10,
        )


def test_duration_limit_is_fail_loud() -> None:
    with pytest.raises(H3PromptCompileError, match="4-15"):
        compile_h3_ref2va_prompt(
            source_prompt="@[A] test",
            duration_seconds=16,
            reference_count=1,
            reference_image_labels=["A"],
        )


def test_compiler_is_idempotent_for_already_compiled_prompt() -> None:
    compiled = compile_h3_ref2va_prompt(
        source_prompt="@[A] test",
        duration_seconds=5,
        reference_count=1,
        reference_image_labels=["A"],
    )
    result = compile_h3_ref2va_prompt(
        source_prompt=compiled,
        duration_seconds=5,
        reference_count=1,
        reference_image_labels=["A"],
    )
    assert result == compiled


def test_prompt_limit_is_checked_before_provider_submission() -> None:
    with pytest.raises(H3PromptCompileError, match="limit is 300"):
        compile_h3_ref2va_prompt(
            source_prompt="@[A] " + ("动作描述" * 200),
            duration_seconds=5,
            reference_count=1,
            reference_image_labels=["A"],
            options={"max_prompt_chars": 300},
        )