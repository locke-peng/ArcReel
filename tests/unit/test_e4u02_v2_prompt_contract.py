from scripts.experiments.run_e4u02_minimax_h3_live import (
    DIALOGUE_1,
    DIALOGUE_2,
    ONLY_VISIBLE_TEXT,
    PROMPT,
)


def test_e4u02_v2_only_visible_text_contract_is_explicit() -> None:
    assert ONLY_VISIBLE_TEXT == "给念念打电话"
    assert PROMPT.count(ONLY_VISIBLE_TEXT) >= 4
    assert "sole readable text allowed" in PROMPT
    assert "only readable text permitted" in PROMPT
    assert "no readable time digits" in PROMPT
    assert "Every other visible surface must be text-free" in PROMPT


def test_e4u02_v2_dialogue_is_audio_only_and_never_subtitle() -> None:
    assert f"<d>[Chinese] {DIALOGUE_1}</d>" in PROMPT
    assert f"<d>[Chinese] {DIALOGUE_2}</d>" in PROMPT
    assert "Dialogue enclosed by <d> is AUDIO-ONLY" in PROMPT
    assert "Never render any <d> content as on-screen text" in PROMPT
    assert "subtitle" in PROMPT.lower()
    assert "forbidden from appearing visually" in PROMPT


def test_e4u02_v2_dialogue_text_is_not_the_visible_text_allowlist() -> None:
    assert DIALOGUE_1 != ONLY_VISIBLE_TEXT
    assert DIALOGUE_2 != ONLY_VISIBLE_TEXT
