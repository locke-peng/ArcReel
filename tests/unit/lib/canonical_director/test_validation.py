from typing import Any, cast

import pytest

from lib.canonical_director.model import CANONICAL_DIRECTOR_MAX_JSON_BYTES
from lib.canonical_director.validation import (
    CanonicalDirectorPayloadError,
    CanonicalDirectorPayloadTooLarge,
    canonical_director_json_bytes,
    normalize_canonical_director_v1_ingress,
    validate_canonical_director_v1,
)
from tests.unit.lib.canonical_director.test_model import _payload


def test_ingress_requires_json_object():
    with pytest.raises(CanonicalDirectorPayloadError, match="JSON object"):
        validate_canonical_director_v1(["not", "an", "object"])


def test_ingress_rejects_payload_over_64_kib():
    payload = _payload()
    cast(list[dict[str, Any]], payload["shots"])[0]["visual_style"] = "x" * CANONICAL_DIRECTOR_MAX_JSON_BYTES

    with pytest.raises(CanonicalDirectorPayloadTooLarge):
        validate_canonical_director_v1(payload)


def test_normalized_payload_stays_under_contract_limit():
    director = validate_canonical_director_v1(_payload())

    assert len(canonical_director_json_bytes(director)) < CANONICAL_DIRECTOR_MAX_JSON_BYTES


def test_compat_ingress_accepts_unit_only():
    director = normalize_canonical_director_v1_ingress(_payload(), unit_id="E1U01")
    assert director.unit_id == "E1U01"


def test_compat_ingress_accepts_unit_wrapper_and_discards_registries():
    director = normalize_canonical_director_v1_ingress(
        {"unit": _payload(), "registries": {"characters": {"C01": {"name": "ignored here"}}}},
        unit_id="E1U01",
    )
    assert director.unit_id == "E1U01"
    assert "registries" not in director.model_dump(mode="json")


def test_compat_ingress_selects_exact_unit_from_episode_wrapper():
    first = _payload()
    second = _payload()
    second["unit_id"] = "E1U02"
    cast(dict[str, Any], second["source"])["shot_ids"] = ["E01S02"]
    cast(list[dict[str, Any]], second["shots"])[0]["shot_id"] = "E01S02"

    director = normalize_canonical_director_v1_ingress(
        {"units": [first, second], "registries": {}},
        unit_id="E1U02",
    )
    assert director.unit_id == "E1U02"


def test_compat_ingress_rejects_ambiguous_episode_wrapper_without_unit_id():
    with pytest.raises(CanonicalDirectorPayloadError, match="requires unit_id"):
        normalize_canonical_director_v1_ingress({"units": [_payload(), _payload()]})


def test_compat_ingress_rejects_unit_mismatch():
    with pytest.raises(CanonicalDirectorPayloadError, match="unit mismatch"):
        normalize_canonical_director_v1_ingress(_payload(), unit_id="E1U99")
