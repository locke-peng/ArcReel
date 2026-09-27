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
    canonical_m4a: bytes
    canonical_m4a_sha256: str
    canonical_decoded_sha256: str


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


def _encode_canonical_m4a(
    asset_path: Path,
    *,
    spec: H3CanonicalAudioTrackSpec,
) -> bytes:
    """Encode the authoritative AAC track directly into MP4/M4A.

    Direct container encoding is intentional: AAC encoder delay/priming metadata is
    part of the playback contract. Encoding through bare ADTS and remuxing later can
    lose that timing semantics even when the AAC spectral content is otherwise equal.
    """

    with tempfile.TemporaryDirectory(prefix="arcreel-h3-audio-") as raw_dir:
        output = Path(raw_dir) / "canonical.m4a"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
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
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("canonical audio encoding produced no M4A artifact")
        return output.read_bytes()


def _decoded_audio_fingerprint(media_path: Path) -> str | None:
    """Hash decoded audio-frame facts, including AAC priming/timeline semantics."""

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
            "-f",
            "framemd5",
            "-",
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return hashlib.sha256(proc.stdout).hexdigest()


def _decoded_audio_fingerprint_bytes(m4a: bytes) -> str:
    with tempfile.TemporaryDirectory(prefix="arcreel-h3-audio-") as raw_dir:
        source = Path(raw_dir) / "canonical.m4a"
        source.write_bytes(m4a)
        digest = _decoded_audio_fingerprint(source)
        if digest is None:
            raise RuntimeError("canonical M4A produced no decoded audio fingerprint")
        return digest


def evaluate_h3_canonical_audio_media(
    media_path: Path,
    *,
    audio: H3ResolvedCanonicalAudio,
) -> tuple[MediaQAFinding, ...]:
    observed_sha = _decoded_audio_fingerprint(media_path)
    observed_label = observed_sha or "missing_or_undecodable"
    if observed_sha == audio.canonical_decoded_sha256:
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
                ("canonical_m4a_sha256", audio.canonical_m4a_sha256),
                ("canonical_decoded_sha256", audio.canonical_decoded_sha256),
                ("observed_decoded_sha256", observed_label),
            ),
        ),
    )


def _remux_canonical_audio(
    media_path: Path,
    *,
    audio: H3ResolvedCanonicalAudio,
) -> None:
    temp_audio = media_path.with_name(f".{media_path.stem}.h3-canonical-audio.tmp.m4a")
    temp_out = media_path.with_name(f".{media_path.stem}.h3-audio-remux.tmp.mp4")
    temp_audio.write_bytes(audio.canonical_m4a)
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
                str(temp_audio),
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
        temp_audio.unlink(missing_ok=True)
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
    if duration + 0.05 < spec.duration_seconds:
        raise RuntimeError(
            "canonical audio does not cover the full unit duration: "
            f"{duration:.6f}s < {spec.duration_seconds:.6f}s"
        )

    # A SHA-pinned source may carry a tail beyond the authored unit. Canonical
    # ownership is bounded by unit.duration_sec; direct M4A encoding consumes
    # exactly that window and retains AAC priming/edit-list playback semantics.
    canonical_m4a = _encode_canonical_m4a(asset, spec=spec)
    resolved = H3ResolvedCanonicalAudio(
        spec=spec,
        asset_path=asset,
        canonical_m4a=canonical_m4a,
        canonical_m4a_sha256=hashlib.sha256(canonical_m4a).hexdigest(),
        canonical_decoded_sha256=_decoded_audio_fingerprint_bytes(canonical_m4a),
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
