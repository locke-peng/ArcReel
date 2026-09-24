from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


UNITS = {
    "E2U05": {
        "duration": 15,
        "dialogues": 0,
        "text": """[Shot 1]
@[餐厅]内，中景、构图靠窗、35mm，镜头缓慢推近约0.3米、慢速。落地玻璃后@[陆予深]、@[陆念]、@[苏晚]三人围桌而坐。
声音：餐厅音乐。

【转场】硬切

[Shot 2] At 00:05.000
近景、构图双人、50mm，镜头固定。@[苏晚]叉甜点递到@[陆念]嘴边，@[陆予深]给她夹菜、三人笑。
声音：笑声。

【转场】硬切

[Shot 3] At 00:10.000
@[餐厅]外玻璃，特写、构图居中、50mm，镜头缓慢推近约0.2米、慢速。玻璃映出@[沈知意]的脸，她盯着窗内@[陆予深]的笑、眼睑缓慢下移、喉结轻滚。
声音：低频氛围。""",
    },
    "E7U06": {
        "duration": 10,
        "dialogues": 2,
        "text": """[Shot 1]
@[酒店]外，中景、构图双人、35mm，镜头固定。@[陆念]扑进@[苏晚]怀里、举着@[贝壳项链]。
@[陆念]：{苏阿姨生日快乐}
声音：笑声。

【转场】硬切

[Shot 2] At 00:05.000
@[酒店]外，特写、构图居中、50mm，镜头缓慢推近约0.2米、慢速。@[陆予深]出现，女儿仰头催。
@[陆念]：{爸爸，你的呢}
声音：低频。""",
    },
    "E11U02": {
        "duration": 15,
        "dialogues": 3,
        "text": """[Shot 1]
@[天枢科技]研发室，近景、构图居中、50mm，镜头固定。年轻@[研究员]看通过结果、松一口气。
@[研究员]：{通过了}
声音：欢呼。

【转场】硬切

[Shot 2] At 00:05.000
近景、构图双人、50mm，镜头固定。@[江屿]把正式@[嘉宾证]放到她手边。
@[江屿]：{明天见真章}
声音：室内声。

【转场】硬切

[Shot 3] At 00:10.000
@[AI峰会]媒体区，中景、构图纵深、35mm，镜头轻微平移。@[陆予深]和@[苏晚]入场。
@[记者]：{陆氏会合作吗}
声音：闪光灯。""",
    },
    "E13U01": {
        "duration": 10,
        "dialogues": 1,
        "text": """[Shot 1]
@[AI峰会]主屏，特写屏幕、构图居中、50mm，镜头固定。黑底逐行出现"@[沈知意] / 天枢科技联合创始人"。
@[主持人]：{欢迎天枢科技联合创始人、天枢原始核心架构设计者——沈知意女士}
声音：电子音。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图居中、35mm，镜头缓慢推近约0.4米、慢速。侧台门打开，@[沈知意]走入追光、步伐平稳。
声音：掌声渐起。""",
    },
    "E14U03": {
        "duration": 15,
        "dialogues": 1,
        "text": """[Shot 1]
@[学校教室]，近景、构图居中、50mm，镜头固定。@[陆念]盯@[手机]未接通界面。
@[陆念]：{妈妈怎么不接}
声音：教室声。

【转场】淡入淡出

[Shot 2] At 00:05.000
@[陆家别墅]卧室，中景、构图居中、35mm，镜头轻微平移。夜里@[陆予深]推门进空房、开灯。
声音：门声。

【转场】硬切

[Shot 3] At 00:10.000
特写屏幕、构图居中、50mm，镜头固定。他再次拨她电话。
声音：电话提示"暂时无法接通"。""",
    },
    "E15U03": {
        "duration": 15,
        "dialogues": 0,
        "text": """[Shot 1]
@[天枢新品发布会]会场，远景、构图纵深、35mm，镜头缓慢拉远。巨屏亮起"TIANSHU NEXT"。
声音：电子音乐。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图纵深、35mm，镜头轻微平移。嘉宾与媒体坐满会场。
声音：人群声。

【转场】硬切

[Shot 3] At 00:10.000
中景、构图居中、35mm，镜头缓慢推近约0.4米、慢速。@[沈知意]独自从后台走上主舞台。
声音：掌声。""",
    },
}


def _reference_entries(text: str) -> list[Entry]:
    seen: list[str] = []
    for name in re.findall(r"@\[([^\]]+)\]", text):
        if name not in seen:
            seen.append(name)
    return [Entry(Ref("unknown", name)) for name in seen]


@pytest.mark.parametrize("unit_id", list(UNITS))
def test_representative_project_units_compile_with_stable_shots_and_dialogue_policy(unit_id: str) -> None:
    case = UNITS[unit_id]
    text = str(case["text"])
    entries = _reference_entries(text)
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=int(case["duration"]),
        request_assets=entries,
        payload={"prompt_compiler": "auto"},
        unit_id=unit_id,
    )
    prompt = result.provider_prompt

    assert result.compiler_applied is True
    assert result.generation_mode == "ref2va"
    assert prompt.count("ARCREEL_H3_VISUAL_FRAME_POLICY:") == 1
    assert prompt.count("Visual-frame note: the spoken words in this shot are audio-only") == int(
        case["dialogues"]
    )
    assert "[Shot 1] [Shot 1]" not in prompt

    expected_shots = len(re.findall(r"(?m)^\[Shot\s+\d+\]", text))
    assert len(re.findall(r"(?m)^\[Shot\s+\d+\]", prompt)) == expected_shots
    assert len(entries) <= 9
    for index in range(1, len(entries) + 1):
        assert f"<Subject {index}>" in prompt


def test_e11u02_exercises_near_limit_eight_reference_images() -> None:
    text = str(UNITS["E11U02"]["text"])
    entries = _reference_entries(text)
    assert len(entries) == 8
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=15,
        request_assets=entries,
        payload={"prompt_compiler": "auto"},
        unit_id="E11U02",
    )
    assert "<Subject 8>" in result.provider_prompt
    assert result.provider_prompt.count("<d>[Chinese]") == 3


def test_e13u01_preserves_intended_identity_screen_text_as_human_text() -> None:
    text = str(UNITS["E13U01"]["text"])
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=_reference_entries(text),
        payload={"prompt_compiler": "auto"},
        unit_id="E13U01",
    )
    prompt = result.provider_prompt
    assert 'On-screen text: render exactly "沈知意 / 天枢科技联合创始人".' in prompt
    assert 'render exactly "<Subject' not in prompt


def test_e15u03_preserves_intended_latin_screen_text_without_dialogue_notes() -> None:
    text = str(UNITS["E15U03"]["text"])
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=15,
        request_assets=_reference_entries(text),
        payload={"prompt_compiler": "auto"},
        unit_id="E15U03",
    )
    prompt = result.provider_prompt
    assert 'On-screen text: render exactly "TIANSHU NEXT".' in prompt
    assert "Visual-frame note: the spoken words in this shot are audio-only" not in prompt


def test_e14u03_audio_prompt_literal_does_not_become_visible_screen_text() -> None:
    text = str(UNITS["E14U03"]["text"])
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=15,
        request_assets=_reference_entries(text),
        payload={"prompt_compiler": "auto"},
        unit_id="E14U03",
    )
    prompt = result.provider_prompt
    assert '声音：电话提示"暂时无法接通"。' in prompt
    assert 'render exactly "暂时无法接通"' not in prompt


def test_compiled_multi_unit_prompt_is_idempotent_for_visual_frame_policy() -> None:
    text = str(UNITS["E13U01"]["text"])
    entries = _reference_entries(text)
    first = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=entries,
        payload={"prompt_compiler": "auto"},
        unit_id="E13U01",
    ).provider_prompt
    second = compile_reference_video_provider_prompt(
        source_prompt=first,
        fallback_prompt=first,
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=entries,
        payload={"prompt_compiler": "auto"},
        unit_id="E13U01",
    ).provider_prompt
    assert second == first
