"""Validation, compatibility ingress, and canonical serialization for CanonicalDirectorV1."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from lib.canonical_director.model import CANONICAL_DIRECTOR_MAX_JSON_BYTES, CanonicalDirectorV1


class CanonicalDirectorPayloadError(ValueError):
    """Malformed request-scoped director payload before provider-specific processing."""


class CanonicalDirectorPayloadTooLarge(CanonicalDirectorPayloadError):
    pass


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalDirectorPayloadError("canonical director payload must be JSON-serializable") from exc


def _preflight_size(payload: object) -> None:
    if len(_json_bytes(payload)) > CANONICAL_DIRECTOR_MAX_JSON_BYTES:
        raise CanonicalDirectorPayloadTooLarge(
            f"canonical director payload exceeds {CANONICAL_DIRECTOR_MAX_JSON_BYTES} UTF-8 JSON bytes"
        )


def validate_canonical_director_v1(payload: object) -> CanonicalDirectorV1:
    """Validate the normalized single-unit internal contract."""

    if not isinstance(payload, Mapping):
        raise CanonicalDirectorPayloadError("canonical director payload must be a JSON object")
    _preflight_size(payload)
    try:
        return CanonicalDirectorV1.model_validate(payload)
    except ValidationError as exc:
        raise CanonicalDirectorPayloadError("canonical director payload does not match CanonicalDirectorV1") from exc


def normalize_canonical_director_v1_ingress(
    payload: object,
    *,
    unit_id: str | None = None,
) -> CanonicalDirectorV1:
    """Normalize the three historical container shapes to one internal single-unit contract.

    Accepted ingress containers are: the unit object itself, {unit, registries}, or
    {units, registries}. registries is compatibility-only and is deliberately
    discarded here; ArcReel identity binding belongs to the later runtime-binding phase.
    The selected unit must already satisfy CanonicalDirectorV1 -- this function does not
    translate legacy director field names or source schemas.
    """

    if not isinstance(payload, Mapping):
        raise CanonicalDirectorPayloadError("canonical director ingress must be a JSON object")
    _preflight_size(payload)

    candidate: object
    wrapped_unit = payload.get("unit")
    wrapped_units = payload.get("units")
    if isinstance(wrapped_unit, Mapping):
        candidate = wrapped_unit
    elif isinstance(wrapped_units, Sequence) and not isinstance(wrapped_units, (str, bytes)):
        units = [item for item in wrapped_units if isinstance(item, Mapping)]
        if unit_id is None:
            if len(units) != 1:
                raise CanonicalDirectorPayloadError(
                    "canonical director ingress with units requires unit_id unless it contains exactly one unit"
                )
            candidate = units[0]
        else:
            matches = [item for item in units if str(item.get("unit_id") or "") == unit_id]
            if len(matches) != 1:
                raise CanonicalDirectorPayloadError(
                    f"canonical director ingress does not contain exactly one unit {unit_id!r}"
                )
            candidate = matches[0]
    else:
        candidate = payload

    director = validate_canonical_director_v1(candidate)
    if unit_id is not None and director.unit_id != unit_id:
        raise CanonicalDirectorPayloadError(
            f"canonical director unit mismatch: requested {unit_id!r}, got {director.unit_id!r}"
        )
    return director


def canonical_director_payload(director: CanonicalDirectorV1) -> dict[str, object]:
    """Return the normalized JSON-compatible shape suitable for a queue request fact."""

    payload = director.model_dump(mode="json", exclude_none=True)
    if not isinstance(payload, dict):
        raise AssertionError("CanonicalDirectorV1 must serialize to a JSON object")
    return payload


def canonical_director_json_bytes(director: CanonicalDirectorV1) -> bytes:
    return _json_bytes(canonical_director_payload(director))


__all__ = [
    "CanonicalDirectorPayloadError",
    "CanonicalDirectorPayloadTooLarge",
    "canonical_director_json_bytes",
    "canonical_director_payload",
    "normalize_canonical_director_v1_ingress",
    "validate_canonical_director_v1",
]