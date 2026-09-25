import base64
import hashlib

from scripts.experiments.run_e11u02_minimax_h3_live import (
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


def test_e11u02_canonical_structure_is_locked() -> None:
    assert DURATION_SECONDS == 15
    assert SHOT_SECONDS == 5
    assert SHOT_SECONDS * 3 == DURATION_SECONDS
    assert MODEL == "minimax_h3_zm_u24"
    assert DIALOGUE_1 == "通过了"
    assert DIALOGUE_2 == "明天见真章"
    assert DIALOGUE_3 == "陆氏会合作吗"


def test_e11u02_scene_bridge_is_sha_pinned() -> None:
    assert SCENE_BRIDGE_B64.is_file()
    raw = "".join(SCENE_BRIDGE_B64.read_text(encoding="utf-8").split())
    decoded = base64.b64decode(raw, validate=True)
    assert hashlib.sha256(decoded).hexdigest() == SCENE_BRIDGE_SHA256
    assert SCENE_BRIDGE_SHA256 == "90ad97c07213d6d9fe1dee15a676b560055ec30fdcd8f041c42f23a643ac201b"


def test_e11u02_dialogues_exist_only_in_audio_seed() -> None:
    for dialogue in (DIALOGUE_1, DIALOGUE_2, DIALOGUE_3):
        assert f"<d>[Chinese] {dialogue}</d>" in AUDIO_SEED_PROMPT
    for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT):
        assert "<d>" not in prompt
        assert "</d>" not in prompt
        assert DIALOGUE_1 not in prompt
        assert DIALOGUE_2 not in prompt
        assert DIALOGUE_3 not in prompt


def test_e11u02_visual_prompts_are_zero_text_zero_cjk() -> None:
    for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT):
        assert not _has_cjk(prompt)
        assert "ZERO readable text" in prompt
        assert prompt.rstrip().splitlines()[-1] == ZERO_TEXT_AVOID


def test_e11u02_shot1_uses_semantic_stability_not_literal_ui_copy() -> None:
    assert "steady green geometric status bar" in SHOT1_PROMPT
    assert "smooth abstract waveform" in SHOT1_PROMPT
    assert "without any literal system message" in SHOT1_PROMPT
    assert "no named principal face is shown close enough" in SHOT1_PROMPT.lower()


def test_e11u02_shot2_is_identity_safe_and_badge_is_blank() -> None:
    assert "show hands/forearms only" in SHOT2_PROMPT
    assert "No faces, no heads, no facial reflections" in SHOT2_PROMPT
    assert "formal summit guest badge" in SHOT2_PROMPT
    assert "blank matte material" in SHOT2_PROMPT
    assert "ZERO readable text on the badge" in SHOT2_PROMPT


def test_e11u02_shot3_avoids_inventing_c02_c04_faces() -> None:
    assert "rear or three-quarter rear throughout" in SHOT3_PROMPT
    assert "Do not create front-facing portrait identities" in SHOT3_PROMPT
    assert "graphite-to-deep-navy business suit" in SHOT3_PROMPT
    assert "warm ivory/champagne tailored outfit" in SHOT3_PROMPT
    assert "small business handbag" in SHOT3_PROMPT


def test_e11u02_shot3_preserves_media_entry_action() -> None:
    assert "summit media-entry plate" in SHOT3_PROMPT
    assert "restrained lateral camera move" in SHOT3_PROMPT
    assert "Reporters raise cameras" in SHOT3_PROMPT
    assert "flash bursts" in SHOT3_PROMPT


def test_e11u02_final_resolution_is_validation_resolution() -> None:
    assert FINAL_WIDTH == 864
    assert FINAL_HEIGHT == 480


def test_e11u02_contract_bundle_passes() -> None:
    _assert_contracts()
