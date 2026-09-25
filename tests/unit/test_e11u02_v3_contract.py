from scripts.experiments.run_e11u02_minimax_h3_v3_live import (
    DIALOGUES,
    DURATION_SECONDS,
    FINAL_HEIGHT,
    FINAL_WIDTH,
    MODEL,
    REPAIR_VERSION,
    SHOT2_PROMPT,
    SHOT_SECONDS,
    V2_SOURCE_RUN_ID,
    ZERO_TEXT_AVOID,
    _assert_prompt_contract,
    _has_cjk,
)


def test_e11u02_v3_structure_is_locked() -> None:
    assert REPAIR_VERSION == "v3_targeted_shot2_semantic_neutral_blank_token"
    assert DURATION_SECONDS == 15
    assert SHOT_SECONDS == 5
    assert SHOT_SECONDS * 3 == DURATION_SECONDS
    assert FINAL_WIDTH == 864
    assert FINAL_HEIGHT == 480
    assert MODEL == "minimax_h3_zm_u24"
    assert V2_SOURCE_RUN_ID == 36148270693


def test_e11u02_v3_dialogue_is_detached() -> None:
    assert "<d>" not in SHOT2_PROMPT
    assert "</d>" not in SHOT2_PROMPT
    for dialogue in DIALOGUES:
        assert dialogue not in SHOT2_PROMPT


def test_e11u02_v3_visual_prompt_has_zero_cjk() -> None:
    assert not _has_cjk(SHOT2_PROMPT)


def test_e11u02_v3_removes_text_bearing_semantic_triggers() -> None:
    lower = SHOT2_PROMPT.lower()
    for token in (
        "badge",
        "credential",
        "summit",
        "guest pass",
        "identity card",
        "name card",
        "lanyard",
    ):
        assert token not in lower


def test_e11u02_v3_object_is_featureless_and_uniform() -> None:
    assert "completely featureless matte rectangular polymer token" in SHOT2_PROMPT
    assert "uniform soft gray" in SHOT2_PROMPT
    assert "No blue patch" in SHOT2_PROMPT
    assert "plain black solid cord only" in SHOT2_PROMPT
    assert "No blue patch, no colored panel, no graphic" in SHOT2_PROMPT


def test_e11u02_v3_excludes_text_bearing_surfaces() -> None:
    assert "NO-SCREEN CONTRACT" in SHOT2_PROMPT
    assert "no monitor, laptop, tablet, phone screen" in SHOT2_PROMPT
    assert "ZERO readable text" in SHOT2_PROMPT
    assert "ZERO glyph-like pseudo-text" in SHOT2_PROMPT
    assert SHOT2_PROMPT.rstrip().splitlines()[-1] == ZERO_TEXT_AVOID


def test_e11u02_v3_keeps_identity_safe_framing() -> None:
    assert "show hands and forearms only" in SHOT2_PROMPT
    assert "No face, head, facial reflection" in SHOT2_PROMPT


def test_e11u02_v3_prompt_contract_passes() -> None:
    _assert_prompt_contract()
