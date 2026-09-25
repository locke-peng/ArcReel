from __future__ import annotations

import re
from pathlib import Path

PROMPT = Path(".github/supplier-prompts/E13U01.v2.txt").read_text(encoding="utf-8")
ALLOWED = {"沈知意", "天枢联合创始人"}


def _cjk_runs(value: str) -> list[str]:
    return re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", value)


def test_v2_keeps_exact_visible_text_allowlist() -> None:
    runs = _cjk_runs(PROMPT)
    assert set(runs) == ALLOWED
    assert runs.count("沈知意") == 1
    assert runs.count("天枢联合创始人") == 1


def test_v2_opens_on_unframed_full_frame_screen() -> None:
    for token in (
        "full-frame opening composition itself",
        "edge-to-edge black",
        "no visible white border",
        "colorful surround",
        "presentation template",
        "already fully resolved at frame one",
    ):
        assert token in PROMPT


def test_v2_uses_clean_c01_identity_anchor() -> None:
    for token in (
        "clean identity anchor",
        "left portrait and right full-body view are the same woman",
        "canonical character C01 Shen Zhiyi",
        "do not substitute another woman",
    ):
        assert token in PROMPT


def test_v2_forces_character_into_spotlight_and_holds_face() -> None:
    assert "By 00:08.5 her face and upper body are inside the brightest core" in PROMPT
    assert "From 00:09.0 to 00:10.0" in PROMPT
    assert "canonical face is clearly visible for identity review" in PROMPT
    assert "must not remain so wide that her face becomes unreadable" in PROMPT


def test_v2_dialogue_stays_detached() -> None:
    assert "<d>" not in PROMPT
    assert "欢迎沈知意" not in PROMPT
    assert "added in post-production audio" in PROMPT


def test_v2_preserves_e12_stage_physics() -> None:
    for token in (
        "exact E12U06 v4 summit-stage continuity state",
        "immediate physical connection to the stage edge",
        "same short threshold",
        "spotlight origin",
    ):
        assert token in PROMPT
