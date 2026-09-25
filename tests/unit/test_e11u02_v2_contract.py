import base64
import hashlib

from scripts.experiments.run_e11u02_minimax_h3_v2_live import (
    AUDIO_SEED_PROMPT,
    DIALOGUE_1,
    DIALOGUE_2,
    DIALOGUE_3,
    DURATION_SECONDS,
    FINAL_HEIGHT,
    FINAL_WIDTH,
    MODEL,
    SCENE_BRIDGE_B64,
    SCENE_BRIDGE_SHA256,
    SHOT1_PROMPT,
    SHOT2_PROMPT,
    SHOT3_PROMPT,
    SHOT_SECONDS,
    ZERO_TEXT_AVOID,
    _assert_contracts,
    _has_cjk,
)


def test_e11u02_v2_canonical_structure_is_locked() -> None:
    assert DURATION_SECONDS == 15
    assert SHOT_SECONDS == 5
    assert SHOT_SECONDS * 3 == DURATION_SECONDS
    assert MODEL == "minimax_h3_zm_u24"
    assert DIALOGUE_1 == "通过了"
    assert DIALOGUE_2 == "明天见真章"
    assert DIALOGUE_3 == "陆氏会合作吗"


def test_e11u02_v2_scene_bridge_is_sha_pinned() -> None:
    assert SCENE_BRIDGE_B64.is_file()
    raw = "".join(SCENE_BRIDGE_B64.read_text(encoding="utf-8").split())
    decoded = base64.b64decode(raw, validate=True)
    assert hashlib.sha256(decoded).hexdigest() == SCENE_BRIDGE_SHA256
    assert SCENE_BRIDGE_SHA256 == "90ad97c07213d6d9fe1dee15a676b560055ec30fdcd8f041c42f23a643ac201b"


def test_e11u02_v2_dialogues_exist_only_in_audio_seed() -> None:
    for dialogue in (DIALOGUE_1, DIALOGUE_2, DIALOGUE_3):
        assert f"<d>[Chinese] {dialogue}</d>" in AUDIO_SEED_PROMPT
    for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT):
        assert "<d>" not in prompt
        assert "</d>" not in prompt
        assert DIALOGUE_1 not in prompt
        assert DIALOGUE_2 not in prompt
        assert DIALOGUE_3 not in prompt


def test_e11u02_v2_visual_prompts_are_zero_text_zero_cjk() -> None:
    for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT):
        assert not _has_cjk(prompt)
        assert "ZERO readable text" in prompt
        assert "ZERO glyph-like pseudo-text" in prompt
        assert prompt.rstrip().splitlines()[-1] == ZERO_TEXT_AVOID


def test_e11u02_v2_shot1_removes_screen_ownership() -> None:
    assert "NO-SCREEN FRAMING" in SHOT1_PROMPT
    assert "no visible monitor face" in SHOT1_PROMPT
    assert "physical equipment indicator module" in SHOT1_PROMPT
    assert "steady green luminous ring or bar" in SHOT1_PROMPT
    assert "No characters, numbers, glyphs" in SHOT1_PROMPT


def test_e11u02_v2_shot2_turns_badge_face_down() -> None:
    assert "BADGE BACKSIDE faces camera" in SHOT2_PROMPT
    assert "printed front side always faces the table" in SHOT2_PROMPT
    assert "plain solid cord" in SHOT2_PROMPT
    assert "completely unprinted and unpatterned" in SHOT2_PROMPT
    assert "show hands and forearms only" in SHOT2_PROMPT


def test_e11u02_v2_shot3_uses_black_drape_media_corridor() -> None:
    assert "PLAIN BLACK ACOUSTIC DRAPES" in SHOT3_PROMPT
    assert "No branded wall" in SHOT3_PROMPT
    assert "BLACK-DRAPE CONTRACT" in SHOT3_PROMPT
    assert "no visible event badges" in SHOT3_PROMPT
    assert "camera rear displays are turned away" in SHOT3_PROMPT
    assert "remain rear or three-quarter rear throughout" in SHOT3_PROMPT


def test_e11u02_v2_final_resolution_is_validation_resolution() -> None:
    assert FINAL_WIDTH == 864
    assert FINAL_HEIGHT == 480


def test_e11u02_v2_contract_bundle_passes() -> None:
    _assert_contracts()
