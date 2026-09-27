"""Canonical deterministic exact-text plate contract for H3 post-provider authoring."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class H3ExactTextPlateSpec:
    unit_id: str
    shot_id: str
    start_seconds: float
    end_seconds: float
    exact_text: str
    asset_path: str
    asset_sha256: str
    contract_sha256: str
    ssim_threshold: float = 0.99

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def _sequence(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _project_relative_asset_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("deterministic text plate asset_path is required")
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("deterministic text plate asset_path must be project-relative")
    return path.as_posix()


def _full_frame_region(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("deterministic text plate region is required")
    if value.get("unit") != "normalized":
        raise ValueError("deterministic text plate region.unit must be normalized")
    expected = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    for key, wanted in expected.items():
        raw = value.get(key)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError(f"deterministic text plate region.{key} must be numeric")
        if abs(float(raw) - wanted) > 1e-9:
            raise ValueError(
                "v1 deterministic text plate supports only full-frame replacement"
            )


def exact_text_plate_contract_digest(
    *,
    unit_id: str,
    shot_id: str,
    start_seconds: float,
    end_seconds: float,
    screen_text: Mapping[str, Any],
) -> str:
    """Bind exact text + plate authorship facts without exposing the text to the provider."""

    payload = {
        "unit_id": unit_id,
        "shot_id": shot_id,
        "start_seconds": float(start_seconds),
        "end_seconds": float(end_seconds),
        "kind": screen_text.get("kind"),
        "text": screen_text.get("text"),
        "plate_spec": screen_text.get("plate_spec"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_exact_text_plate_spec(
    screen_text: Mapping[str, Any],
    *,
    unit_id: str,
    shot_id: str,
    start_seconds: float,
    end_seconds: float,
) -> H3ExactTextPlateSpec | None:
    """Parse one exact screen-text item.

    No plate_spec means legacy/provider-owned exact text and returns None. Once a
    plate_spec is present, the v1 contract is strict and fails loud.
    """

    plate = screen_text.get("plate_spec")
    if plate is None:
        return None
    if str(screen_text.get("legibility") or "") != "exact":
        raise ValueError("deterministic plate_spec is allowed only for exact screen text")
    if not isinstance(plate, Mapping):
        raise ValueError("deterministic text plate_spec must be an object")
    if plate.get("schema_version") != 1:
        raise ValueError("deterministic text plate schema_version must be 1")
    if plate.get("ownership") != "deterministic_plate":
        raise ValueError("deterministic text plate ownership must be deterministic_plate")
    if plate.get("compositing") != "full_frame_replace":
        raise ValueError(
            "v1 deterministic text plate compositing must be full_frame_replace"
        )

    text = screen_text.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("deterministic exact text plate requires non-empty text")

    asset_path = _project_relative_asset_path(plate.get("asset_path"))
    asset_sha256 = str(plate.get("asset_sha256") or "").lower()
    if not _SHA256_RE.fullmatch(asset_sha256):
        raise ValueError("deterministic text plate asset_sha256 must be lowercase SHA256")

    _full_frame_region(plate.get("region"))

    typography = plate.get("typography")
    if not isinstance(typography, Mapping):
        raise ValueError("deterministic text plate typography is required")
    if typography.get("authority") != "asset_pixels":
        raise ValueError(
            "v1 deterministic text plate typography.authority must be asset_pixels"
        )

    threshold_raw = plate.get("ssim_threshold", 0.99)
    if (
        not isinstance(threshold_raw, (int, float))
        or isinstance(threshold_raw, bool)
        or not 0.98 <= float(threshold_raw) <= 1.0
    ):
        raise ValueError("deterministic text plate ssim_threshold must be within 0.98..1.0")

    if end_seconds <= start_seconds:
        raise ValueError("deterministic text plate shot interval must be positive")

    digest = exact_text_plate_contract_digest(
        unit_id=unit_id,
        shot_id=shot_id,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        screen_text=screen_text,
    )
    return H3ExactTextPlateSpec(
        unit_id=unit_id,
        shot_id=shot_id,
        start_seconds=float(start_seconds),
        end_seconds=float(end_seconds),
        exact_text=text,
        asset_path=asset_path,
        asset_sha256=asset_sha256,
        contract_sha256=digest,
        ssim_threshold=float(threshold_raw),
    )


def exact_text_plate_specs_from_unit(
    unit: Mapping[str, Any],
) -> tuple[H3ExactTextPlateSpec, ...]:
    unit_id = str(unit.get("unit_id") or "").strip()
    if not unit_id:
        raise ValueError("canonical exact-text contract requires unit_id")

    specs: list[H3ExactTextPlateSpec] = []
    seen_shots: set[str] = set()
    for shot in _sequence(unit.get("shots")):
        if not isinstance(shot, Mapping):
            continue
        shot_id = str(shot.get("shot_id") or "").strip()
        if not shot_id:
            raise ValueError("canonical exact-text contract requires shot_id")
        start = shot.get("start_sec")
        end = shot.get("end_sec")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
        ):
            raise ValueError("canonical exact-text plate shots require numeric start_sec/end_sec")

        for item in _sequence(shot.get("screen_text")):
            if not isinstance(item, Mapping):
                continue
            spec = parse_exact_text_plate_spec(
                item,
                unit_id=unit_id,
                shot_id=shot_id,
                start_seconds=float(start),
                end_seconds=float(end),
            )
            if spec is None:
                continue
            if shot_id in seen_shots:
                raise ValueError(
                    "v1 deterministic text plate allows at most one plate contract per shot"
                )
            seen_shots.add(shot_id)
            specs.append(spec)
    return tuple(specs)
