"""Canonical deterministic full-unit soundtrack contract for H3 runtime repair."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class H3CanonicalAudioTrackSpec:
    unit_id: str
    duration_seconds: float
    asset_path: str
    asset_sha256: str
    sample_rate_hz: int
    channels: int
    bitrate_bps: int
    contract_sha256: str


def _project_relative_asset_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("canonical audio asset_path is required")
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("canonical audio asset_path must be project-relative")
    return path.as_posix()


def canonical_audio_track_contract_digest(
    *,
    unit_id: str,
    duration_seconds: float,
    audio_track_spec: Mapping[str, Any],
) -> str:
    payload = {
        "unit_id": unit_id,
        "duration_seconds": float(duration_seconds),
        "audio_track_spec": audio_track_spec,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_canonical_audio_track_spec(
    unit: Mapping[str, Any],
) -> H3CanonicalAudioTrackSpec | None:
    raw = unit.get("audio_track_spec")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("canonical audio_track_spec must be an object")

    unit_id = str(unit.get("unit_id") or "").strip()
    if not unit_id:
        raise ValueError("canonical audio track requires unit_id")
    duration = unit.get("duration_sec")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or float(duration) <= 0
    ):
        raise ValueError("canonical audio track requires positive duration_sec")

    if raw.get("schema_version") != 1:
        raise ValueError("canonical audio schema_version must be 1")
    if raw.get("ownership") != "deterministic_audio":
        raise ValueError("canonical audio ownership must be deterministic_audio")
    if raw.get("scope") != "full_unit":
        raise ValueError("v1 canonical audio scope must be full_unit")
    if raw.get("codec") != "aac":
        raise ValueError("v1 canonical audio codec must be aac")

    asset_path = _project_relative_asset_path(raw.get("asset_path"))
    asset_sha256 = str(raw.get("asset_sha256") or "").lower()
    if not _SHA256_RE.fullmatch(asset_sha256):
        raise ValueError("canonical audio asset_sha256 must be lowercase SHA256")

    sample_rate = raw.get("sample_rate_hz")
    if (
        type(sample_rate) is not int
        or not 8_000 <= sample_rate <= 96_000
    ):
        raise ValueError("canonical audio sample_rate_hz must be 8000..96000")

    channels = raw.get("channels")
    if type(channels) is not int or channels not in {1, 2}:
        raise ValueError("v1 canonical audio channels must be 1 or 2")

    bitrate = raw.get("bitrate_bps")
    if (
        type(bitrate) is not int
        or not 32_000 <= bitrate <= 512_000
    ):
        raise ValueError("canonical audio bitrate_bps must be 32000..512000")

    digest = canonical_audio_track_contract_digest(
        unit_id=unit_id,
        duration_seconds=float(duration),
        audio_track_spec=raw,
    )
    return H3CanonicalAudioTrackSpec(
        unit_id=unit_id,
        duration_seconds=float(duration),
        asset_path=asset_path,
        asset_sha256=asset_sha256,
        sample_rate_hz=sample_rate,
        channels=channels,
        bitrate_bps=bitrate,
        contract_sha256=digest,
    )
