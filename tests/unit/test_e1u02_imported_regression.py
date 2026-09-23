from __future__ import annotations

from dataclasses import dataclass

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.speech_artifact_provenance import project_subtitle_utterances
from lib.speech_composition import admit_script_unit
from lib.speech_presentation import (
    MechanicalSubtitleTiming,
    video_unit_subtitle_timing,
)

E1U02_TEXT = """[Shot 1]
@[陆家别墅]门廊，暖黄壁灯。中景、构图门廊居中、35mm浅景深，镜头固定。@[周姨]从门内右侧走出，双手在围裙上擦一下，身体前倾约10度、眼睁大2mm、嘴唇微张。
@[周姨]：{太太，您怎么来了}
声音：夜风、行李轮停。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图双人、35mm，镜头轻微右摇约5度、慢速。@[沈知意]把拉杆前推10cm递出，视线越过周姨扫向门内、眼睑上抬1mm。
@[沈知意]：{念念呢}
声音：门厅声、脚步。

【转场】硬切

[Shot 3] At 00:10.000
@[陆家别墅]二楼走廊，暖黄壁灯。中景、构图门框居中、机位略低、35mm，镜头缓慢推近约0.3米、慢速。@[沈知意]右手推门（门板转约30度），看见@[陆念]趴在矮桌前串@[贝壳项链]、眉心微蹙2mm。
@[沈知意]：{念念}
声音：门轴轻响、贝壳碰撞。"""

E1U02_UNIT = {
    "unit_id": "E1U02",
    "duration_seconds": 15,
    "text": E1U02_TEXT,
}


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def _entries() -> list[Entry]:
    return [
        Entry(Ref("scene", "陆家别墅")),
        Entry(Ref("character", "周姨")),
        Entry(Ref("character", "沈知意")),
        Entry(Ref("character", "陆念")),
        Entry(Ref("prop", "贝壳项链")),
    ]


def test_imported_e1u02_h3_compilation_keeps_shots_dialogue_and_blocks_visible_control_text() -> None:
    result = compile_reference_video_provider_prompt(
        source_prompt=E1U02_TEXT,
        fallback_prompt="legacy rendered prompt with Avoid: BGM、文字字幕、水印",
        model_name="MiniMax-H3",
        duration_seconds=15,
        request_assets=_entries(),
        payload={"prompt_compiler": "auto"},
        unit_id="E1U02",
    )
    prompt = result.provider_prompt

    assert result.compiler_applied is True
    assert result.generation_mode == "ref2va"
    assert prompt.count("ARCREEL_H3_VISIBLE_TEXT_GUARD:") == 1
    assert "Never render any of them as visible text." in prompt
    assert "Never render dialogue as subtitles, captions" in prompt
    assert 'Visible text is allowed only when a shot explicitly instructs: render exactly "' in prompt

    assert "[Shot 1] [Shot 1]" not in prompt
    shot1 = prompt.index("[Shot 1]")
    first_dialogue = prompt.index("<d>[Chinese] 太太，您怎么来了</d>")
    shot2 = prompt.index("[Shot 2] At 00:05.000")
    second_dialogue = prompt.index("<d>[Chinese] 念念呢</d>")
    shot3 = prompt.index("[Shot 3] At 00:10.000")
    third_dialogue = prompt.index("<d>[Chinese] 念念</d>")
    assert shot1 < first_dialogue < shot2 < second_dialogue < shot3 < third_dialogue

    for index in range(1, 6):
        assert f"<Subject {index}>" in prompt


def test_imported_e1u02_reproduces_old_whole_clip_mechanical_subtitle_bug() -> None:
    admission = admit_script_unit("video_units", E1U02_UNIT)
    assert admission.allowed is True
    utterances = project_subtitle_utterances(admission.preparation)

    old = MechanicalSubtitleTiming().distribute(
        utterances,
        boundary_microseconds=15_083_333,
    )
    assert [(cue.start_microseconds, cue.duration_microseconds, cue.text) for cue in old] == [
        (0, 9_282_051, "太太，您怎么来了"),
        (9_282_051, 3_480_769, "念念呢"),
        (12_762_820, 2_320_513, "念念"),
    ]
    # The old first cue crosses the authored Shot 2 boundary (~5.028s in the real media).
    assert old[0].end_microseconds > 5_027_777


def test_imported_e1u02_shot_aware_subtitles_stay_inside_authored_shot_windows() -> None:
    admission = admit_script_unit("video_units", E1U02_UNIT)
    assert admission.allowed is True
    utterances = project_subtitle_utterances(admission.preparation)

    timing = video_unit_subtitle_timing(E1U02_UNIT, admission.preparation)
    cues = timing.distribute(
        utterances,
        boundary_microseconds=15_083_333,
    )

    assert timing.basis_identity["kind"] == "mechanical-shot-window-text-length"
    assert [(cue.start_microseconds, cue.duration_microseconds, cue.text) for cue in cues] == [
        (0, 5_027_777, "太太，您怎么来了"),
        (5_027_777, 5_027_778, "念念呢"),
        (10_055_555, 5_027_778, "念念"),
    ]
    assert cues[0].end_microseconds == cues[1].start_microseconds
    assert cues[1].end_microseconds == cues[2].start_microseconds
    assert cues[2].end_microseconds == 15_083_333


def test_video_unit_without_authored_shot_timestamps_keeps_legacy_timing_policy() -> None:
    legacy = {
        "unit_id": "E1U99",
        "duration_seconds": 15,
        "text": "@[周姨]：{第一句}\n@[沈知意]：{第二句}",
    }
    admission = admit_script_unit("video_units", legacy)
    timing = video_unit_subtitle_timing(legacy, admission.preparation)
    assert timing.basis_identity == {"kind": "mechanical-text-length", "version": 1}
