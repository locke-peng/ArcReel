from typing import Any, cast

import pytest
from pydantic import ValidationError

from lib.canonical_director.model import CanonicalDirectorV1
from lib.canonical_director.validation import (
    CanonicalDirectorPayloadError,
    canonical_director_payload,
    validate_canonical_director_v1,
)


def _payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "unit_id": "E1U01",
        "source": {
            "kind": "canonical_shot_ir",
            "schema_version": "3.0-p0.1",
            "project_id": "demo",
            "shot_ids": ["E01S01"],
        },
        "timeline_duration_seconds": 5,
        "shots": [
            {
                "shot_id": "E01S01",
                "start_seconds": 0,
                "duration_seconds": 5,
                "framing": {"id": "SS-03", "label": "medium shot"},
                "composition": {"id": "CP-03", "label": "leading lines"},
                "lens": {"focal_length_mm": 50, "family": "standard", "depth_of_field": "moderate"},
                "camera": {
                    "position": "eye level",
                    "motion": {"type": "push in", "direction": "forward", "amplitude": "small", "speed": "slow"},
                },
                "lighting": {
                    "direction": {"id": "LT-02", "label": "side light"},
                    "ratio": {"id": "LR-02", "label": "medium contrast"},
                    "color_temperature": {"id": "CTM-04", "label": "mixed"},
                },
                "color_grade": {"id": "CG-02", "label": "cold blue urban"},
                "environment": {
                    "scene_id": "S01",
                    "zone_id": "Z01",
                    "time_of_day": "night",
                    "anchors": ["arrival hall"],
                    "props": ["phone"],
                },
                "subjects": [
                    {
                        "subject_id": "C01",
                        "variant_id": "W01",
                        "position": "foreground",
                        "facial_expression": "restrained disappointment",
                        "body_language": "slight shoulder drop",
                    }
                ],
                "speech_performance": [
                    {"subject_id": "C01", "delivery": "restrained", "offscreen": False}
                ],
                "continuity": {"level": "hard", "visible_props": ["phone"]},
                "visual_transition": {"intent": "match action", "medium": "phone to paper"},
                "sound_design": {"ambience": ["airport PA"], "sfx": ["luggage wheels"]},
                "negative_constraints": {
                    "allow_visible_text": False,
                    "allow_expressionless": False,
                    "forbid": ["watermark"],
                },
                "visual_style": "cinematic live-action short drama",
                "quality_terms": ["cinematic", "high detail"],
            }
        ],
    }


def _first_shot(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(list[dict[str, Any]], payload["shots"])[0]


def test_valid_single_unit_contract_round_trips_to_normalized_json_shape():
    director = validate_canonical_director_v1(_payload())

    normalized = canonical_director_payload(director)
    source = cast(dict[str, Any], normalized["source"])
    shot = cast(list[dict[str, Any]], normalized["shots"])[0]
    subject = cast(list[dict[str, Any]], shot["subjects"])[0]

    assert normalized["schema_version"] == "1.0"
    assert normalized["unit_id"] == "E1U01"
    assert source["shot_ids"] == ["E01S01"]
    assert subject["variant_id"] == "W01"


def test_contract_forbids_content_replacement_fields():
    payload = _payload()
    _first_shot(payload)["dialogue"] = [{"speaker_id": "C01", "text": "must not enter director contract"}]

    with pytest.raises(CanonicalDirectorPayloadError, match="CanonicalDirectorV1"):
        validate_canonical_director_v1(payload)


def test_speech_performance_forbids_spoken_text():
    payload = _payload()
    cue = cast(list[dict[str, Any]], _first_shot(payload)["speech_performance"])[0]
    cue["text"] = "formal script owns this"

    with pytest.raises(CanonicalDirectorPayloadError, match="CanonicalDirectorV1"):
        validate_canonical_director_v1(payload)


@pytest.mark.parametrize("forbidden", ["provider", "model", "endpoint", "reference_image_path", "credential"])
def test_contract_forbids_provider_and_file_execution_fields(forbidden: str):
    payload = _payload()
    payload[forbidden] = "forbidden"

    with pytest.raises(CanonicalDirectorPayloadError, match="CanonicalDirectorV1"):
        validate_canonical_director_v1(payload)


def test_source_shot_ids_must_exactly_match_shot_order():
    payload = _payload()
    cast(dict[str, Any], payload["source"])["shot_ids"] = ["E01S02"]

    with pytest.raises(CanonicalDirectorPayloadError, match="CanonicalDirectorV1"):
        validate_canonical_director_v1(payload)


def test_shots_cannot_overlap():
    payload = _payload()
    cast(dict[str, Any], payload["source"])["shot_ids"] = ["E01S01", "E01S02"]
    payload["timeline_duration_seconds"] = 6
    second = dict(_first_shot(payload))
    second.update({"shot_id": "E01S02", "start_seconds": 4, "duration_seconds": 2})
    cast(list[dict[str, Any]], payload["shots"]).append(second)

    with pytest.raises(CanonicalDirectorPayloadError, match="CanonicalDirectorV1"):
        validate_canonical_director_v1(payload)


def test_direct_model_rejects_extra_fields_even_without_ingress_helper():
    payload = _payload()
    payload["mystery"] = True

    with pytest.raises(ValidationError):
        CanonicalDirectorV1.model_validate(payload)
