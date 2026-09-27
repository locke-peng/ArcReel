"""Trusted deterministic exact-text plate QA and runtime authoring for H3."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.path_safety import safe_join
from lib.reference_video.h3_auto_repair_loop import H3AutoRepairPlan
from lib.reference_video.h3_exact_text_contract import (
    H3ExactTextPlateSpec,
    exact_text_plate_specs_from_unit,
)
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
    MediaQATimeRange,
)
from lib.video_prompt_compilers.h3_director_compiler import CanonicalDirectorBundle

_SSIM_RE = re.compile(r"All:(?P<ssim>\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class H3ResolvedTextPlate:
    spec: H3ExactTextPlateSpec
    asset_path: Path


def _probe_video(path: Path) -> tuple[float, float, int, int]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=codec_type,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    video = next(
        stream
        for stream in payload.get("streams", [])
        if stream.get("codec_type") == "video"
    )
    num, den = str(video["r_frame_rate"]).split("/", 1)
    fps = float(num) / float(den)
    return (
        float(payload["format"]["duration"]),
        fps,
        int(video["width"]),
        int(video["height"]),
    )


def _plate_ssim(media_path: Path, plate: H3ResolvedTextPlate) -> float:
    total, fps, width, height = _probe_video(media_path)
    spec = plate.spec
    if spec.end_seconds > total + (1.0 / fps):
        raise RuntimeError(
            f"canonical exact-text window exceeds media duration: {spec.end_seconds} > {total}"
        )

    duration = spec.duration_seconds
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-ss",
            f"{spec.start_seconds:.9f}",
            "-t",
            f"{duration:.9f}",
            "-i",
            str(media_path),
            "-loop",
            "1",
            "-framerate",
            f"{fps:.12f}",
            "-t",
            f"{duration:.9f}",
            "-i",
            str(plate.asset_path),
            "-filter_complex",
            (
                f"[0:v]fps={fps:.12f},format=yuv420p[m];"
                f"[1:v]scale={width}:{height}:flags=lanczos,"
                f"fps={fps:.12f},format=yuv420p[p];"
                "[m][p]ssim"
            ),
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    matches = _SSIM_RE.findall(proc.stderr)
    if not matches:
        raise RuntimeError("ffmpeg did not emit exact-text plate SSIM")
    return float(matches[-1])


def evaluate_h3_exact_text_media(
    media_path: Path,
    *,
    plates: tuple[H3ResolvedTextPlate, ...],
    unit_duration_seconds: float,
) -> tuple[MediaQAFinding, ...]:
    findings: list[MediaQAFinding] = []
    for plate in plates:
        spec = plate.spec
        observed = _plate_ssim(media_path, plate)
        if observed >= spec.ssim_threshold:
            continue
        findings.append(
            MediaQAFinding(
                unit_id=spec.unit_id,
                shot_id=spec.shot_id,
                time_range=MediaQATimeRange(
                    start_seconds=spec.start_seconds,
                    end_seconds=spec.end_seconds,
                ),
                region="full_frame",
                failure_class=H3FailureClass.EXACT_TEXT_REQUIRED,
                canonical_violation=(
                    "canonical exact-text shot is not the SHA-pinned deterministic plate"
                ),
                severity=MediaQASeverity.BLOCKING,
                provider_result_usable=True,
                audio_is_accepted=True,
                repairability=MediaQARepairability.DETERMINISTIC,
                affected_fraction=min(
                    1.0,
                    spec.duration_seconds / unit_duration_seconds,
                ),
                exact_visible_text=spec.exact_text,
                tags=("exact_text_required", "exact_text_mismatch"),
                details=(
                    ("plate_contract_sha256", spec.contract_sha256),
                    ("plate_asset_sha256", spec.asset_sha256),
                    ("observed_plate_ssim", f"{observed:.9f}"),
                    ("required_plate_ssim", f"{spec.ssim_threshold:.9f}"),
                ),
            )
        )
    return tuple(findings)


def _replace_full_frame_window(
    media_path: Path,
    *,
    plate: H3ResolvedTextPlate,
) -> None:
    total, fps, width, height = _probe_video(media_path)
    spec = plate.spec
    if spec.start_seconds < 0 or spec.end_seconds > total + (1.0 / fps):
        raise RuntimeError("deterministic exact-text plate window is outside media duration")

    labels: list[str] = []
    filters: list[str] = []
    if spec.start_seconds > 1e-9:
        filters.append(
            f"[0:v]trim=start=0:end={spec.start_seconds:.9f},"
            "setpts=PTS-STARTPTS[vpre]"
        )
        labels.append("[vpre]")

    filters.append(
        f"[1:v]scale={width}:{height}:flags=lanczos,format=yuv420p,"
        f"trim=duration={spec.duration_seconds:.9f},setpts=PTS-STARTPTS[vplate]"
    )
    labels.append("[vplate]")

    if spec.end_seconds < total - (1.0 / fps):
        filters.append(
            f"[0:v]trim=start={spec.end_seconds:.9f}:end={total:.9f},"
            "setpts=PTS-STARTPTS[vpost]"
        )
        labels.append("[vpost]")

    if len(labels) == 1:
        filters.append(f"{labels[0]}null[v]")
    else:
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[v]")

    temp = media_path.with_name(f".{media_path.stem}.h3-exact-text.tmp.mp4")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(media_path),
        "-loop",
        "1",
        "-framerate",
        f"{fps:.12f}",
        "-i",
        str(plate.asset_path),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-r",
        f"{fps:.12f}",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-t",
        f"{total:.9f}",
        "-movflags",
        "+faststart",
        str(temp),
    ]
    try:
        subprocess.run(command, check=True)
        if not temp.is_file() or temp.stat().st_size == 0:
            raise RuntimeError("deterministic exact-text authoring produced no output")
        os.replace(temp, media_path)
    finally:
        temp.unlink(missing_ok=True)


def build_h3_exact_text_runtime_bundle(
    canonical_director: Mapping[str, Any],
    *,
    unit_id: str,
    project_path: Path,
) -> tuple[
    H3MediaQAEvaluator | None,
    Mapping[H3RepairAction, H3DeterministicRepairHandler],
]:
    """Build exact-text QA/handler only for explicit deterministic plate contracts."""

    bundle = CanonicalDirectorBundle.resolve(canonical_director, unit_id=unit_id)
    raw_duration = bundle.unit.get("duration_sec")
    if (
        not isinstance(raw_duration, (int, float))
        or isinstance(raw_duration, bool)
        or float(raw_duration) <= 0
    ):
        raise ValueError("canonical exact-text runtime requires positive unit duration_sec")
    unit_duration = float(raw_duration)

    specs = exact_text_plate_specs_from_unit(bundle.unit)
    if not specs:
        return None, {}

    resolved: list[H3ResolvedTextPlate] = []
    for spec in specs:
        asset = safe_join(project_path, spec.asset_path, require_file=True)
        actual_sha = sha256_file(asset)
        if actual_sha != spec.asset_sha256:
            raise RuntimeError(
                f"deterministic text plate SHA mismatch for {spec.shot_id}: "
                f"{actual_sha} != {spec.asset_sha256}"
            )
        resolved.append(H3ResolvedTextPlate(spec=spec, asset_path=asset))
    plates = tuple(resolved)
    by_shot = {plate.spec.shot_id: plate for plate in plates}

    async def _evaluator(media_path: Path) -> tuple[MediaQAFinding, ...]:
        return await asyncio.to_thread(
            evaluate_h3_exact_text_media,
            media_path,
            plates=plates,
            unit_duration_seconds=unit_duration,
        )

    def _repair(media_path: Path, plan: H3AutoRepairPlan) -> None:
        shot_id = plan.finding.shot_id
        if not shot_id or shot_id not in by_shot:
            raise RuntimeError("exact-text repair plan does not resolve to a canonical plate")
        _replace_full_frame_window(media_path, plate=by_shot[shot_id])

    return _evaluator, {
        H3RepairAction.DETERMINISTIC_TEXT_PLATE: _repair,
    }
