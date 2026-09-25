from scripts.experiments.run_e11u02_minimax_h3_v4_live import (
    C04_ANCHOR,
    C04_ANCHOR_SHA256,
    DURATION_SECONDS,
    FINAL_HEIGHT,
    FINAL_WIDTH,
    MODEL,
    REPORTER_DIALOGUE,
    REPAIR_VERSION,
    SHOT3_PROMPT,
    SHOT_SECONDS,
    V2_SOURCE_RUN_ID,
    V3_SOURCE_RUN_ID,
    ZERO_TEXT_AVOID,
    _assert_prompt_contract,
    _has_cjk,
    _sha256,
)


def test_e11u02_v4_structure_is_locked() -> None:
    assert REPAIR_VERSION == "v4_targeted_shot3_c04_rear_identity_lock"
    assert DURATION_SECONDS == 15
    assert SHOT_SECONDS == 5
    assert SHOT_SECONDS * 3 == DURATION_SECONDS
    assert FINAL_WIDTH == 864
    assert FINAL_HEIGHT == 480
    assert MODEL == "minimax_h3_zm_u24"
    assert V2_SOURCE_RUN_ID == 36148270693
    assert V3_SOURCE_RUN_ID == 36160563284


def test_e11u02_v4_c04_anchor_is_sha_pinned() -> None:
    assert C04_ANCHOR.is_file()
    assert _sha256(C04_ANCHOR) == C04_ANCHOR_SHA256
    assert C04_ANCHOR_SHA256 == "1a6f50d353c0620f693c89f42a8128400877e1629e3a0ee97f7008a60021e6be"


def test_e11u02_v4_dialogue_is_detached() -> None:
    assert REPORTER_DIALOGUE == "陆氏会合作吗"
    assert REPORTER_DIALOGUE not in SHOT3_PROMPT
    assert "<d>" not in SHOT3_PROMPT
    assert "</d>" not in SHOT3_PROMPT


def test_e11u02_v4_visual_prompt_has_zero_cjk() -> None:
    assert not _has_cjk(SHOT3_PROMPT)


def test_e11u02_v4_locks_c04_rear_identity() -> None:
    assert "canonical C04 Su Wan" in SHOT3_PROMPT
    assert "long DARK-BROWN WAVY HAIR" in SHOT3_PROMPT
    assert "warm ivory/cream professional upper" in SHOT3_PROMPT
    assert "light camel/champagne tailored trousers" in SHOT3_PROMPT
    assert "No blonde hair" in SHOT3_PROMPT
    assert "No alternate actress" in SHOT3_PROMPT
    assert "No face substitution" in SHOT3_PROMPT


def test_e11u02_v4_keeps_c02_identity_safe() -> None:
    assert "C02 SAFETY CONTRACT" in SHOT3_PROMPT
    assert "rear or three-quarter rear" in SHOT3_PROMPT
    assert "never create a front-facing portrait face" in SHOT3_PROMPT


def test_e11u02_v4_removes_text_surfaces_from_media_corridor() -> None:
    assert "BLACK-DRAPE CONTRACT" in SHOT3_PROMPT
    assert "No sponsor wall" in SHOT3_PROMPT
    assert "No sponsor wall, event title, projection, LED panel" in SHOT3_PROMPT
    assert "camera rear displays face away" in SHOT3_PROMPT
    assert "ZERO readable text" in SHOT3_PROMPT
    assert "ZERO glyph-like pseudo-text" in SHOT3_PROMPT
    assert SHOT3_PROMPT.rstrip().splitlines()[-1] == ZERO_TEXT_AVOID


def test_e11u02_v4_preserves_canonical_media_entry_action() -> None:
    assert "enter together" in SHOT3_PROMPT
    assert "restrained lateral follow" in SHOT3_PROMPT
    assert "Reporters on both sides raise cameras" in SHOT3_PROMPT
    assert "flash bursts" in SHOT3_PROMPT
    assert "do not stop and do not answer" in SHOT3_PROMPT


def test_e11u02_v4_prompt_contract_passes() -> None:
    _assert_prompt_contract()
