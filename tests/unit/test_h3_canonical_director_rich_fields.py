from __future__ import annotations

from lib.video_prompt_compilers.h3_director_compiler import compile_h3_director_prompt


def test_rich_fields_are_rendered_and_derivative_ref_maps_to_base_identity() -> None:
    canonical = {
        "unit": {
            "unit_id": "E13U03",
            "duration_sec": 5,
            "scene_id": "S14",
            "active_subject_ids": ["C01"],
            "depicted_subject_ids": [],
            "referenced_entity_ids": [],
            "continuity_level": "hard",
            "speaker_semantic_order": ["C01"],
            "cross_shot_dialogue": [],
            "sound_design": {
                "ambience": "summit room tone",
                "sfx": ["system confirmation tone"],
                "diegetic_music": [],
                "music": "N/A",
            },
            "shots": [
                {
                    "shot_id": "E13S03",
                    "start_sec": 0,
                    "duration_sec": 5,
                    "framing": {"id": "SS-03", "label": "medium shot"},
                    "angle": {"id": "AN-01", "label": "eye level"},
                    "composition": {"id": "CP-02", "label": "centered composition"},
                    "lens_mm": 50,
                    "lens_family": "standard",
                    "depth_of_field": "moderate depth of field",
                    "camera_position_code": "CAM-EYE",
                    "camera_motion": {"type": "push_in", "direction": "forward", "amplitude": "small", "speed": "slow"},
                    "lighting": {
                        "direction": {"id": "LT-02", "label": "side light"},
                        "ratio": {"id": "LR-02", "label": "medium contrast"},
                        "color_temperature": {"id": "CTM-01", "label": "neutral"},
                        "notes": "controlled keynote lighting",
                    },
                    "color_grade": {"id": "CG-17", "label": "silver gray low saturation"},
                    "environment": {
                        "scene_id": "S14",
                        "scene_name": "AI峰会主会场",
                        "zone_id": None,
                        "time_of_day": "day",
                        "weather": "indoor",
                        "environment_anchors": ["main stage", "giant screen"],
                        "props": ["presentation clicker"],
                    },
                    "props": ["presentation clicker"],
                    "subject_states": [
                        {
                            "subject_id": "C01",
                            "name": "沈知意",
                            "position": "foreground",
                            "costume_variant": "W05",
                            "reference_name_hint": "沈知意/W05",
                            "appearance_anchors": ["female lead", "white summit suit"],
                            "facial_expression": "calm authority",
                            "body_language": "upright controlled posture",
                        }
                    ],
                    "visual_style": "cinematic live-action short drama",
                    "quality_terms": ["cinematic", "high detail"],
                    "action": "沈知意 steps into the public reveal and faces the audience.",
                    "emotion_motion": "calm authority",
                    "screen_text": [],
                    "dialogue_direction": {"C01": "calm and controlled"},
                    "dialogue": [
                        {"speaker_id": "C01", "text": "我是天枢联合创始人。", "offscreen": False, "cutoff": False}
                    ],
                    "continuity_in": {
                        "previous_shot_id": "E13S02",
                        "state": {
                            "scene": {"scene_id": "S14"},
                            "subjects": [{"subject_id": "C01", "name": "沈知意", "costume_variant": "W05"}],
                        },
                    },
                    "transition_to_next": {"name": "match cut", "medium": "stage screen to reaction"},
                    "negative_constraints": {
                        "allow_visible_text": False,
                        "allow_expressionless": False,
                        "allow_flat_lighting": False,
                        "extra_forbid": ["watermark"],
                        "extra_allow": [],
                    },
                }
            ],
        },
        "registries": {
            "characters": {"C01": {"name": "沈知意"}},
            "scenes": {"S14": {"name": "AI峰会主会场"}},
        },
    }

    prompt, mode = compile_h3_director_prompt(
        canonical_director=canonical,
        unit_id="E13U03",
        duration_seconds=5,
        reference_source_names=["沈知意/W05", "AI峰会主会场"],
        reference_image_labels=["沈知意/W05", "AI峰会主会场"],
        reference_kinds={"沈知意/W05": "character", "AI峰会主会场": "scene"},
        max_prompt_chars=7000,
    )

    assert mode == "ref2va"
    assert "Visual setup: framing medium shot" in prompt
    assert "composition centered composition" in prompt
    assert "Lighting: side light" in prompt
    assert "Color grade: silver gray low saturation" in prompt
    assert "Environment: AI峰会主会场" in prompt
    assert "Subject staging: 沈知意" in prompt
    assert "costume W05" in prompt
    assert "Continuity: enter from E13S02" in prompt
    assert "Transition to next unit: match cut" in prompt
    assert "SFX: system confirmation tone" in prompt
    # Critical regression: a derivative ref must still bind to canonical C01.
    assert "<Subject 1> (S1) says" in prompt
