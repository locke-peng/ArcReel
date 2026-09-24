from __future__ import annotations

import re

from lib.video_prompt_compilers.h3_prompt_compiler import (
    compile_h3_ref2va_prompt,
    validate_h3_native_ref2va_prompt,
)


E4U02_SOURCE = """[Shot 1] A close shot inside @[沈知意小房子] frames @[手机] in the foreground. The phone screen displays the alarm label "给念念打电话" clearly while the room remains still.
Sound: A short electronic notification sounds over quiet room tone.
[Shot 2] At 00:05.000
The shot transitions into a memory. A close shot shows @[幼年陆念] holding @[手机] against her cheek while her shoulders tremble.
@[幼年陆念]：{妈妈，我想你。}
Sound: Light phone-line noise and a soft breath.
[Shot 3] At 00:10.000
The memory changes to the same child looking away and handling a small toy beside @[手机].
@[幼年陆念]：{妈妈，我在忙。}
Sound: The phone-line ambience continues softly."""


def _compile_e4u02() -> str:
    prompt = compile_h3_ref2va_prompt(
        source_prompt=E4U02_SOURCE,
        duration_seconds=15,
        reference_count=3,
        reference_source_names=["沈知意小房子", "手机", "幼年陆念"],
        options={
            "reference_kinds": {
                "沈知意小房子": "scene",
                "手机": "object",
                "幼年陆念": "character",
            }
        },
    )
    return validate_h3_native_ref2va_prompt(
        prompt,
        duration_seconds=15,
        reference_count=3,
    )


def test_e4u02_v2_phone_ui_has_exactly_one_legal_cjk_visible_literal() -> None:
    prompt = _compile_e4u02()
    without_dialogue = re.sub(r"<d>\[[^\]]+\].*?</d>", "", prompt, flags=re.DOTALL)
    cjk_quoted = [
        match.group(0)
        for match in re.finditer(r'"[^"\r\n]*"', without_dialogue)
        if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", match.group(0))
    ]
    assert cjk_quoted == ['"给念念打电话"']
    assert prompt.count('"给念念打电话"') == 1
    assert (
        "Readable on-screen text is limited strictly to the exact quoted scene-text literals "
        "explicitly specified in the shots."
    ) in prompt
    assert (
        "Do not create any additional readable letters, numbers, captions, subtitles, dialogue "
        "transcription, chat bubbles, badges, timestamps, watermarks, or UI copy."
    ) in prompt


def test_e4u02_v2_dialogue_exists_only_as_audio_not_visible_text() -> None:
    prompt = _compile_e4u02()
    assert "<d>[Chinese] 妈妈，我想你。</d>" in prompt
    assert "<d>[Chinese] 妈妈，我在忙。</d>" in prompt

    without_dialogue = re.sub(r"<d>\[[^\]]+\].*?</d>", "", prompt, flags=re.DOTALL)
    assert "妈妈，我想你。" not in without_dialogue
    assert "妈妈，我在忙。" not in without_dialogue
    assert '"妈妈，我想你。"' not in prompt
    assert '"妈妈，我在忙。"' not in prompt

    assert (
        "All <d> dialogue is spoken audio only. Never render, caption, subtitle, transcribe, quote, "
        "or otherwise display any <d> content as visible text, overlays, speech bubbles, or UI text."
    ) in prompt
    assert prompt.count(
        "The <d> line is spoken audio only and must never appear as subtitles, captions, "
        "on-screen transcription, speech bubbles, UI text, or any other visible text."
    ) == 2


def test_e4u02_v2_stays_in_native_h3_six_section_contract() -> None:
    prompt = _compile_e4u02()
    assert "ARCREEL_H3_VISIBLE_TEXT_GUARD" not in prompt
    assert "ARCREEL_H3_VISUAL_FRAME_POLICY" not in prompt
    assert prompt.count("subject_definitions:") == 1
    assert prompt.count("summary:") == 1
    assert prompt.count("retention_analysis:") == 1
    assert prompt.count("detailed_description:") == 1
    assert prompt.count("overall_soundscape:") == 1
    assert prompt.count("non_diegetic_music:") == 1
