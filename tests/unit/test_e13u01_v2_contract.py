from scripts.experiments.run_e13u01_minimax_h3_v2_live import (
    AUDIO_SEED_PROMPT,
    BRIDGE_SHA256,
    CHARACTER_ID,
    CHARACTER_NAME,
    DURATION_SECONDS,
    ENTRY_FINAL_AVOID_LINE,
    ENTRY_PROMPT,
    HOST_DIALOGUE,
    SHOT_SECONDS,
    VISIBLE_TEXT_NAME,
    VISIBLE_TEXT_TITLE,
    _decode_bridge,
    _sha256,
)


def test_e13u01_v2_canonical_facts_are_locked() -> None:
    assert CHARACTER_ID == "C01"
    assert CHARACTER_NAME == "沈知意"
    assert VISIBLE_TEXT_NAME == "沈知意"
    assert VISIBLE_TEXT_TITLE == "天枢联合创始人"
    assert HOST_DIALOGUE == "欢迎沈知意"
    assert DURATION_SECONDS == 10
    assert SHOT_SECONDS == 5
    assert BRIDGE_SHA256 == "fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135"


def test_e13u01_v2_provider_prompt_contains_no_cjk_visual_text_source() -> None:
    assert not any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in ENTRY_PROMPT
    )
    assert VISIBLE_TEXT_NAME not in ENTRY_PROMPT
    assert VISIBLE_TEXT_TITLE not in ENTRY_PROMPT
    assert HOST_DIALOGUE not in ENTRY_PROMPT


def test_e13u01_v2_dialogue_is_detached_from_h3_visual_prompt() -> None:
    assert "<d>" not in ENTRY_PROMPT
    assert "</d>" not in ENTRY_PROMPT
    assert f"<d>[Chinese] {HOST_DIALOGUE}</d>" in AUDIO_SEED_PROMPT
    assert "visual generation only" in ENTRY_PROMPT


def test_e13u01_v2_h3_only_owns_shot2_entrance() -> None:
    assert "VERY FIRST FRAME" in ENTRY_PROMPT
    assert "already visibly crossing" in ENTRY_PROMPT
    assert "By 00:01 she is fully through" in ENTRY_PROMPT
    assert "main LED screen is completely outside frame" in ENTRY_PROMPT
    assert "camera never pans to the LED screen" in ENTRY_PROMPT


def test_e13u01_v2_shot2_has_zero_readable_text_contract() -> None:
    assert "ZERO readable text" in ENTRY_PROMPT
    assert "No Chinese, English, numbers" in ENTRY_PROMPT
    assert "exit sign" in ENTRY_PROMPT
    assert ENTRY_PROMPT.rstrip().splitlines()[-1] == ENTRY_FINAL_AVOID_LINE


def test_e13u01_v2_c01_identity_contract_is_explicit() -> None:
    assert "canonical C01" in ENTRY_PROMPT
    assert "exact face topology" in ENTRY_PROMPT
    assert "No generic businesswoman" in ENTRY_PROMPT
    assert "No face substitution" in ENTRY_PROMPT


def test_e13u01_v2_e12_continuity_is_explicit() -> None:
    assert "accepted final stage-wing geometry from the preceding unit" in ENTRY_PROMPT
    assert "already-open side door directly attached to the immediate stage edge" in ENTRY_PROMPT
    assert "short threshold" in ENTRY_PROMPT
    assert "white spotlight" in ENTRY_PROMPT
    assert "Do not create a corridor" in ENTRY_PROMPT


def test_e13u01_v2_final_timeline_is_deterministic_two_by_five_seconds() -> None:
    assert SHOT_SECONDS * 2 == DURATION_SECONDS


def test_e13u01_v2_bridge_chunks_decode_to_pinned_source(tmp_path) -> None:
    target = tmp_path / "bridge.jpg"
    _decode_bridge(target)
    assert target.is_file()
    assert _sha256(target) == BRIDGE_SHA256


def test_e13u01_v2_does_not_delegate_exact_screen_typography_to_h3() -> None:
    lowered = ENTRY_PROMPT.lower()
    assert "screen strings" not in lowered
    assert "giant summit screen" not in lowered
    assert "led screen is completely outside frame" in lowered
