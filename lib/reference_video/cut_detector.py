"""Actual-media cut detection for canonical shot-boundary verification."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FRAME_RE = re.compile(r"frame:\s*(?P<frame>\d+).*pts_time:(?P<pts_time>-?\d+(?:\.\d+)?)")
_SCORE_RE = re.compile(r"lavfi\.scene_score=(?P<score>\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class CutDetection:
    actual_cut_frame: int
    actual_cut_time: float
    target_cut_frame: int
    target_cut_time: float
    delta_frames: int
    delta_seconds: float
    confidence: float
    evidence: str

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "actual_cut_frame": self.actual_cut_frame,
            "actual_cut_time": self.actual_cut_time,
            "target_cut_frame": self.target_cut_frame,
            "target_cut_time": self.target_cut_time,
            "delta_frames": self.delta_frames,
            "delta_seconds": self.delta_seconds,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def _probe_fps(media_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate",
            "-of",
            "json",
            str(media_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    raw = payload["streams"][0]["avg_frame_rate"]
    numerator, denominator = raw.split("/", maxsplit=1)
    fps = float(numerator) / float(denominator)
    if fps <= 0:
        raise RuntimeError(f"invalid fps: {raw}")
    return fps


def _scene_scores(media_path: Path, fps: float) -> list[tuple[int, float, float]]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(media_path),
            "-vf",
            "select='gte(scene,0)',metadata=print",
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    samples: list[tuple[int, float, float]] = []
    pending_time: float | None = None
    for line in proc.stderr.splitlines():
        frame_match = _FRAME_RE.search(line)
        if frame_match:
            pending_time = float(frame_match.group("pts_time"))
            continue

        score_match = _SCORE_RE.search(line)
        if score_match and pending_time is not None:
            score = float(score_match.group("score"))
            frame = round(pending_time * fps)
            samples.append((frame, pending_time, score))
            pending_time = None

    if not samples:
        raise RuntimeError("ffmpeg did not emit scene scores")
    return samples


def detect_expected_cuts(
    media_path: Path,
    *,
    target_cut_frames: tuple[int, ...],
    search_radius_frames: int = 24,
    min_scene_score: float = 0.15,
) -> tuple[CutDetection, ...]:
    """Detect actual cuts nearest known canonical boundaries.

    Canonical supplies the target boundaries; the media supplies the actual boundary.
    The detector searches scene-score maxima near each target instead of trusting prompt
    timestamps or previously-authored constants.
    """

    if not media_path.is_file():
        raise FileNotFoundError(media_path)
    if not target_cut_frames:
        return ()
    if search_radius_frames < 0:
        raise ValueError("search_radius_frames must be >= 0")
    if not 0.0 <= min_scene_score <= 1.0:
        raise ValueError("min_scene_score must be between 0 and 1")

    fps = _probe_fps(media_path)
    samples = _scene_scores(media_path, fps)
    detections: list[CutDetection] = []

    for target in target_cut_frames:
        candidates = [
            sample for sample in samples if abs(sample[0] - target) <= search_radius_frames
        ]
        if not candidates:
            raise RuntimeError(f"no scene-score samples near target frame {target}")

        actual_frame, actual_time, score = max(candidates, key=lambda sample: sample[2])
        if score < min_scene_score:
            raise RuntimeError(
                f"no confident cut near target frame {target}; max scene score={score:.6f}"
            )

        target_time = target / fps
        delta_frames = actual_frame - target
        detections.append(
            CutDetection(
                actual_cut_frame=actual_frame,
                actual_cut_time=actual_time,
                target_cut_frame=target,
                target_cut_time=target_time,
                delta_frames=delta_frames,
                delta_seconds=actual_time - target_time,
                confidence=score,
                evidence=(
                    f"ffmpeg lavfi.scene_score={score:.6f}; "
                    f"search_radius_frames={search_radius_frames}"
                ),
            )
        )

    return tuple(detections)
