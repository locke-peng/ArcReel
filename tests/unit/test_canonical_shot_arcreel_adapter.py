from __future__ import annotations

from lib.video_prompt_compilers.canonical_shot_arcreel_adapter import (
    adapt_document,
    arcreel_unit_id,
    build_coverage_report,
    select_unit_bundle,
)
from lib.video_prompt_compilers.h3_director_compiler import compile_h3_director_prompt


def _shot(shot_id: str = "E01S01") -> dict:
    return {
        "schema_version": "3.0-p0.1",
        "shot_id": shot_id,
        "order": 1,
        "start_time_sec": 0,
        "duration_sec": 5,
        "framing": {"id": "SS-03", "label": "medium shot"},
        "angle": {"id": "AN-01", "label": "eye level"},
        "composition": {"id": "CP-03", "label": "leading lines"},
        "lens": {
            "focal_length_mm": 50,
            "lens_family": "standard",
            "depth_of_field": "moderate depth of field",
        },
        "camera": {
            "position": "CAM-EYE",
            "movement": "push_in",
            "speed": "slow",
            "amplitude": "small",
        },
        "lighting": {
            "direction": {"id": "LT-02", "label": "side light"},
            "ratio": {"id": "LR-02", "label": "medium contrast"},
            "color_temperature": {"id": "CTM-04", "label": "mixed color temperature"},
            "notes": "character-driven intimacy",
        },
        "color_grade": {"id": "CG-02", "label": "cold blue urban"},
        "motion": {"id": "MOV-PUSH", "label": "push in"},
        "emotion": {
            "primary_id": "EMO-NEG-03",
            "secondary_ids": ["EMO-NEU-07"],
            "visible_cues": ["lowered gaze"],
        },
        "visual": {
            "aspect_ratio": "16:9",
            "style": "cinematic realism",
            "quality_terms": ["cinematic", "high detail"],
            "render_notes": [],
        },
        "scene": {
            "location": "S01 M国机场",
            "time_of_day": "night",
            "weather": "indoor",
            "environment": ["arrival hall"],
            "props": ["phone"],
            "visible_text": ["妈妈"],
        },
        "subjects": [
            {
                "subject_id": "C01",
                "name": "沈知意",
                "position": "foreground",
                "appearance_anchors": ["female lead", "costume_stage W01"],
                "action": "拖着行李走出机场",
                "facial_expression": "restrained disappointment",
                "body_language": "slight shoulder drop",
                "dialogue": [
                    {
                        "speaker_id": "S1",
                        "language": "Chinese",
                        "text": "今天是我生日",
                        "delivery": "restrained",
                        "offscreen": False,
                        "cross_cut": False,
                        "cutoff": False,
                    }
                ],
            }
        ],
        "audio": {
            "ambience": ["机场广播"],
            "sfx": ["行李轮声"],
            "diegetic_music": [],
            "non_diegetic_music": "N/A",
        },
        "transition": {"name": "match cut", "medium": "phone to paper"},
        "reference_uses": [],
        "negative_policy": {
            "allow_visible_text": True,
            "allow_expressionless": False,
            "allow_flat_lighting": False,
            "extra_forbid": ["watermark"],
            "extra_allow": [],
        },
        "notes": ["costume_stage_C01=W01"],
    }


def test_unit_id_mapping_is_one_shot_per_reference_video_unit() -> None:
    assert arcreel_unit_id("E01S01") == "E1U01"
    assert arcreel_unit_id("E15S16") == "E15U16"


def test_adapter_preserves_rich_fields_and_normalizes_dialogue_owner() -> None:
    document = {
        "schema_version": "3.0-p0.1",
        "project_id": "demo",
        "shots": [_shot()],
    }
    bundle, issues = adapt_document(document)
    assert issues == []

    unit = bundle["units"][0]
    shot = unit["shots"][0]
    assert unit["unit_id"] == "E1U01"
    assert unit["scene_id"] == "S01"
    assert shot["framing"]["label"] == "medium shot"
    assert shot["composition"]["label"] == "leading lines"
    assert shot["lighting"]["direction"]["label"] == "side light"
    assert shot["color_grade"]["label"] == "cold blue urban"
    assert shot["subject_states"][0]["costume_variant"] == "W01"
    assert shot["subject_states"][0]["reference_name_hint"] == "沈知意/W01"
    assert shot["dialogue"][0]["speaker_id"] == "C01"
    assert shot["dialogue"][0]["source_local_speaker_id"] == "S1"
    assert shot["transition_to_next"]["name"] == "match cut"
    assert shot["screen_text"][0]["text"] == "妈妈"

    report = build_coverage_report(document, bundle, issues)
    assert report["source_shot_count"] == 1
    assert report["output_unit_count"] == 1
    assert report["facts"]["dialogue_lines"] == 1
    assert report["facts"]["unresolved_local_dialogue_speaker_ids"] == 0
    assert report["facts"]["explicit_transition_shots"] == 1


def test_adapter_bundle_compiles_through_real_h3_director_path() -> None:
    document = {
        "schema_version": "3.0-p0.1",
        "project_id": "demo",
        "shots": [_shot()],
    }
    bundle, _ = adapt_document(document)
    payload = select_unit_bundle(bundle, "E1U01")

    prompt, mode = compile_h3_director_prompt(
        canonical_director=payload,
        unit_id="E1U01",
        duration_seconds=5,
        reference_source_names=["沈知意/W01", "M国机场"],
        reference_image_labels=["沈知意/W01", "M国机场"],
        reference_kinds={"沈知意/W01": "character", "M国机场": "scene"},
        max_prompt_chars=7000,
    )

    assert mode == "ref2va"
    assert "Visual setup: framing medium shot" in prompt
    assert "Lighting: side light" in prompt
    assert "Color grade: cold blue urban" in prompt
    assert "Environment: M国机场" in prompt
    assert "costume W01" in prompt
    assert "<Subject 1> (S1) says" in prompt
    assert "<d>[Chinese] 今天是我生日</d>" in prompt
    assert "Transition to next unit: match cut" in prompt
