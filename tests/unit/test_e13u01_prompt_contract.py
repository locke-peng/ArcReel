from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.experiments.run_e13u01_minimax_h3_live import (
    AUDIO_SHA256,
    BRIDGE_SHA256,
    CHARACTER_ID,
    FINAL_AVOID_LINE,
    FORBIDDEN_HOST_TRANSCRIPT,
    PROMPT,
    STAGE_SHA256,
    VISIBLE_NAME,
    VISIBLE_TITLE,
)


def test_e13u01_visual_prompt_has_only_canonical_readable_chinese() -> None:
    cjk_runs = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", PROMPT)
    assert cjk_runs
    assert set(cjk_runs) == {VISIBLE_NAME, VISIBLE_TITLE}
    assert VISIBLE_NAME == "沈知意"
    assert VISIBLE_TITLE == "天枢联合创始人"
    assert FORBIDDEN_HOST_TRANSCRIPT not in PROMPT
    assert "<d>" not in PROMPT
    assert "</d>" not in PROMPT
    assert PROMPT.rstrip().endswith(FINAL_AVOID_LINE)


def test_e13u01_binds_c01_identity_and_exact_screen_separately() -> None:
    assert CHARACTER_ID == "C01"
    assert "<Subject 2> is canonical character C01" in PROMPT
    assert "LEFT side of <Picture 2>" in PROMPT
    assert "RIGHT side of <Picture 2>" in PROMPT
    assert "Do not merge the woman's portrait into the title card." in PROMPT
    assert "No substitute woman and no identity drift." in PROMPT
    assert "text only, not a portrait or identity card" in PROMPT


def test_e13u01_inherits_physical_stage_continuity_from_e12u06() -> None:
    assert "accepted E12U06 final stage state" in PROMPT
    assert "side-stage door physically attached to the immediate stage edge" in PROMPT
    assert "very short threshold" in PROMPT
    assert "direct connection from the doorway to the stage floor" in PROMPT
    assert "There is no backstage corridor, lobby, long hallway, independent foyer, or detached doorway." in PROMPT
    assert "[Shot 2] At 00:05.000" in PROMPT


def test_e13u01_detaches_host_dialogue_into_audio_reference() -> None:
    assert "<Audio 1>" in PROMPT
    assert "off-screen host introduction followed by audience applause" in PROMPT
    assert "Never transcribe, quote, caption, subtitle" in PROMPT
    assert "No subtitle track, burned-in subtitle" in PROMPT
    assert FORBIDDEN_HOST_TRANSCRIPT == "欢迎沈知意"
    assert FORBIDDEN_HOST_TRANSCRIPT not in PROMPT


def test_e13u01_reference_hash_contract_is_exact() -> None:
    assert STAGE_SHA256 == "250960b55d6f417d6ca8f55c66cd0a6d46771253aa3165f978244681156d1023"
    assert BRIDGE_SHA256 == "e52d13f2c438382bf8de219af911ca28ab9ec172f15447f7846a1cc261f4a613"
    assert AUDIO_SHA256 == "c2feb633f8621160340ff5acda6c2de0e305e1aa2839adf90e3afef4d8d830d6"


def test_e13u01_endpoint_maps_stage_bridge_and_audio() -> None:
    definition = json.loads(
        Path("scripts/experiments/autodl_minimax_h3_e13u01_endpoint.json").read_text(encoding="utf-8")
    )
    assert definition["submit"]["url"].endswith(
        "/api/v1/comfyui/comfyui_workflow/minimax_h3_image_audio_to_video_v2_15s"
    )
    assert definition["inputs"]["stage_image"]["source"] == "start_image"
    assert definition["inputs"]["c01_screen_bridge"]["source"] == "end_image"
    assert definition["inputs"]["reference_audio"]["source"] == "reference_audio_files"
    body = definition["submit"]["body"]
    assert body["ref_image_0"] == "{{ inputs.stage_image }}"
    assert body["ref_image_1"] == "{{ inputs.c01_screen_bridge }}"
    assert body["$each"]["key"] == "ref_audio_{{ index }}"
    assert definition["capabilities"]["max_reference_audio_total_seconds"] == 15
