from __future__ import annotations

import inspect

from scripts.experiments import run_e12u06_minimax_h3_live as e12


def test_e12u06_canonical_timing_and_provider_contract_are_locked() -> None:
    assert e12.UNIT_ID == "E12U06"
    assert e12.MODEL == "minimax_h3_zm_u24"
    assert e12.DURATION_SECONDS == 10
    assert e12.ASPECT_RATIO == "16:9"
    assert e12.RESOLUTION == "480p横"
    assert e12.CANONICAL_REFERENCE_SHA256 == (
        "7b296bcbd21fdc1ef4792649c6062355c568bf64c2756a9319d86048d38a3762"
    )


def test_e12u06_prompt_keeps_screen_state_semantic_only() -> None:
    prompt = e12.PROMPT
    assert "blank geometric placeholders" in prompt
    assert "empty horizontal bars" in prompt
    assert "readable language, names, titles, portraits, headshots, logos, letters, numbers" in prompt
    assert "glyph-like marks" in prompt
    assert "no readable characters or portrait imagery" in prompt


def test_e12u06_second_shot_locks_stage_wing_geometry_at_five_seconds() -> None:
    prompt = e12.PROMPT
    assert "[Shot 2] At 00:05.000" in prompt
    assert "stage-wing side door is built directly into the wing immediately beside the performance area" in prompt
    assert "physically touching the stage edge" in prompt
    assert "Do not depict a remote backstage corridor" in prompt


def test_e12u06_preview_runtime_lock_is_part_of_paid_supplier_path() -> None:
    source = inspect.getsource(e12.main)
    assert "provider_prompt_sha256" in source
    assert "assert_provider_prompt_matches_preview" in source
    assert "preview.provider_prompt != runtime.provider_prompt" in source


def test_e12u06_paid_path_persists_and_probes_provider_duration() -> None:
    source = inspect.getsource(e12.main)
    assert "provider_duration_seconds" in source
    assert "probe_existing_video_duration_seconds" in source
    assert '"preview_runtime_prompt_equal": True' in source
