from scripts.experiments.run_e13u03_minimax_h3_live import (
    AUDIO_SEED_PROMPT,
    C01_BRIDGE_SHA256,
    C01_ID,
    C03_ID,
    C03_REF_SHA256,
    DIALOGUE,
    DURATION_SECONDS,
    FINAL_HEIGHT,
    FINAL_WIDTH,
    MODEL,
    SCENE_BRIDGE_SHA256,
    SHOT1_PROMPT,
    SHOT2_PROMPT,
    SHOT3_PROMPT,
    SHOT_SECONDS,
    ZERO_TEXT_AVOID,
    _assert_contracts,
    _sha256,
    C03_REF,
    SCENE_BRIDGE,
)


def _has_cjk(value: str) -> bool:
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in value
    )


def test_e13u03_canonical_structure_is_locked() -> None:
    assert DURATION_SECONDS == 15
    assert SHOT_SECONDS == 5
    assert SHOT_SECONDS * 3 == DURATION_SECONDS
    assert MODEL == "minimax_h3_zm_u24"
    assert C01_ID == "C01"
    assert C03_ID == "C03"
    assert DIALOGUE == "打开底层日志"


def test_e13u03_source_assets_are_sha_pinned() -> None:
    assert SCENE_BRIDGE_SHA256 == "2221bc97ca6fcc6249021f45b93f1e6107b8c9b02115a179856685dc01bfec67"
    assert C03_REF_SHA256 == "c92b71c3fe707088dd340d41de9a202e2ab7d02392fef4913b2df6959c4932b0"
    assert C01_BRIDGE_SHA256 == "fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135"
    assert SCENE_BRIDGE.is_file()
    assert C03_REF.is_file()
    assert _sha256(SCENE_BRIDGE) == SCENE_BRIDGE_SHA256
    assert _sha256(C03_REF) == C03_REF_SHA256


def test_e13u03_dialogue_exists_only_in_audio_seed() -> None:
    assert f"<d>[Chinese] {DIALOGUE}</d>" in AUDIO_SEED_PROMPT
    for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT):
        assert DIALOGUE not in prompt
        assert "<d>" not in prompt
        assert "</d>" not in prompt


def test_e13u03_visual_prompts_have_zero_cjk_source_text() -> None:
    for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT):
        assert not _has_cjk(prompt)
        assert "ZERO readable text" in prompt
        assert prompt.rstrip().splitlines()[-1] == ZERO_TEXT_AVOID


def test_e13u03_shot1_locks_school_and_c03_reaction() -> None:
    assert "school technology classroom" in SHOT1_PROMPT
    assert "canonical C03" in SHOT1_PROMPT
    assert "suddenly straightens her back and sits upright" in SHOT1_PROMPT
    assert "slow push-in" in SHOT1_PROMPT.lower()
    assert "projector feed is defocused and non-linguistic" in SHOT1_PROMPT


def test_e13u03_shot2_locks_c01_console_operation() -> None:
    assert "canonical C01" in SHOT2_PROMPT
    assert "malfunctioning control console" in SHOT2_PROMPT
    assert "By 00:01.5 she reaches it" in SHOT2_PROMPT
    assert "begins typing" in SHOT2_PROMPT
    assert "No recast, face substitution" in SHOT2_PROMPT


def test_e13u03_shot3_uses_semantic_only_log_geometry() -> None:
    assert "Canonical provides NO literal log strings" in SHOT3_PROMPT
    assert "horizontal luminous bars" in SHOT3_PROMPT
    assert "Do not invent code or text" in SHOT3_PROMPT
    assert "ZERO readable or glyph-like text" in SHOT3_PROMPT


def test_e13u03_final_resolution_is_validation_resolution() -> None:
    assert FINAL_WIDTH == 864
    assert FINAL_HEIGHT == 480


def test_e13u03_contract_bundle_passes() -> None:
    _assert_contracts()


def test_e13u03_no_visual_prompt_invents_canonical_text() -> None:
    assert "root access" not in SHOT3_PROMPT.lower()
    assert "model core" not in SHOT3_PROMPT.lower()
    assert "error layer" not in SHOT3_PROMPT.lower()
    assert "third layer" not in SHOT3_PROMPT.lower()
