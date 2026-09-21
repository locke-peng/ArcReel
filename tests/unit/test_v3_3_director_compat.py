from __future__ import annotations

from dataclasses import dataclass

from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.video_prompt_compilers.h3_director_compiler import compile_h3_director_prompt


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def _v33_bundle() -> dict:
    return {
        "registries": {
            "characters": {
                "CHAR-SZY": {"name": "沈知意"},
                "CHAR-LN": {"name": "陆念"},
            },
            "scenes": {
                "SC-SUMMIT": {"name": "AI峰会主会场"},
            },
        },
        "units": [
            {
                "unit_id": "E13-U01",
                "duration_sec": 10,
                "scene_id": "SC-SUMMIT",
                "continuity_level": "hard",
                "scene_anchors": ["主舞台大屏", "技术控制台", "侧台门", "VIP前排"],
                "continuity_in": {
                    "subjects": {"CHAR-SZY": "侧台门后，白色职业西装"},
                    "environment": "主屏黑场待揭示",
                    "axis": "舞台-观众席180度轴线锁定",
                },
                "continuity_out": {
                    "subjects": {"CHAR-SZY": "追光中心，面向观众"},
                    "environment": "主屏显示沈知意身份",
                    "axis": "保持舞台-观众席轴线",
                },
                "active_subject_ids": ["CHAR-SZY"],
                "depicted_subject_ids": [],
                "referenced_entity_ids": [],
                "speaker_semantic_order": ["CHAR-SZY"],
                "shots": [
                    {
                        "shot_id": "E13-U01-S01",
                        "start_sec": 0,
                        "end_sec": 4,
                        "duration_sec": 4,
                        "shot_size": "SS-06 大特写",
                        "composition": "CP-01 居中对称，身份文字与人物建立公共揭示",
                        "lens_mm": 85,
                        "camera_position_code": "CAM-EYE",
                        "camera_motion": {
                            "type": "static",
                            "direction": "none",
                            "amplitude": "none",
                            "speed": "static",
                        },
                        "lighting": {
                            "direction": "LT-02 侧光",
                            "ratio": "LR-03 中高反差",
                            "color_temperature": "CTM-04 冷白科技光",
                        },
                        "color_grade": "CG-10 冷白科技舞台，低饱和，肤色自然",
                        "scene_anchors": ["主舞台大屏", "侧台门"],
                        "emotion_motion": "身份公开前的临界停顿；全场注意力被大屏吸住",
                        "action": "巨屏亮起沈知意的身份信息，侧台门同时打开，她尚未完全走入追光。",
                        "screen_text": [
                            {
                                "kind": "identity title",
                                "legibility": "exact",
                                "text": "沈知意 / 天枢联合创始人·原始架构师",
                            }
                        ],
                        "dialogue": [],
                        "transition_in": {
                            "type": "big_screen_reveal",
                            "medium": "主屏由黑场亮起",
                            "from": "E12侧台门开启",
                        },
                        "transition_out": {
                            "type": "gaze_bridge",
                            "medium": "全场视线从大屏转向侧台",
                        },
                    },
                    {
                        "shot_id": "E13-U01-S02",
                        "start_sec": 4,
                        "end_sec": 10,
                        "duration_sec": 6,
                        "shot_size": "SS-03 中景",
                        "composition": "CP-05 中心构图，舞台纵深完整",
                        "lens_mm": 50,
                        "camera_position_code": "CAM-EYE",
                        "camera_motion": {
                            "type": "tracking",
                            "direction": "follow_subject",
                            "amplitude": "small",
                            "speed": "slow",
                        },
                        "lighting": {
                            "direction": "追光由侧台移动到舞台中心",
                            "ratio": "人物亮、观众席压暗",
                            "color_temperature": "冷白为主",
                        },
                        "color_grade": "清透、冷静、克制，高光不过曝",
                        "scene_anchors": ["主舞台大屏", "技术控制台", "VIP前排"],
                        "emotion_motion": "震惊环境中保持从容；步幅稳定，肩背打开，不急不躲",
                        "action": "沈知意从侧台走入追光并站定，主屏身份条保持可读，观众席由窃窃私语转为安静。",
                        "screen_text": [],
                        "dialogue": [
                            {
                                "speaker_id": "CHAR-SZY",
                                "text": "打开版本差异。",
                            }
                        ],
                        "dialogue_direction": {
                            "CHAR-SZY": "平静、专业、低音量，不解释身份"
                        },
                        "transition_in": {
                            "type": "gaze_bridge",
                            "medium": "承接上一镜全场视线",
                        },
                        "transition_out": {
                            "type": "action_match",
                            "medium": "她转向技术控制台的动作",
                            "to": "故障修复单元",
                        },
                    },
                ],
                "cross_shot_dialogue": [],
                "sound_design": {
                    "ambience": "会场空调底噪、观众低声议论、舞台电子系统轻微运行声。",
                    "music": "低频电子持续音在身份亮屏时进入，人物站定后迅速压低。",
                },
                "director_notes": {
                    "visual_style": "公开审判组：冷亮、高压、聚光；后半逐渐转为掌控感。",
                    "transition_motif": "大屏 reveal + 目光承接",
                },
            }
        ],
    }


def test_v33_integrated_director_dimensions_survive_t2va_compile() -> None:
    bundle = _v33_bundle()
    prompt, mode = compile_h3_director_prompt(
        canonical_director=bundle,
        unit_id="E13-U01",
        duration_seconds=10,
    )

    assert mode == "t2va"
    assert "Scene: AI峰会主会场." in prompt
    assert "Unit scene anchors:" in prompt
    assert "主舞台大屏" in prompt
    assert "Continuity-in state" in prompt
    assert "Continuity-out state" in prompt
    assert "舞台-观众席180度轴线锁定" in prompt

    assert "Framing / shot size: SS-06 大特写." in prompt
    assert "Composition: CP-01 居中对称" in prompt
    assert "Lighting:" in prompt
    assert "LT-02 侧光" in prompt
    assert "Color grade: CG-10 冷白科技舞台" in prompt
    assert "Scene anchors that must remain spatially stable" in prompt

    assert "Transition in:" in prompt
    assert "big_screen_reveal" in prompt
    assert "Transition out:" in prompt
    assert "gaze_bridge" in prompt
    assert "[Shot 2] At 00:04.000" in prompt
    assert "50mm lens" in prompt
    assert "slow small tracking shot following the subject" in prompt
    assert "Performance / emotional beat:" in prompt
    assert 'render exactly "沈知意 / 天枢联合创始人·原始架构师"' in prompt
    assert "<d>[Chinese] 打开版本差异。</d>" in prompt

    assert "overall_soundscape:\n会场空调底噪" in prompt
    assert "non_diegetic_music:\n低频电子持续音" in prompt
    assert "NEGATIVE:" not in prompt


def test_v33_integrated_director_survives_real_reference_video_compilation_t2va() -> None:
    result = compile_reference_video_provider_prompt(
        source_prompt="legacy fallback",
        fallback_prompt="legacy rendered",
        model_name="MiniMax-H3",
        duration_seconds=10,
        request_assets=[],
        payload={"canonical_director": _v33_bundle(), "prompt_compiler": "auto"},
        unit_id="E13-U01",
    )
    assert result.compiler_applied is True
    assert result.generation_mode == "t2va"
    assert "Framing / shot size: SS-06 大特写." in result.provider_prompt
    assert "Continuity-in state" in result.provider_prompt
    assert "big_screen_reveal" in result.provider_prompt


def test_v33_integrated_director_survives_real_reference_video_compilation_ref2va() -> None:
    result = compile_reference_video_provider_prompt(
        source_prompt="legacy fallback",
        fallback_prompt="legacy rendered",
        model_name="MiniMax-H3",
        duration_seconds=10,
        request_assets=[Entry(Ref("character", "沈知意"))],
        payload={
            "canonical_director": _v33_bundle(),
            "prompt_compiler": "auto",
            "reference_image_labels": ["沈知意"],
        },
        unit_id="E13-U01",
    )
    assert result.compiler_applied is True
    assert result.generation_mode == "ref2va"
    assert "<Picture 1>" in result.provider_prompt
    assert "<Subject 1>" in result.provider_prompt
    assert "Framing / shot size: SS-06 大特写." in result.provider_prompt
    assert "Color grade: CG-10 冷白科技舞台" in result.provider_prompt
    assert "action_match" in result.provider_prompt
