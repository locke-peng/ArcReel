"""Canonical timeline Media QA and deterministic A/V retime for H3 runtime repair."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.reference_video.cut_detector import detect_expected_cuts, probe_video_fps
from lib.reference_video.h3_auto_repair_loop import H3AutoRepairPlan
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
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
class H3CanonicalTimeline:
    unit_id: str
    duration_seconds: float
    target_cut_times: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id is required")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")
        previous = 0.0
        for cut in self.target_cut_times:
            if not 0.0 < cut < self.duration_seconds:
                raise ValueError("target cuts must fall strictly inside the unit duration")
            if cut <= previous:
                raise ValueError("target cuts must be strictly increasing")
            previous = cut


def canonical_timeline_from_director(
    canonical_director: Mapping[str, Any],
    *,
    unit_id: str,
) -> H3CanonicalTimeline:
    """Resolve trusted Canonical Director shot starts into target editorial boundaries."""

    bundle = CanonicalDirectorBundle.resolve(canonical_director, unit_id=unit_id)
    unit = bundle.unit
    raw_shots = unit.get("shots")
    if not isinstance(raw_shots, Sequence) or isinstance(raw_shots, (str, bytes)):
        raise ValueError("canonical director unit requires shots")
    shots = [shot for shot in raw_shots if isinstance(shot, Mapping)]
    if not shots:
        raise ValueError("canonical director unit requires non-empty shots")

    starts = tuple(float(shot.get("start_sec") or 0.0) for shot in shots)
    if abs(starts[0]) > 1e-6:
        raise ValueError("first canonical shot must start at 0")
    if any(right <= left for left, right in zip(starts, starts[1:])):
        raise ValueError("canonical shot starts must be strictly increasing")

    raw_duration = unit.get("duration_sec")
    if isinstance(raw_duration, (int, float)) and not isinstance(raw_duration, bool):
        duration = float(raw_duration)
    else:
        last_end = shots[-1].get("end_sec")
        if not isinstance(last_end, (int, float)) or isinstance(last_end, bool):
            raise ValueError("canonical director unit requires duration_sec or final end_sec")
        duration = float(last_end)

    return H3CanonicalTimeline(
        unit_id=unit_id,
        duration_seconds=duration,
        target_cut_times=starts[1:],
    )


def _video_stream_facts(media_path: Path) -> tuple[int, int | None, int | None]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,nb_read_frames,sample_rate,channels",
            "-of",
            "json",
            str(media_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    streams = payload.get("streams") or []
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if not isinstance(video, Mapping):
        raise RuntimeError("media has no video stream")
    raw_frames = video.get("nb_read_frames")
    if raw_frames in {None, "N/A"}:
        raise RuntimeError("ffprobe could not count video frames")
    frame_count = int(raw_frames)

    audio = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    if not isinstance(audio, Mapping):
        return frame_count, None, None

    raw_sample_rate = audio.get("sample_rate")
    raw_channels = audio.get("channels")
    sample_rate = int(raw_sample_rate) if raw_sample_rate not in {None, "N/A"} else None
    channels = int(raw_channels) if raw_channels not in {None, "N/A"} else None
    return frame_count, sample_rate, channels


def _target_cut_frames(timeline: H3CanonicalTimeline, fps: float) -> tuple[int, ...]:
    return tuple(round(value * fps) for value in timeline.target_cut_times)


def evaluate_h3_timeline_media(
    media_path: Path,
    *,
    timeline: H3CanonicalTimeline,
    tolerance_frames: int = 0,
    search_radius_seconds: float = 1.0,
    min_scene_score: float = 0.15,
) -> tuple[MediaQAFinding, ...]:
    """Return one timing-only finding when actual hard cuts miss Canonical boundaries."""

    if tolerance_frames < 0:
        raise ValueError("tolerance_frames must be >= 0")
    if search_radius_seconds < 0:
        raise ValueError("search_radius_seconds must be >= 0")
    if not timeline.target_cut_times:
        return ()

    fps = probe_video_fps(media_path)
    targets = _target_cut_frames(timeline, fps)
    radius = max(1, round(search_radius_seconds * fps))
    try:
        cuts = detect_expected_cuts(
            media_path,
            target_cut_frames=targets,
            search_radius_frames=radius,
            min_scene_score=min_scene_score,
        )
    except RuntimeError as exc:
        return (
            MediaQAFinding(
                unit_id=timeline.unit_id,
                canonical_violation=(
                    "canonical shot boundaries could not be verified from actual media cuts"
                ),
                severity=MediaQASeverity.BLOCKING,
                provider_result_usable=True,
                audio_is_accepted=True,
                repairability=MediaQARepairability.HUMAN_REVIEW,
                affected_fraction=1.0,
                tags=("cut_detection_unresolved",),
                details=(("cut_detector_error", str(exc)),),
            ),
        )

    deltas = tuple(cut.delta_frames for cut in cuts)
    if all(abs(delta) <= tolerance_frames for delta in deltas):
        return ()

    return (
        MediaQAFinding(
            unit_id=timeline.unit_id,
            canonical_violation=(
                "actual media cuts do not land on canonical shot boundaries"
            ),
            severity=MediaQASeverity.BLOCKING,
            provider_result_usable=True,
            audio_is_accepted=True,
            repairability=MediaQARepairability.DETERMINISTIC,
            affected_fraction=1.0,
            failure_class=H3FailureClass.TIMELINE_ONLY_FAILURE,
            evidence_frames=tuple(cut.actual_cut_frame for cut in cuts),
            tags=("cut_timing",),
            details=(
                (
                    "actual_cut_frames",
                    json.dumps([cut.actual_cut_frame for cut in cuts]),
                ),
                (
                    "target_cut_frames",
                    json.dumps([cut.target_cut_frame for cut in cuts]),
                ),
            ),
        ),
    )


def _atempo_factor(value: float) -> str:
    if not 0.5 <= value <= 2.0:
        raise RuntimeError(
            f"deterministic A/V retime requires atempo within 0.5..2.0; got {value}"
        )
    return f"{value:.12f}"


def retime_h3_media_to_canonical_timeline(
    media_path: Path,
    *,
    timeline: H3CanonicalTimeline,
    search_radius_seconds: float = 1.0,
    min_scene_score: float = 0.15,
) -> None:
    """Retime picture and matching audio in place to Canonical shot boundaries."""

    if not media_path.is_file():
        raise FileNotFoundError(media_path)
    if not timeline.target_cut_times:
        return

    fps = probe_video_fps(media_path)
    target_cuts = _target_cut_frames(timeline, fps)
    radius = max(1, round(search_radius_seconds * fps))
    detections = detect_expected_cuts(
        media_path,
        target_cut_frames=target_cuts,
        search_radius_frames=radius,
        min_scene_score=min_scene_score,
    )
    actual_cuts = tuple(cut.actual_cut_frame for cut in detections)

    source_frame_count, sample_rate, channels = _video_stream_facts(media_path)
    target_frame_count = round(timeline.duration_seconds * fps)
    source_boundaries = (0, *actual_cuts, source_frame_count)
    target_boundaries = (0, *target_cuts, target_frame_count)

    if len(source_boundaries) != len(target_boundaries):
        raise RuntimeError("source and target timeline segment counts differ")

    source_segments = tuple(
        right - left for left, right in zip(source_boundaries, source_boundaries[1:])
    )
    target_segments = tuple(
        right - left for left, right in zip(target_boundaries, target_boundaries[1:])
    )
    if any(frames <= 0 for frames in (*source_segments, *target_segments)):
        raise RuntimeError("timeline contains an empty or reversed segment")

    has_audio = sample_rate is not None and channels is not None
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, (source_start, source_end, source_frames, target_frames) in enumerate(
        zip(
            source_boundaries,
            source_boundaries[1:],
            source_segments,
            target_segments,
        )
    ):
        start_seconds = source_start / fps
        end_seconds = source_end / fps
        pts_factor = target_frames / source_frames
        filters.append(
            f"[0:v]trim=start={start_seconds:.9f}:end={end_seconds:.9f},"
            f"setpts=(PTS-STARTPTS)*{pts_factor:.12f},fps={fps:.12f}[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
        if has_audio:
            atempo = source_frames / target_frames
            filters.append(
                f"[0:a]atrim=start={start_seconds:.9f}:end={end_seconds:.9f},"
                "asetpts=PTS-STARTPTS,"
                f"atempo={_atempo_factor(atempo)}[a{index}]"
            )
            concat_inputs.append(f"[a{index}]")

    concat = "".join(concat_inputs)
    filters.append(
        f"{concat}concat=n={len(source_segments)}:v=1:a={1 if has_audio else 0}"
        + ("[v][a]" if has_audio else "[v]")
    )

    temp = media_path.with_name(f".{media_path.stem}.h3-retime.tmp.mp4")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(media_path),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
    ]
    if has_audio:
        command.extend(["-map", "[a]"])
    command.extend(
        [
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
        ]
    )
    if has_audio:
        command.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                str(sample_rate),
                "-ac",
                str(channels),
            ]
        )
    command.extend(
        [
            "-t",
            f"{target_frame_count / fps:.9f}",
            "-movflags",
            "+faststart",
            str(temp),
        ]
    )

    try:
        subprocess.run(command, check=True)
        if not temp.is_file() or temp.stat().st_size == 0:
            raise RuntimeError("deterministic A/V retime produced no output")
        os.replace(temp, media_path)
    finally:
        temp.unlink(missing_ok=True)


def build_h3_timeline_runtime_bundle(
    canonical_director: Mapping[str, Any],
    *,
    unit_id: str,
    tolerance_frames: int = 0,
    search_radius_seconds: float = 1.0,
    min_scene_score: float = 0.15,
) -> tuple[
    H3MediaQAEvaluator,
    Mapping[H3RepairAction, H3DeterministicRepairHandler],
]:
    """Build a trusted timeline-only evaluator/handler pair from Canonical Director."""

    timeline = canonical_timeline_from_director(canonical_director, unit_id=unit_id)

    async def _evaluator(media_path: Path) -> tuple[MediaQAFinding, ...]:
        return await asyncio.to_thread(
            evaluate_h3_timeline_media,
            media_path,
            timeline=timeline,
            tolerance_frames=tolerance_frames,
            search_radius_seconds=search_radius_seconds,
            min_scene_score=min_scene_score,
        )

    def _repair(media_path: Path, _plan: H3AutoRepairPlan) -> None:
        retime_h3_media_to_canonical_timeline(
            media_path,
            timeline=timeline,
            search_radius_seconds=search_radius_seconds,
            min_scene_score=min_scene_score,
        )

    return _evaluator, {
        H3RepairAction.DETERMINISTIC_AV_RETIME: _repair,
    }
