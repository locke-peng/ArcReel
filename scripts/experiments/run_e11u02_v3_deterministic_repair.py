"""Deterministic E11U02 v3 repair over immutable v2 MiniMax H3 supplier outputs.

This script does NOT call the provider. It consumes the exact paid v2 supplier evidence,
verifies SHA-256 provenance, removes non-canonical text-bearing surfaces deterministically,
re-authors the exact 5s+5s+5s timeline, and preserves the detached canonical soundtrack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

UNIT_ID = "E11U02"
UPSTREAM_RUN_ID = 36148270693
UPSTREAM_ARTIFACT_ID = 10870732082
UPSTREAM_ARTIFACT_NAME = "e11u02-v2-zero-text-physical-state-evidence"
UPSTREAM_HEAD_SHA = "e3d5e8abd053442c5981ca76ff4e57a6a84beae4"

FPS = 24
SHOT_SECONDS = 5
DURATION_SECONDS = 15
WIDTH = 864
HEIGHT = 480

UPSTREAM_SHA256 = {
    "shot1": "aecded93bd579ea89cb65f1f7c431446f55c4eac516ce85f90964a408d027a48",
    "shot2": "7effe252c0c0384a7697002d8d095b95cbade03f695949d46e014d2816091507",
    "shot3": "ad6dc5cec862220754b9ba082cdf12f2fb3e569e8777873294e7231b728b9751",
    "soundtrack": "dd8be354040d959ff7e94b2c6e7220148373a2c10c897b88d0b8c6984d9486d2",
}

# These are screen-surface bounds from the exact SHA-pinned Shot 1 supplier plate.
# They are intentionally limited to display surfaces; the foreground physical
# status indicator is not touched.
SHOT1_SCREEN_RECTS = (
    (0, 45, 90, 270),
    (345, 135, 495, 245),
    (250, 245, 370, 350),
    (316, 228, 370, 275),
    (470, 230, 530, 280),
    (515, 235, 568, 345),
    (595, 245, 660, 335),
    (690, 125, 855, 275),
)

# Time-varying badge-label defocus bounds for the exact SHA-pinned Shot 2 plate.
# The source badge remains physically present; only the hallucinated printed/logo
# region is defocused. Canonical specifies the guest badge but no badge typography.
SHOT2_LABEL_KEYFRAMES = (
    (0.00, None),
    (0.45, None),
    (0.60, (540, 75, 740, 205)),
    (0.75, (510, 85, 720, 200)),
    (1.00, (350, 80, 550, 220)),
    (1.25, (210, 95, 410, 245)),
    (1.50, (245, 140, 420, 290)),
    (1.75, (285, 185, 410, 315)),
    (2.00, (260, 235, 420, 360)),
    (2.25, (245, 265, 425, 395)),
    (2.75, (245, 270, 420, 395)),
    (5.00, (245, 270, 420, 395)),
)

# Side-media defocus protects incidental supporting badges / camera displays while
# keeping the canonical C02/C04 rear silhouettes sharp in the center.
SHOT3_LEFT_FULL = 210
SHOT3_LEFT_FEATHER_END = 260
SHOT3_RIGHT_FEATHER_START = 625
SHOT3_RIGHT_FULL = 675
SHOT3_EXIT_SIGN_RECT = (430, 35, 500, 90)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _ffprobe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(proc.stdout)


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing upstream {label}: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA mismatch: {actual} != {expected}")


def _shot2_rect_for(t: float) -> tuple[int, int, int, int] | None:
    if t < SHOT2_LABEL_KEYFRAMES[0][0]:
        return None
    for (t0, r0), (t1, r1) in zip(
        SHOT2_LABEL_KEYFRAMES,
        SHOT2_LABEL_KEYFRAMES[1:],
        strict=True,
    ):
        if t0 <= t <= t1:
            if r0 is None and r1 is None:
                return None
            if r0 is None:
                return r1
            if r1 is None:
                return r0
            if t1 == t0:
                return r1
            alpha = (t - t0) / (t1 - t0)
            return tuple(
                int(round(r0[idx] * (1.0 - alpha) + r1[idx] * alpha))
                for idx in range(4)
            )
    return SHOT2_LABEL_KEYFRAMES[-1][1]


def _extract_first_five_seconds(source: Path, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-t",
        str(SHOT_SECONDS),
        "-vf",
        f"fps={FPS}",
        str(frames_dir / "frame_%04d.png"),
    )
    frames = sorted(frames_dir.glob("frame_*.png"))
    expected = FPS * SHOT_SECONDS
    if len(frames) != expected:
        raise RuntimeError(f"expected {expected} frames, got {len(frames)} from {source}")


def _encode_frames(frames_dir: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(frames_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-t",
        str(SHOT_SECONDS),
        str(output),
    )


def _repair_shot1(source: Path, output: Path, workdir: Path) -> None:
    frames_dir = workdir / "shot1_frames"
    _extract_first_five_seconds(source, frames_dir)
    for frame_path in sorted(frames_dir.glob("frame_*.png")):
        image = Image.open(frame_path).convert("RGB")
        for rect in SHOT1_SCREEN_RECTS:
            crop = image.crop(rect).filter(ImageFilter.GaussianBlur(radius=18))
            image.paste(crop, rect[:2])
        image.save(frame_path, format="PNG")
    _encode_frames(frames_dir, output)


def _repair_shot2(source: Path, output: Path, workdir: Path) -> None:
    frames_dir = workdir / "shot2_frames"
    _extract_first_five_seconds(source, frames_dir)
    for frame_index, frame_path in enumerate(sorted(frames_dir.glob("frame_*.png"))):
        t = frame_index / FPS
        image = Image.open(frame_path).convert("RGB")
        rect = _shot2_rect_for(t)
        if rect is not None:
            crop = image.crop(rect).filter(ImageFilter.GaussianBlur(radius=24))
            image.paste(crop, rect[:2])
        image.save(frame_path, format="PNG")
    _encode_frames(frames_dir, output)


def _shot3_defocus_mask() -> Image.Image:
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 0, SHOT3_LEFT_FULL, HEIGHT), fill=255)
    draw.rectangle((SHOT3_RIGHT_FULL, 0, WIDTH, HEIGHT), fill=255)

    left_span = SHOT3_LEFT_FEATHER_END - SHOT3_LEFT_FULL
    for x in range(SHOT3_LEFT_FULL, SHOT3_LEFT_FEATHER_END):
        value = int(round(255 * (SHOT3_LEFT_FEATHER_END - x) / left_span))
        draw.line((x, 0, x, HEIGHT), fill=value)

    right_span = SHOT3_RIGHT_FULL - SHOT3_RIGHT_FEATHER_START
    for x in range(SHOT3_RIGHT_FEATHER_START, SHOT3_RIGHT_FULL):
        value = int(round(255 * (x - SHOT3_RIGHT_FEATHER_START) / right_span))
        draw.line((x, 0, x, HEIGHT), fill=value)

    draw.rectangle(SHOT3_EXIT_SIGN_RECT, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=6))


def _repair_shot3(source: Path, output: Path, workdir: Path) -> None:
    frames_dir = workdir / "shot3_frames"
    _extract_first_five_seconds(source, frames_dir)
    mask = _shot3_defocus_mask()
    for frame_path in sorted(frames_dir.glob("frame_*.png")):
        image = Image.open(frame_path).convert("RGB")
        blurred = image.filter(ImageFilter.GaussianBlur(radius=9))
        image = Image.composite(blurred, image, mask)
        image.save(frame_path, format="PNG")
    _encode_frames(frames_dir, output)


def _author_final(
    shot1: Path,
    shot2: Path,
    shot3: Path,
    soundtrack: Path,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(shot1),
        "-i",
        str(shot2),
        "-i",
        str(shot3),
        "-i",
        str(soundtrack),
        "-filter_complex",
        (
            "[0:v]setpts=PTS-STARTPTS,format=yuv420p[v0];"
            "[1:v]setpts=PTS-STARTPTS,format=yuv420p[v1];"
            "[2:v]setpts=PTS-STARTPTS,format=yuv420p[v2];"
            "[v0][v1][v2]concat=n=3:v=1:a=0[v]"
        ),
        "-map",
        "[v]",
        "-map",
        "3:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-t",
        str(DURATION_SECONDS),
        "-movflags",
        "+faststart",
        str(output),
    )


def _resolve_upstream(upstream_dir: Path) -> dict[str, Path]:
    files = {
        "shot1": upstream_dir / "E11U02_SHOT1_provider_raw.mp4",
        "shot2": upstream_dir / "E11U02_SHOT2_provider_raw.mp4",
        "shot3": upstream_dir / "E11U02_SHOT3_provider_raw.mp4",
        "soundtrack": upstream_dir / "project" / "fixtures" / "E11U02_canonical_soundtrack.wav",
    }
    for key, path in files.items():
        _require_hash(path, UPSTREAM_SHA256[key], key)
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("live_artifacts") / UNIT_ID)
    args = parser.parse_args()

    upstream = _resolve_upstream(args.upstream_dir)
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=True)
    project = root / "project"
    plates_dir = project / "fixtures"
    final_dir = project / "reference_videos"
    plates_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="e11u02_v3_") as temp_name:
        workdir = Path(temp_name)
        shot1 = plates_dir / "E11U02_v3_shot1_text_scrubbed.mp4"
        shot2 = plates_dir / "E11U02_v3_shot2_badge_scrubbed.mp4"
        shot3 = plates_dir / "E11U02_v3_shot3_media_defocused.mp4"

        _repair_shot1(upstream["shot1"], shot1, workdir)
        _repair_shot2(upstream["shot2"], shot2, workdir)
        _repair_shot3(upstream["shot3"], shot3, workdir)

    soundtrack_copy = plates_dir / "E11U02_canonical_soundtrack.wav"
    shutil.copy2(upstream["soundtrack"], soundtrack_copy)
    final_video = final_dir / "E11U02.mp4"
    _author_final(shot1, shot2, shot3, soundtrack_copy, final_video)

    probe = _ffprobe(final_video)
    duration = float(probe["format"]["duration"])
    video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")

    if abs(duration - DURATION_SECONDS) > 0.05:
        raise RuntimeError(f"unexpected final duration: {duration}")
    if (video_stream.get("width"), video_stream.get("height")) != (WIDTH, HEIGHT):
        raise RuntimeError(f"unexpected final resolution: {video_stream}")
    if audio_stream.get("codec_name") != "aac":
        raise RuntimeError(f"unexpected final audio codec: {audio_stream}")

    report = {
        "status": "DETERMINISTIC_REPAIR_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v3_deterministic_text_surface_scrub",
        "source_supplier_run_id": UPSTREAM_RUN_ID,
        "source_supplier_artifact_id": UPSTREAM_ARTIFACT_ID,
        "source_supplier_artifact_name": UPSTREAM_ARTIFACT_NAME,
        "source_supplier_head_sha": UPSTREAM_HEAD_SHA,
        "source_supplier_hashes": UPSTREAM_SHA256,
        "provider_recalled": False,
        "repair_layers": {
            "shot1": "deterministic Gaussian defocus only on SHA-pinned screen surfaces; physical stable-status indicator preserved",
            "shot2": "deterministic time-varying defocus over hallucinated badge typography/logo region; badge action preserved",
            "shot3": "deterministic side-media and exit-sign defocus; central C02/C04 rear silhouettes preserved",
        },
        "canonical_visible_text": [],
        "canonical_dialogue_audio_reused": [
            "通过了",
            "明天见真章",
            "陆氏会合作吗",
        ],
        "timeline_seconds": [5, 5, 5],
        "final_probe": probe,
        "processed_plate_sha256": {
            "shot1": _sha256(shot1),
            "shot2": _sha256(shot2),
            "shot3": _sha256(shot3),
            "soundtrack": _sha256(soundtrack_copy),
        },
        "final_video_sha256": _sha256(final_video),
        "final_video_size_bytes": final_video.stat().st_size,
        "github_sha": os.environ.get("GITHUB_SHA"),
    }
    (root / "E11U02_v3_repair_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "ffprobe_final.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
