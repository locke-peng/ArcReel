from __future__ import annotations

import hashlib

from scripts.experiments.run_e4u02_minimax_h3_live import (
    CHARACTER_ID,
    CHARACTER_NAME,
    CHARACTER_REF,
    DIALOGUE_1,
    DIALOGUE_2,
    ONLY_VISIBLE_TEXT,
    PROMPT,
)


EXPECTED_C03_FACE_SHA256 = "c3ea705490e1367950a6bc95ea225e0982b6c01c0b1810184cb9f8a9b9f800fc"


def test_e4u02_v3_uses_canonical_c03_reference_asset() -> None:
    assert CHARACTER_ID == "C03"
    assert CHARACTER_NAME == "陆念"
    assert CHARACTER_REF.is_file()
    assert hashlib.sha256(CHARACTER_REF.read_bytes()).hexdigest() == EXPECTED_C03_FACE_SHA256


def test_e4u02_v3_shot2_and_shot3_share_one_character_identity() -> None:
    assert "<Subject 2> is canonical character C03 陆念" in PROMPT
    assert "one person across both memory shots" in PROMPT
    assert "two ages of ONE PERSON" in PROMPT
    assert "same canonical person, C03 陆念" in PROMPT
    assert "No face substitution" in PROMPT
    assert "do not change facial identity" in PROMPT
    assert "<Subject 3>" not in PROMPT


def test_e4u02_v3_preserves_previous_text_and_dialogue_guards() -> None:
    assert ONLY_VISIBLE_TEXT == "给念念打电话"
    assert PROMPT.count(ONLY_VISIBLE_TEXT) >= 4
    assert f"<d>[Chinese] {DIALOGUE_1}</d>" in PROMPT
    assert f"<d>[Chinese] {DIALOGUE_2}</d>" in PROMPT
    assert "sole readable text allowed" in PROMPT
    assert "AUDIO-ONLY" in PROMPT
    assert "Never render any <d> content as on-screen text" in PROMPT
