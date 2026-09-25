from scripts.experiments.run_e13u01_minimax_h3_live import (
    AUDIO_SEED_PROMPT,
    BRIDGE_SHA256,
    CHARACTER_ID,
    CHARACTER_NAME,
    FINAL_AVOID_LINE,
    FINAL_PROMPT,
    HOST_DIALOGUE,
    VISIBLE_TEXT_NAME,
    VISIBLE_TEXT_TITLE,
)


def test_e13u01_canonical_facts_are_locked() -> None:
    assert CHARACTER_ID == "C01"
    assert CHARACTER_NAME == "沈知意"
    assert VISIBLE_TEXT_NAME == "沈知意"
    assert VISIBLE_TEXT_TITLE == "天枢联合创始人"
    assert HOST_DIALOGUE == "欢迎沈知意"
    assert BRIDGE_SHA256 == "156f4429ec41493f5445dcfeadba9989b626413bc666d62291f3b026b70ec7b1"


def test_e13u01_audio_seed_owns_dialogue() -> None:
    assert f"<d>[Chinese] {HOST_DIALOGUE}</d>" in AUDIO_SEED_PROMPT
    assert "off-screen female summit host" in AUDIO_SEED_PROMPT
    assert "No non-diegetic music" in AUDIO_SEED_PROMPT


def test_e13u01_final_visual_prompt_has_no_dialogue_transcript() -> None:
    assert "<d>" not in FINAL_PROMPT
    assert "</d>" not in FINAL_PROMPT
    assert HOST_DIALOGUE not in FINAL_PROMPT
    assert "<Audio 1>" in FINAL_PROMPT
    assert "AUDIO/TEXT SEPARATION" in FINAL_PROMPT


def test_e13u01_visible_text_whitelist_is_exact() -> None:
    # The final visual prompt intentionally contains Chinese only for the two canonical screen strings.
    cjk_runs = set()
    current = []
    for char in FINAL_PROMPT:
        is_cjk = "\u3400" <= char <= "\u4dbf" or "\u4e00" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff"
        if is_cjk:
            current.append(char)
        elif current:
            cjk_runs.add("".join(current))
            current = []
    if current:
        cjk_runs.add("".join(current))
    assert cjk_runs == {VISIBLE_TEXT_NAME, VISIBLE_TEXT_TITLE}


def test_e13u01_e12_continuity_is_explicit_physical_geometry() -> None:
    assert "accepted E12U06 final spatial state" in FINAL_PROMPT
    assert "open side door remains directly attached to the stage wing at the immediate stage edge" in FINAL_PROMPT
    assert "threshold connects directly to the stage floor" in FINAL_PROMPT
    assert "Do not create a long backstage corridor" in FINAL_PROMPT


def test_e13u01_c01_identity_lock_is_explicit() -> None:
    assert "canonical C01 沈知意" in FINAL_PROMPT
    assert "exact face identity and white professional suit" in FINAL_PROMPT
    assert "No generic businesswoman" in FINAL_PROMPT
    assert "no face drift" in FINAL_PROMPT


def test_e13u01_timeline_is_exactly_two_five_second_shots() -> None:
    assert "[Shot 1] 00:00-00:05." in FINAL_PROMPT
    assert "[Shot 2] 00:05-00:10." in FINAL_PROMPT
    assert "exactly two authored 5-second shots" in FINAL_PROMPT


def test_e13u01_final_avoid_line_is_last() -> None:
    assert FINAL_PROMPT.rstrip().splitlines()[-1] == FINAL_AVOID_LINE
