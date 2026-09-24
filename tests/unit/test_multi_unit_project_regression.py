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
    "E4U02": {
        "duration": 15,
        "dialogues": 2,
        "text": """[Shot 1]
@[沈知意小房子]，特写屏幕、构图居中、50mm，镜头固定。闹钟标签写着"给念念打电话"。
声音：电子提示。

【转场】褪色淡入

[Shot 2] At 00:05.000
闪回近景、构图居中、50mm，镜头轻微缩放。@[幼年陆念]抱@[手机]贴脸哭、肩膀一抽一抽。
@[幼年陆念]：{妈妈，我想你}
声音：电话底噪。

【转场】褪色淡入

[Shot 3] At 00:10.000
闪回近景、构图居中、50mm，镜头固定。稍大的@[陆念]看一眼别处、低头摆弄手里玩具。
@[陆念]：{妈妈，我在忙}
声音：忙音。""",
    },
    "E11U03": {
        "duration": 15,
        "dialogues": 2,
        "text": """[Shot 1]
@[AI峰会]媒体区，近景、构图居中、50mm，镜头固定。@[苏晚]对镜头从容微笑。
@[苏晚]：{等会就知道}
声音：媒体声。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图纵深、35mm，镜头缓慢推近约0.3米、慢速。@[陆予深]经过"天枢"巨屏、下意识停步。
声音：电子低频。

【转场】硬切

[Shot 3] At 00:10.000
@[学校教室]，中景、构图居中、35mm，镜头固定。投影播放峰会预告。
@[老师]：{今天看直播}
声音：教室声。""",
    },
    "E12U04": {
        "duration": 15,
        "dialogues": 2,
        "text": """[Shot 1]
@[AI峰会]观众席，中景、构图纵深、35mm，镜头轻微平移。观众骚动、媒体连续举机拍摄。
声音：议论与快门。

【转场】硬切

[Shot 2] At 00:05.000
近景、构图居中、50mm，镜头固定。@[技术负责人]盯着屏幕、摇头。
@[技术负责人]：{需要真正熟悉天枢底层的人}
声音：低频。

【转场】硬切

[Shot 3] At 00:10.000
中景、构图居中、35mm，镜头缓慢推近约0.3米、慢速。@[江屿]从观众席站起。
@[江屿]：{那正好}
声音：会场声。""",
    },
    "E12U06": {
        "duration": 10,
        "dialogues": 0,
        "text": """[Shot 1]
@[AI峰会]主屏，特写屏幕、构图居中、50mm，镜头固定。主屏由报错切黑、身份字幕开始加载。
声音：电子低频。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图居中、35mm，镜头缓慢推近约0.4米、慢速。舞台侧门缓缓开启、追光亮起。
声音：掌声前的寂静。""",
    },
    "E13U03": {
        "duration": 15,
        "dialogues": 1,
        "text": """[Shot 1]
@[学校教室]，中景、构图居中、35mm，镜头缓慢推近约0.3米、慢速。直播里@[陆念]猛地坐直。
声音：同学惊呼。

【转场】溶接

[Shot 2] At 00:05.000
@[AI峰会]舞台控制台，近景、构图居中、50mm，镜头固定。@[沈知意]走到控制台前坐下。
@[沈知意]：{打开底层日志}
声音：键盘声。

【转场】硬切

[Shot 3] At 00:10.000
特写屏幕、构图居中、50mm，镜头轻微缩放。日志快速滚动、她目光扫过。
声音：电子声。""",
    },
    "E2U04": {
        "duration": 15,
        "dialogues": 2,
        "text": """[Shot 1]
特写、构图居中、50mm，镜头缓慢推近约0.2米、慢速。@[陆念]抬头认真看、眉头微蹙。
@[陆念]：{苏阿姨不能当吗}
声音：心跳。

【转场】硬切

[Shot 2] At 00:05.000
@[陆家别墅]，特写屏幕、构图居中、50mm，镜头固定。@[手机]震动弹出消息。
@[陆予深]：{中午有事}
@[沈知意]眼睑下移3mm、嘴唇闭合。声音：消息震动。

【转场】溶接

[Shot 3] At 00:10.000
@[餐厅]外，中景、构图驾驶座、35mm，镜头随车轻微平移。@[沈知意]双手握方向盘、目视前方、神情空白、面部无明显起伏。
声音：车流。""",
    },
    "E3U02": {
        "duration": 15,
        "dialogues": 2,
        "text": """[Shot 1]
@[陆家别墅]门厅，近景、构图双人、50mm，镜头缓慢推近约0.2米、慢速。@[周姨]双手在围裙上、身体微仰、嘴唇微张。
@[周姨]：{太太，您要走}
声音：门厅声。

【转场】硬切

[Shot 2] At 00:05.000
中景、构图居中、35mm，镜头缓慢拉远、慢速。@[沈知意]拖箱走出别墅大门，步伐稳定、不回头。
@[沈知意]：{我回国}
声音：行李轮滚动。

【转场】硬切

[Shot 3] At 00:10.000
@[M国机场]，特写手机屏幕、构图居中、50mm，镜头固定。@[手机]显示"单程"机票、时间清晰。
声音：值机提示。""",
    },
    "E9U04": {
        "duration": 15,
        "dialogues": 2,
        "text": """[Shot 1]
@[陆家老宅]门口，远景、构图纵深、35mm，镜头缓慢拉远。@[沈知意]车尾灯远去。
声音：车声。

【转场】淡入淡出

[Shot 2] At 00:05.000
中景、构图居中、35mm，镜头固定。次晨@[陆念]盯@[手机]屏幕、没有妈妈消息。
@[陆念]：{她怎么不打了}
声音：早餐声。

【转场】硬切

[Shot 3] At 00:10.000
@[陆氏集团]办公室，近景、构图居中、50mm，镜头固定。@[陆予深]端咖啡的手停一下。
@[陆予深]：{她最近忙}
声音：杯碟声。""",
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


def test_e4u02_preserves_intended_alarm_label_but_not_dialogue_as_screen_text() -> None:
    text = str(UNITS["E4U02"]["text"])
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=15,
        request_assets=_reference_entries(text),
        payload={"prompt_compiler": "auto"},
        unit_id="E4U02",
    )
    prompt = result.provider_prompt
    assert 'On-screen text: render exactly "给念念打电话".' in prompt
    assert 'render exactly "妈妈，我想你"' not in prompt
    assert 'render exactly "妈妈，我在忙"' not in prompt


def test_e12u06_does_not_invent_identity_copy_when_source_only_says_loading() -> None:
    text = str(UNITS["E12U06"]["text"])
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=_reference_entries(text),
        payload={"prompt_compiler": "auto"},
        unit_id="E12U06",
    )
    prompt = result.provider_prompt
    assert "身份字幕开始加载" in prompt
    assert "On-screen text: render exactly" not in prompt


def test_e13u03_keeps_livestream_and_log_actions_without_forcing_visible_captions() -> None:
    text = str(UNITS["E13U03"]["text"])
    result = compile_reference_video_provider_prompt(
        source_prompt=text,
        fallback_prompt=text,
        model_name="minimax_h3_zm_u24",
        duration_seconds=15,
        request_assets=_reference_entries(text),
        payload={"prompt_compiler": "auto"},
        unit_id="E13U03",
    )
    prompt = result.provider_prompt
    assert "直播里<Subject" in prompt
    assert "日志快速滚动" in prompt
    assert 'render exactly "打开底层日志"' not in prompt
