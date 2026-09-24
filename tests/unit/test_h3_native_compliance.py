from __future__ import annotations

import re

import pytest

from lib.video_prompt_compilers.h3_prompt_compiler import (
    compile_h3_ref2va_prompt,
    validate_h3_native_ref2va_prompt,
)


CASES = {
    "E4U02": {
        "duration": 15,
        "refs": [("沈知意小房子", "scene"), ("手机", "object"), ("幼年陆念", "character")],
        "text": '''[Shot 1] A close shot inside @[沈知意小房子] frames @[手机] in the foreground. The phone screen displays the alarm label "给念念打电话" clearly while the room remains still.
Sound: A short electronic notification sounds over quiet room tone.
[Shot 2] At 00:05.000
The shot transitions into a memory. A close shot shows @[幼年陆念] holding @[手机] against her cheek while her shoulders tremble.
@[幼年陆念]：{妈妈，我想你。}
Sound: Light phone-line noise and a soft breath.
[Shot 3] At 00:10.000
The memory changes to the same child looking away and handling a small toy beside @[手机].
@[幼年陆念]：{妈妈，我在忙。}
Sound: The phone-line ambience continues softly.''',
    },
    "E11U02": {
        "duration": 15,
        "refs": [
            ("天枢科技研发室", "scene"),
            ("研究员", "character"),
            ("江屿", "character"),
            ("嘉宾证", "object"),
            ("AI峰会媒体区", "scene"),
            ("陆予深", "character"),
            ("苏晚", "character"),
            ("记者", "character"),
        ],
        "text": '''[Shot 1] A close shot inside @[天枢科技研发室] shows @[研究员] reading the passing test result and releasing a held breath.
@[研究员]：{通过了。}
Sound: A brief burst of team cheers and workstation ambience.
[Shot 2] At 00:05.000
The shot cuts to @[江屿] placing @[嘉宾证] beside the workstation in a balanced two-person composition.
@[江屿]：{明天见真章。}
Sound: Quiet office room tone and the light tap of the badge on the desk.
[Shot 3] At 00:10.000
A medium shot establishes @[AI峰会媒体区]. @[陆予深] and @[苏晚] enter while @[记者] turns toward them with a microphone.
@[记者]：{陆氏会合作吗？}
Sound: Camera shutters and low media-area chatter.''',
    },
    "E12U06": {
        "duration": 10,
        "refs": [("AI峰会主屏", "scene"), ("峰会主屏", "object"), ("侧台门", "object")],
        "text": '''[Shot 1] A close shot within @[AI峰会主屏] centers @[峰会主屏]. The error display falls to black and an identity-title loading state begins, but no exact readable identity text is specified.
Sound: A low electronic system tone fades out.
[Shot 2] At 00:05.000
The shot cuts to @[侧台门] as it opens slowly and a stage spotlight rises through the darkened auditorium.
Sound: The hall falls nearly silent before the first applause begins.''',
    },
    "E13U01": {
        "duration": 10,
        "refs": [("AI峰会", "scene"), ("峰会主屏", "object"), ("沈知意", "character")],
        "text": '''[Shot 1] A close shot inside @[AI峰会] centers @[峰会主屏], which displays "沈知意 / 天枢联合创始人·原始架构师" in clear readable type. The off-screen host (S1) announces: <d>[Chinese] 欢迎天枢联合创始人、天枢原始架构师——沈知意女士。</d>
Sound: A clean electronic reveal tone and the first audience reaction.
[Shot 2] At 00:05.000
The shot cuts to a medium view as @[沈知意] enters through the side-stage light and walks toward the center mark at an even pace.
Sound: Audience applause grows across the hall.''',
    },
    "E13U03": {
        "duration": 15,
        "refs": [("学校教室", "scene"), ("陆念", "character"), ("沈知意", "character"), ("控制台", "object"), ("日志屏", "object")],
        "text": '''[Shot 1] A medium shot inside @[学校教室] shows @[陆念] watching the summit livestream and suddenly sitting upright as the reveal reaches the classroom screen.
Sound: Several classmates react with short surprised breaths.
[Shot 2] At 00:05.000
The shot cuts to @[沈知意] seated at @[控制台] on the summit stage. She places both hands near the keyboard and speaks at an even pace.
@[沈知意]：{打开底层日志。}
Sound: Keyboard taps and low control-room ambience.
[Shot 3] At 00:10.000
A close shot centers @[日志屏] as system logs scroll rapidly while @[沈知意] tracks the changing lines with her eyes.
Sound: Soft electronic interface tones and continued keyboard input.''',
    },
    "E15U03": {
        "duration": 15,
        "refs": [("天枢新品发布会", "scene"), ("发布会巨屏", "object"), ("沈知意", "character")],
        "text": '''[Shot 1] A wide shot establishes @[天枢新品发布会] as @[发布会巨屏] displays "TIANSHU NEXT" clearly above the main stage.
Sound: Low audience room tone and a clean stage-system activation sound.
[Shot 2] At 00:05.000
The shot cuts to a medium-wide view of the seated guests and media as camera shutters begin to fire.
Sound: Low crowd movement and scattered camera shutters.
[Shot 3] At 00:10.000
A medium shot shows @[沈知意] walking alone from backstage toward the center of the stage while the camera pushes in with small amplitude at slow speed.
Sound: Applause rises and fills the hall.''',
    },
}


def _compile(unit_id: str) -> str:
    case = CASES[unit_id]
    source_names = [name for name, _kind in case["refs"]]
    kinds = {name: kind for name, kind in case["refs"]}
    return compile_h3_ref2va_prompt(
        source_prompt=case["text"],
        duration_seconds=case["duration"],
        reference_count=len(source_names),
        reference_source_names=source_names,
        options={"reference_kinds": kinds},
    )


@pytest.mark.parametrize("unit_id", list(CASES))
def test_supplier_priority_units_compile_as_strict_native_ref2va(unit_id: str) -> None:
    prompt = _compile(unit_id)
    case = CASES[unit_id]
    assert validate_h3_native_ref2va_prompt(
        prompt,
        duration_seconds=case["duration"],
        reference_count=len(case["refs"]),
    ) == prompt
    assert prompt.startswith("subject_definitions:")
    assert "ARCREEL_H3_VISUAL_FRAME_POLICY" not in prompt
    assert "Visual-frame note:" not in prompt
    assert "[Shot 1] At " not in prompt
    assert prompt.count("subject_definitions:") == 1
    assert prompt.count("summary:") == 1
    assert prompt.count("retention_analysis:") == 1
    assert prompt.count("detailed_description:") == 1
    assert prompt.count("overall_soundscape:") == 1
    assert prompt.count("non_diegetic_music:") == 1


def test_e11u02_exercises_eight_actual_reference_images() -> None:
    prompt = _compile("E11U02")
    for index in range(1, 9):
        assert f"<Picture {index}>" in prompt
        assert f"<Subject {index}>" in prompt
    assert "<Picture 9>" not in prompt
    assert prompt.count("<d>[Chinese]") == 3


def test_e4u02_keeps_alarm_label_visible_but_dialogue_audio_only() -> None:
    prompt = _compile("E4U02")
    assert '"给念念打电话"' in prompt
    assert '"妈妈，我想你。"' not in prompt
    assert '"妈妈，我在忙。"' not in prompt
    assert "<d>[Chinese] 妈妈，我想你。</d>" in prompt
    assert "<d>[Chinese] 妈妈，我在忙。</d>" in prompt


def test_e12u06_does_not_invent_identity_copy() -> None:
    prompt = _compile("E12U06")
    assert "identity-title loading state" in prompt
    assert "沈知意 /" not in prompt


def test_e13u01_preserves_exact_original_language_visible_identity_text() -> None:
    prompt = _compile("E13U01")
    assert '"沈知意 / 天枢联合创始人·原始架构师"' in prompt
    assert "<d>[Chinese] 欢迎天枢联合创始人、天枢原始架构师——沈知意女士。</d>" in prompt


def test_e13u03_dialogue_is_not_promoted_to_visible_text() -> None:
    prompt = _compile("E13U03")
    assert "<d>[Chinese] 打开底层日志。</d>" in prompt
    assert '"打开底层日志。"' not in prompt


def test_e15u03_preserves_latin_screen_text_without_dialogue() -> None:
    prompt = _compile("E15U03")
    assert '"TIANSHU NEXT"' in prompt
    assert "<d>[" not in prompt


def test_no_chinese_execution_prose_escapes_dialogue_or_visible_quotes() -> None:
    cjk = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
    dialogue = re.compile(r"<d>\[[^\]]+\].*?</d>", re.DOTALL)
    quoted = re.compile(r'"[^"\r\n]*"')
    for unit_id in CASES:
        prompt = _compile(unit_id)
        masked = dialogue.sub("", prompt)
        masked = quoted.sub("", masked)
        assert cjk.search(masked) is None, unit_id