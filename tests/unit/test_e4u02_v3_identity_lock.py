import hashlib

from scripts.experiments.run_e4u02_minimax_h3_live import (
    CHARACTER_ID,
    CHARACTER_NAME,
    CURRENT_CHARACTER_REF,
    CURRENT_CHARACTER_SHA256,
    DIALOGUE_1,
    DIALOGUE_2,
    ONLY_VISIBLE_TEXT,
    PROMPT,
    YOUNG_CHARACTER_NAME,
    YOUNG_CHARACTER_REF,
    YOUNG_CHARACTER_SHA256,
)


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_e4u02_v3_uses_exact_official_age_specific_c03_assets() -> None:
    assert CHARACTER_ID == "C03"
    assert CHARACTER_NAME == "陆念"
    assert YOUNG_CHARACTER_NAME == "幼年陆念"
    assert YOUNG_CHARACTER_REF.is_file()
    assert CURRENT_CHARACTER_REF.is_file()
    assert YOUNG_CHARACTER_SHA256 == "6f0fe84b8e150abce613499536dd614302598767836083209a2aa5e58d60ecde"
    assert CURRENT_CHARACTER_SHA256 == "c92b71c3fe707088dd340d41de9a202e2ab7d02392fef4913b2df6959c4932b0"
    assert _sha256(YOUNG_CHARACTER_REF) == YOUNG_CHARACTER_SHA256
    assert _sha256(CURRENT_CHARACTER_REF) == CURRENT_CHARACTER_SHA256


def test_e4u02_v3_shots_bind_to_the_correct_age_reference_without_swapping() -> None:
    assert "<Subject 2> is 幼年陆念" in PROMPT
    assert "<Subject 3> is canonical character C03 陆念" in PROMPT
    assert "[Shot 2] must use <Subject 2> from <Picture 2>" in PROMPT
    assert "[Shot 3] must use <Subject 3> from <Picture 3>" in PROMPT
    assert "<Subject 2> and <Subject 3> are the SAME PERSON at two ages" in PROMPT
    assert "never swap the two age references" in PROMPT
    assert "No face substitution" in PROMPT
    assert "do not merge the two references into a new face" in PROMPT.lower()


def test_e4u02_v3_preserves_previous_text_and_dialogue_guards() -> None:
    assert ONLY_VISIBLE_TEXT == "给念念打电话"
    assert PROMPT.count(ONLY_VISIBLE_TEXT) >= 4
    assert f"<d>[Chinese] {DIALOGUE_1}</d>" in PROMPT
    assert f"<d>[Chinese] {DIALOGUE_2}</d>" in PROMPT
    assert "sole readable text allowed" in PROMPT
    assert "AUDIO-ONLY" in PROMPT
    assert "Never render any <d> content as on-screen text" in PROMPT
