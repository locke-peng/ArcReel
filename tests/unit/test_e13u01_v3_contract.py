from __future__ import annotations

import re
from pathlib import Path

PROMPT = Path(".github/supplier-prompts/E13U01.v3.txt").read_text(encoding="utf-8")
ALLOWED = {"沈知意", "天枢联合创始人"}


def _cjk_runs(value: str) -> list[str]:
    return re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", value)


def test_v3_exact_text_allowlist() -> None:
    runs = _cjk_runs(PROMPT)
    assert set(runs) == ALLOWED
    assert runs.count("沈知意") == 1
    assert runs.count("天枢联合创始人") == 1


def test_v3_shot1_is_edge_to_edge_reference_state() -> None:
    assert "fills the complete frame edge-to-edge from the first frame" in PROMPT
    assert "already fully resolved at 00:00" in PROMPT
    assert "No bezel, wall, stage, colorful surround" in PROMPT


def test_v3_shot2_excludes_main_screen_loading_state() -> None:
    assert "crop the main LED screen completely out of view" in PROMPT
    assert "No main-screen loading blocks are visible" in PROMPT


def test_v3_followspot_acquires_c01_early() -> None:
    assert "follow-spot visibly pans left" in PROMPT
    assert "By 00:07.0 the spotlight reaches her" in PROMPT
    assert "By 00:07.5 her face, shoulders, torso, and white suit are clearly inside" in PROMPT
    assert "From 00:08.0 through 00:10.0 she stops in that light" in PROMPT


def test_v3_c01_identity_and_stage_continuity_are_locked() -> None:
    for token in (
        "canonical character C01 Shen Zhiyi",
        "exact C01 facial identity",
        "exact side-door architecture",
        "short threshold",
        "wall panels",
        "floor identical to <Picture 2>",
    ):
        assert token in PROMPT


def test_v3_dialogue_is_detached() -> None:
    assert "<d>" not in PROMPT
    assert "欢迎沈知意" not in PROMPT
    assert "added in post-production audio" in PROMPT
