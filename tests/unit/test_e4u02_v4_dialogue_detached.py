from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.experiments.run_e4u02_minimax_h3_audio_detached_live import (
    CHARACTER_ID,
    CURRENT_CHARACTER_REF,
    CURRENT_CHARACTER_SHA256,
    FINAL_AVOID_LINE,
    FORBIDDEN_DIALOGUE_1,
    FORBIDDEN_DIALOGUE_2,
    ONLY_VISIBLE_TEXT,
    PROMPT,
    YOUNG_CHARACTER_REF,
    YOUNG_CHARACTER_SHA256,
    _sha256,
)


def test_e4u02_v4_dialogue_tokens_are_absent_from_visual_provider_prompt() -> None:
    assert "<d>" not in PROMPT
    assert "</d>" not in PROMPT
    assert FORBIDDEN_DIALOGUE_1 not in PROMPT
    assert FORBIDDEN_DIALOGUE_2 not in PROMPT
    assert "<Audio 1>" in PROMPT
    assert "<Audio 1>: fully_copy" in PROMPT
    assert "spoken content is audio-only" in PROMPT
    assert "do not print or display what is spoken" in PROMPT


def test_e4u02_v4_only_cjk_text_in_provider_prompt_is_legal_phone_label() -> None:
    cjk_runs = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", PROMPT)
    assert cjk_runs
    assert set(cjk_runs) == {ONLY_VISIBLE_TEXT}
    assert PROMPT.count(ONLY_VISIBLE_TEXT) >= 4
    assert PROMPT.rstrip().endswith(FINAL_AVOID_LINE)


def test_e4u02_v4_keeps_official_c03_two_age_identity_chain() -> None:
    assert CHARACTER_ID == "C03"
    assert YOUNG_CHARACTER_REF.is_file()
    assert CURRENT_CHARACTER_REF.is_file()
    assert _sha256(YOUNG_CHARACTER_REF) == YOUNG_CHARACTER_SHA256
    assert _sha256(CURRENT_CHARACTER_REF) == CURRENT_CHARACTER_SHA256
    assert "LEFT is the younger age and RIGHT is the later age" in PROMPT
    assert "SAME PERSON at different ages" in PROMPT
    assert "same C03 child at two ages" in PROMPT
    assert "No face substitution" in PROMPT


def test_e4u02_v4_autodl_endpoint_maps_images_and_audio_separately() -> None:
    definition = json.loads(
        Path("scripts/experiments/autodl_minimax_h3_image_audio_endpoint.json").read_text(encoding="utf-8")
    )
    assert definition["submit"]["url"].endswith(
        "/api/v1/comfyui/comfyui_workflow/minimax_h3_image_audio_to_video_v2_15s"
    )
    assert definition["inputs"]["phone_image"]["source"] == "start_image"
    assert definition["inputs"]["identity_bridge"]["source"] == "end_image"
    assert definition["inputs"]["reference_audio"]["source"] == "reference_audio_files"

    body = definition["submit"]["body"]
    assert body["ref_image_0"] == "{{ inputs.phone_image }}"
    assert body["ref_image_1"] == "{{ inputs.identity_bridge }}"
    assert body["$each"]["in"] == "inputs.reference_audio"
    assert body["$each"]["key"] == "ref_audio_{{ index }}"

    caps = definition["capabilities"]
    assert caps["reference_audio_mode"] == "direct"
    assert caps["max_reference_audio_count"] == 3
    assert caps["max_reference_audio_total_seconds"] == 15
    assert caps["audio_track"] == "always_on"
