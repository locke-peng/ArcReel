from __future__ import annotations

import re
from pathlib import Path

PROMPT_PATH = Path(".github/supplier-prompts/E13U01.v1.txt")
PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

ALLOWED = {"沈知意", "天枢联合创始人"}


def _cjk_runs(value: str) -> list[str]:
    return re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", value)


def test_e13u01_is_two_shot_ten_second_unit() -> None:
    assert "[Shot 1] 00:00-00:05." in PROMPT
    assert "[Shot 2] At 00:05.000" in PROMPT
    assert "10-second" in PROMPT


def test_e13u01_visible_text_is_static_exact_allowlist() -> None:
    runs = _cjk_runs(PROMPT)
    assert set(runs) == ALLOWED
    assert runs.count("沈知意") == 1
    assert runs.count("天枢联合创始人") == 1
    assert '"沈知意"' in PROMPT
    assert '"天枢联合创始人"' in PROMPT


def test_e13u01_dialogue_is_detached_from_visual_prompt() -> None:
    assert "<d>" not in PROMPT
    assert "欢迎沈知意" not in PROMPT
    assert "do not synthesize or typeset host dialogue" in PROMPT
    assert "added in post-production audio" in PROMPT


def test_e13u01_locks_e12u06_stage_continuity() -> None:
    for token in (
        "exact E12U06 v4 summit-stage continuity state",
        "same stage-wing door",
        "immediate physical connection to the stage edge",
        "same floor geometry",
        "same spotlight",
        "short threshold",
    ):
        assert token in PROMPT


def test_e13u01_locks_c01_identity() -> None:
    for token in (
        "canonical character C01 Shen Zhiyi",
        "Preserve her exact face identity",
        "white tailored trouser suit",
        "Do not substitute another woman",
        "only featured person",
    ):
        assert token in PROMPT


def test_e13u01_uses_positive_screen_state_plus_final_avoid_guard() -> None:
    assert "The two strings are presented as two centered lines exactly as shown in <Picture 2>." in PROMPT
    assert "The title is the only readable content in frame." in PROMPT
    assert PROMPT.rstrip().endswith(
        "Avoid: BGM, subtitles, captions, dialogue transcription, speech bubbles, lower-thirds, "
        "watermarks, logos, timestamps, pseudo-text, and any readable text except the two approved screen strings."
    )
