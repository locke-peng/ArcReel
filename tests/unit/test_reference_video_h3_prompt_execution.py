from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import (
    compile_reference_video_provider_prompt,
    should_compile_reference_video_h3,
)


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def test_auto_compiles_custom_autodl_h3_alias() -> None:
    prompt = compile_reference_video_provider_prompt(
        source_prompt="@[沈家新房] 中景。@[姜采苓]{相公，交杯酒还没喝。}",
        fallback_prompt="legacy rendered prompt",
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=[
            Entry(Ref("scene", "沈家新房")),
            Entry(Ref("character", "姜采苓")),
        ],
        payload={},
    )
    assert prompt.startswith("subject_definitions:")
    assert "<d>[Chinese] 相公，交杯酒还没喝。</d>" in prompt


def test_raw_keeps_arcreel_rendered_prompt() -> None:
    prompt = compile_reference_video_provider_prompt(
        source_prompt="@[沈家新房] 中景。",
        fallback_prompt="legacy rendered prompt",
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=[Entry(Ref("scene", "沈家新房"))],
        payload={"prompt_compiler": "raw"},
    )
    assert prompt == "legacy rendered prompt"


def test_manual_labels_must_match_actual_provider_image_count() -> None:
    with pytest.raises(ValueError, match="actual reference image count"):
        compile_reference_video_provider_prompt(
            source_prompt="@[A] @[B]",
            fallback_prompt="legacy",
            model_name="minimax_h3_zm_u24",
            duration_seconds=10,
            request_assets=[Entry(Ref("scene", "A")), Entry(Ref("character", "B"))],
            payload={"reference_image_labels": ["A"]},
        )


def test_non_h3_auto_uses_legacy_prompt() -> None:
    prompt = compile_reference_video_provider_prompt(
        source_prompt="@[A] action",
        fallback_prompt="legacy",
        model_name="seedance-2.5-pro",
        duration_seconds=10,
        request_assets=[Entry(Ref("character", "A"))],
        payload={},
    )
    assert prompt == "legacy"


def test_h3_auto_disables_legacy_visual_reuse() -> None:
    assert should_compile_reference_video_h3(
        payload={},
        model_name="minimax_h3_zm_u24",
        has_references=True,
    )
    assert not should_compile_reference_video_h3(
        payload={"prompt_compiler": "raw"},
        model_name="minimax_h3_zm_u24",
        has_references=True,
    )
