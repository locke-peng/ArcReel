"""Deterministic post-generation sanitization for accepted-motion E11U02 v2 evidence.

This stage performs no provider call. It verifies the exact v2 final video SHA,
pixelates only known text-risk surfaces, preserves the authored 5s+5s+5s
timeline and source audio, then emits a v3 candidate for dense visual review.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

UNIT_ID = "E11U02"
SOURCE_VIDEO_SHA256 = "edff353aa05833b3fb523f2ec48b7b58adbd6e7aba1bdccd71f5a0142dde5055"
EXPECTED_DURATION_SECONDS = 15.0
EXPECTED_WIDTH = 864
EXPECTED_HEIGHT = 480
EXPECTED_FPS = 24.0


@dataclass(frozen=True)
class PixelateMask:
    name: str
    start: float
    end: float
    x: int
    y: int
    width: int
    height: int
    block: int = 12


MASKS: tuple[PixelateMask, ...] = (
    # Shot 1: screen/UI surfaces. Preserve the physical green indicator ring.
    PixelateMask("shot1_left_wall_display", 0.0, 5.0, 0, 55, 105, 190, 10),
    PixelateMask("shot1_rear_center_display", 0.0, 5.0, 340, 125, 170, 110, 10),
    PixelateMask("shot1_front_left_display", 0.0, 5.0, 220, 245, 125, 100, 10),
    PixelateMask("shot1_front_right_display", 0.0, 5.0, 520, 240, 85, 100, 10),
    PixelateMask("shot1_far_right_display", 0.0, 5.0, 695, 125, 140, 165, 10),
    PixelateMask("shot1_indicator_inner_screen", 0.0, 5.0, 410, 268, 55, 32, 8),
    # Shot 2: moving printed badge label. The blank badge body, hands and cord remain visible.
    PixelateMask("shot2_badge_label_entry", 5.50, 6.00, 480, 70, 255, 165, 14),
    PixelateMask("shot2_badge_label_turn", 6.00, 6.50, 205, 90, 225, 180, 14),
    PixelateMask("shot2_badge_label_lowering", 6.50, 7.00, 270, 180, 160, 145, 12),
    PixelateMask("shot2_badge_label_resting", 7.00, 10.00, 235, 245, 180, 160, 12),
    PixelateMask("shot2_badge_lower_microprint", 7.00, 10.00, 145, 360, 75, 65, 10),
    # Shot 3: corridor exit/signage surface. Reporter badges remain too small to read at delivery size.
    PixelateMask("shot3_exit_sign", 10.80, 15.00, 665, 42, 80, 58, 8),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict:
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
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def _filter_graph() -> str:
    parts: list[str] = ["[0:v]setpts=PTS-STARTPTS[v0]"]
    current = "v0"
    for idx, mask in enumerate(MASKS):
        base = f"base{idx}"
        crop = f"crop{idx}"
        pix = f"pix{idx}"
        nxt = f"v{idx + 1}"
        small_w = max(1, mask.width // mask.block)
        small_h = max(1, mask.height // mask.block)
        parts.append(f"[{current}]split=2[{base}][{crop}]")
        parts.append(
            f"[{crop}]crop={mask.width}:{mask.height}:{mask.x}:{mask.y},"
            f"scale={small_w}:{small_h}:flags=area,"
            f"scale={mask.width}:{mask.height}:flags=neighbor[{pix}]"
        )
        parts.append(
            f"[{base}][{pix}]overlay={mask.x}:{mask.y}:"
            f"enable='between(t,{mask.start:.2f},{mask.end:.2f})'[{nxt}]"
        )
        current = nxt
    parts.append(f"[{current}]format=yuv420p[vout]")
    return ";".join(parts)


def sanitize(source: Path, output: Path) -> dict:
    if not source.is_file():
        raise RuntimeError(f"missing pinned E11U02 v2 source video: {source}")
    source_sha = sha256_file(source)
    if source_sha != SOURCE_VIDEO_SHA256:
        raise RuntimeError(
            f"E11U02 v2 source SHA mismatch: {source_sha} != {SOURCE_VIDEO_SHA256}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            _filter_graph(),
            "-map",
            "[vout]",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-r",
            "24",
            "-c:a",
            "copy",
            "-t",
            "15",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("E11U02 v3 sanitizer produced no output")

    metadata = probe(output)
    duration = float(metadata["format"]["duration"])
    video_stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in metadata["streams"] if s["codec_type"] == "audio")
    if abs(duration - EXPECTED_DURATION_SECONDS) > 0.05:
        raise RuntimeError(f"unexpected E11U02 v3 duration: {duration}")
    if int(video_stream["width"]) != EXPECTED_WIDTH or int(video_stream["height"]) != EXPECTED_HEIGHT:
        raise RuntimeError(
            f"unexpected E11U02 v3 resolution: {video_stream['width']}x{video_stream['height']}"
        )
    if video_stream["codec_name"] != "h264":
        raise RuntimeError(f"unexpected E11U02 v3 video codec: {video_stream['codec_name']}")
    if audio_stream["codec_name"] != "aac":
        raise RuntimeError(f"unexpected E11U02 v3 audio codec: {audio_stream['codec_name']}")

    return {
        "status": "SANITIZED_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v3_deterministic_text_surface_sanitization",
        "source_run_id": 36148270693,
        "source_commit": "e3d5e8abd053442c5981ca76ff4e57a6a84beae4",
        "source_video_sha256": source_sha,
        "sanitizer_contract": {
            "supplier_reused": True,
            "new_paid_provider_calls": 0,
            "timeline_reauthored": False,
            "audio_reused_bitstream": True,
            "masked_surfaces": [asdict(mask) for mask in MASKS],
        },
        "final_duration_seconds": duration,
        "final_resolution": f"{video_stream['width']}x{video_stream['height']}",
        "video_codec": video_stream["codec_name"],
        "audio_codec": audio_stream["codec_name"],
        "audio_sample_rate": audio_stream.get("sample_rate"),
        "audio_channels": audio_stream.get("channels"),
        "final_video_sha256": sha256_file(output),
        "final_video_size_bytes": output.stat().st_size,
    }


def main() -> None:
    source = Path("v2_evidence/project/reference_videos/E11U02.mp4")
    root = Path("live_artifacts/E11U02_v3")
    output = root / "project/reference_videos/E11U02.mp4"
    report = sanitize(source, output)
    root.mkdir(parents=True, exist_ok=True)
    (root / "E11U02_v3_sanitization_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "ffprobe_final.json").write_text(
        json.dumps(probe(output), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
