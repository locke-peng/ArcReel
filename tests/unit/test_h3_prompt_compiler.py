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

