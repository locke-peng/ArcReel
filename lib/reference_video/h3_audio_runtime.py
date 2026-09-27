"""Trusted full-unit canonical soundtrack QA and deterministic remux for H3."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.path_safety import safe_join
from lib.reference_video.h3_audio_contract import (
    H3CanonicalAudioTrackSpec,
    parse_canonical_audio_track_spec,
)
from lib.reference_video.h3_auto_repair_loop import H3AutoRepairPlan
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_runtime_gate import (
    H3DeterministicRepairHandler,
    H3MediaQAEvaluator,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
)
from lib.video_prompt_compilers.h3_director_compiler import CanonicalDirectorBundle


@dataclass(frozen=True)
class H3ResolvedCanonicalAudio:
    spec: H3CanonicalAudioTrackSpec
    asset_path: Path
    canonical_adts: bytes
    canonical_encoded_adts_sha256: str
    canonical_muxed_adts_sha256: str


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    return float(payload["format"]["duration"])


def _encode_canonical_adts(
    asset_path: Path,
    *,
    spec: H3CanonicalAudioTrackSpec,
) -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(asset_path),
            "-vn",
            "-map_metadata",
            "-1",
            "-ar",
            str(spec.sample_rate_hz),
            "-ac",
            str(spec.channels),
            "-c:a",
            "aac",
            "-b:a",
            str(spec.bitrate_bps),
            "-t",
            f"{spec.duration_seconds:.9f}",
            "-f",
            "adts",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    if not proc.stdout:
        raise RuntimeError("canonical audio encoding produced no AAC packets")
    return proc.stdout


def _media_adts(media_path: Path) -> bytes | None:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-map",
            "0:a:0",
            "-c:a",
            "copy",
            "-f",
            "adts",
            "-",
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def _canonical_muxed_adts_sha256(
    canonical_adts: bytes,
    *,
    duration_seconds: float,
) -> str:
    """Fingerprint the AAC packets after the same MP4 duration closure used at runtime."""

    with tempfile.TemporaryDirectory(prefix="arcreel-h3-audio-") as raw_dir:
        root = Path(raw_dir)
        source = root / "canonical.aac"
        muxed = root / "canonical.m4a"
        source.write_bytes(canonical_adts)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-c:a",
                "copy",
                "-t",
                f"{duration_seconds:.9f}",
                "-movflags",
                "+faststart",
                str(muxed),
            ],
            check=True,
        )
        roundtrip = _media_adts(muxed)
        if roundtrip is None:
            raise RuntimeError("canonical audio MP4 round-trip produced no AAC packets")
        return hashlib.sha256(roundtrip).hexdigest()


def evaluate_h3_canonical_audio_media(
    media_path: Path,
    *,
    audio: H3ResolvedCanonicalAudio,
) -> tuple[MediaQAFinding, ...]:
    observed = _media_adts(media_path)
    observed_sha = (
        hashlib.sha256(observed).hexdigest()
        if observed is not None
        else "missing_or_non_aac"
    )
    if observed_sha == audio.canonical_muxed_adts_sha256:
        return ()

    return (
        MediaQAFinding(
            unit_id=audio.spec.unit_id,
            canonical_violation=(
                "final soundtrack does not match the SHA-pinned Canonical full-unit audio"
            ),
            severity=MediaQASeverity.BLOCKING,
            provider_result_usable=True,
            audio_is_accepted=False,
            repairability=MediaQARepairability.DETERMINISTIC,
            affected_fraction=1.0,
            failure_class=H3FailureClass.AUDIO_ONLY_FAILURE,
            tags=("audio_only_failure", "canonical_audio_mismatch"),
            details=(
                ("audio_contract_sha256", audio.spec.contract_sha256),
                ("audio_asset_sha256", audio.spec.asset_sha256),
                (
                    "canonical_encoded_adts_sha256",
                    audio.canonical_encoded_adts_sha256,
                ),
                (
                    "canonical_muxed_adts_sha256",
                    audio.canonical_muxed_adts_sha256,
                ),
                ("observed_adts_sha256", observed_sha),
            ),
        ),
    )


def _remux_canonical_audio(
    media_path: Path,
    *,
    audio: H3ResolvedCanonicalAudio,
) -> None:
    temp_aac = media_path.with_name(f".{media_path.stem}.h3-canonical-audio.tmp.aac")
    temp_out = media_path.with_name(f".{media_path.stem}.h3-audio-remux.tmp.mp4")
    temp_aac.write_bytes(audio.canonical_adts)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(media_path),
                "-i",
                str(temp_aac),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-t",
                f"{audio.spec.duration_seconds:.9f}",
                "-movflags",
                "+faststart",
                str(temp_out),
            ],
            check=True,
        )
        if not temp_out.is_file() or temp_out.stat().st_size == 0:
            raise RuntimeError("canonical audio remux produced no output")
        os.replace(temp_out, media_path)
    finally:
        temp_aac.unlink(missing_ok=True)
        temp_out.unlink(missing_ok=True)


def build_h3_canonical_audio_runtime_bundle(
    canonical_director: Mapping[str, Any],
    *,
    unit_id: str,
    project_path: Path,
) -> tuple[
    H3MediaQAEvaluator | None,
    Mapping[H3RepairAction, H3DeterministicRepairHandler],
]:
    bundle = CanonicalDirectorBundle.resolve(canonical_director, unit_id=unit_id)
    spec = parse_canonical_audio_track_spec(bundle.unit)
    if spec is None:
        return None, {}

    asset = safe_join(project_path, spec.asset_path, require_file=True)
    actual_sha = sha256_file(asset)
    if actual_sha != spec.asset_sha256:
        raise RuntimeError(
            f"canonical audio SHA mismatch: {actual_sha} != {spec.asset_sha256}"
        )

    duration = _probe_duration(asset)
    if abs(duration - spec.duration_seconds) > 0.05:
        raise RuntimeError(
            "canonical audio duration does not match unit duration: "
            f"{duration:.6f}s != {spec.duration_seconds:.6f}s"
        )

    canonical_adts = _encode_canonical_adts(asset, spec=spec)
    resolved = H3ResolvedCanonicalAudio(
        spec=spec,
        asset_path=asset,
        canonical_adts=canonical_adts,
        canonical_encoded_adts_sha256=hashlib.sha256(canonical_adts).hexdigest(),
        canonical_muxed_adts_sha256=_canonical_muxed_adts_sha256(
            canonical_adts,
            duration_seconds=spec.duration_seconds,
        ),
    )

    async def _evaluator(media_path: Path) -> tuple[MediaQAFinding, ...]:
        return await asyncio.to_thread(
            evaluate_h3_canonical_audio_media,
            media_path,
            audio=resolved,
        )

    def _repair(media_path: Path, _plan: H3AutoRepairPlan) -> None:
        _remux_canonical_audio(media_path, audio=resolved)

    return _evaluator, {
        H3RepairAction.AUDIO_REPAIR_REMUX: _repair,
    }
