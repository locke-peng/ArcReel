"""Deterministic E15U03 timeline repair over the accepted MiniMax H3 supplier video.

The supplier render has correct content and C01 identity but its authored visual cuts land at
frame 118 (~4.9167s) and frame 222 (9.25s), so Shot 07 is too short. This stage never recalls
the provider. It verifies exact upstream bytes and deterministically retimes both picture and
sound so the three canonical beats occupy exactly 5s + 5s + 5s.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

UNIT_ID = "E15U03"

SOURCE_SUPPLIER_RUN_ID = 36009732060
SOURCE_SUPPLIER_ARTIFACT_ID = 10812256991
SOURCE_SUPPLIER_ARTIFACT_NAME = "supplier-e15u03-evidence"
SOURCE_SUPPLIER_HEAD_SHA = "a5c192427d47c94fe9e60c9c0e5ca62aa35b4be8"
SOURCE_SUPPLIER_TASK_ID = "53944e96-e4b3-465f-b046-a8b6f111de3b"

SOURCE_PROMPT_SHA256 = "b8143dfe1e500a83d6f45f0ca133cf3fed9ab55c7ab6739686c11b0f1eb87dd0"
SOURCE_VIDEO_SHA256 = "17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36"
SOURCE_REFERENCE_SHA256 = (
    "87d54ccd76abd21e2a03e83036cac6af9469b6de50614a44c67196d0e8b9674a",
    "50893f22ed6e38bd3764f088ec2cd7e1f5ccecaaadd707e0d63ee2e217782bb9",
)
SOURCE_C01_IDENTITY_SHA256 = SOURCE_REFERENCE_SHA256[1]

FPS = 24
WIDTH = 864
HEIGHT = 480
SHOT_SECONDS = 5
DURATION_SECONDS = 15
TARGET_SHOT_FRAMES = FPS * SHOT_SECONDS

# Hard cuts measured on the exact supplier bytes.
SHOT1_SOURCE_END_FRAME = 118
SHOT2_SOURCE_START_FRAME = 118
SHOT2_SOURCE_END_FRAME = 222
SHOT3_SOURCE_START_FRAME = 222
SHOT3_SOURCE_END_FRAME = 342

SHOT1_SOURCE_FRAMES = SHOT1_SOURCE_END_FRAME
SHOT2_SOURCE_FRAMES = SHOT2_SOURCE_END_FRAME - SHOT2_SOURCE_START_FRAME
SHOT3_SOURCE_FRAMES = SHOT3_SOURCE_END_FRAME - SHOT3_SOURCE_START_FRAME

SHOT1_SOURCE_SECONDS = SHOT1_SOURCE_FRAMES / FPS
SHOT2_SOURCE_SECONDS = SHOT2_SOURCE_FRAMES / FPS
SHOT3_SOURCE_SECONDS = SHOT3_SOURCE_FRAMES / FPS

SHOT1_VIDEO_PTS_FACTOR = SHOT_SECONDS / SHOT1_SOURCE_SECONDS
SHOT2_VIDEO_PTS_FACTOR = SHOT_SECONDS / SHOT2_SOURCE_SECONDS
SHOT3_VIDEO_PTS_FACTOR = SHOT_SECONDS / SHOT3_SOURCE_SECONDS

SHOT1_AUDIO_TEMPO = SHOT1_SOURCE_SECONDS / SHOT_SECONDS
SHOT2_AUDIO_TEMPO = SHOT2_SOURCE_SECONDS / SHOT_SECONDS
SHOT3_AUDIO_TEMPO = SHOT3_SOURCE_SECONDS / SHOT_SECONDS

CANONICAL_VISIBLE_TEXT = ("TIANSHU NEXT",)


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


def _verify_upstream(upstream_dir: Path) -> tuple[Path, Path]:
    video = upstream_dir / "E15U03.mp4"
    prompt = upstream_dir / "final_prompt.txt"
    summary = upstream_dir / "live_test_summary.json"

    if not video.is_file() or not prompt.is_file() or not summary.is_file():
        raise RuntimeError("E15U03 supplier evidence is incomplete")

    actual_video_sha = _sha256(video)
    if actual_video_sha != SOURCE_VIDEO_SHA256:
        raise RuntimeError(
            f"E15U03 supplier video SHA mismatch: {actual_video_sha} != {SOURCE_VIDEO_SHA256}"
        )

    actual_prompt_sha = _sha256(prompt)
    if actual_prompt_sha != SOURCE_PROMPT_SHA256:
        raise RuntimeError(
            f"E15U03 prompt SHA mismatch: {actual_prompt_sha} != {SOURCE_PROMPT_SHA256}"
        )

    data = json.loads(summary.read_text(encoding="utf-8"))
    if data.get("task_id") != SOURCE_SUPPLIER_TASK_ID:
        raise RuntimeError("E15U03 supplier task_id mismatch")
    if data.get("supplier_status") != "SUCCESS":
        raise RuntimeError("E15U03 upstream supplier status is not SUCCESS")
    if tuple(data.get("reference_sha256") or ()) != SOURCE_REFERENCE_SHA256:
        raise RuntimeError("E15U03 reference SHA list mismatch")
    if data.get("video_sha256") != SOURCE_VIDEO_SHA256:
        raise RuntimeError("E15U03 summary video SHA mismatch")
    if data.get("prompt_sha256") != SOURCE_PROMPT_SHA256:
        raise RuntimeError("E15U03 summary prompt SHA mismatch")

    return video, prompt


def _author_exact_timeline(source_video: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    cut1 = SHOT1_SOURCE_END_FRAME / FPS
    cut2 = SHOT2_SOURCE_END_FRAME / FPS
    shot3_end = SHOT3_SOURCE_END_FRAME / FPS

    filter_complex = (
        f"[0:v]trim=start=0:end={cut1:.9f},"
        f"setpts=(PTS-STARTPTS)*{SHOT1_VIDEO_PTS_FACTOR:.12f},fps={FPS}[v0];"
        f"[0:a]atrim=start=0:end={cut1:.9f},asetpts=PTS-STARTPTS,"
        f"atempo={SHOT1_AUDIO_TEMPO:.12f}[a0];"
        f"[0:v]trim=start={cut1:.9f}:end={cut2:.9f},"
        f"setpts=(PTS-STARTPTS)*{SHOT2_VIDEO_PTS_FACTOR:.12f},fps={FPS}[v1];"
        f"[0:a]atrim=start={cut1:.9f}:end={cut2:.9f},asetpts=PTS-STARTPTS,"
        f"atempo={SHOT2_AUDIO_TEMPO:.12f}[a1];"
        f"[0:v]trim=start={cut2:.9f}:end={shot3_end:.9f},"
        f"setpts=(PTS-STARTPTS)*{SHOT3_VIDEO_PTS_FACTOR:.12f},fps={FPS}[v2];"
        f"[0:a]atrim=start={cut2:.9f}:end={shot3_end:.9f},asetpts=PTS-STARTPTS,"
        f"atempo={SHOT3_AUDIO_TEMPO:.12f}[a2];"
        "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]"
    )

    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_video),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
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
        "-ar",
        "32000",
        "-ac",
        "2",
        "-t",
        str(DURATION_SECONDS),
        "-movflags",
        "+faststart",
        str(output),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("live_artifacts") / UNIT_ID)
    args = parser.parse_args()

    source_video, prompt = _verify_upstream(args.upstream_dir)

    root = args.output_dir
    project = root / "project"
    final_dir = project / "reference_videos"
    evidence_dir = project / "fixtures"
    final_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    source_copy = evidence_dir / "E15U03_supplier_source.mp4"
    prompt_copy = evidence_dir / "E15U03_supplier_prompt.txt"
    shutil.copy2(source_video, source_copy)
    shutil.copy2(prompt, prompt_copy)

    final_video = final_dir / "E15U03.mp4"
    _author_exact_timeline(source_copy, final_video)

    probe = _ffprobe(final_video)
    duration = float(probe["format"]["duration"])
    video_stream = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")

    if abs(duration - DURATION_SECONDS) > 0.05:
        raise RuntimeError(f"unexpected E15U03 final duration: {duration}")
    if (video_stream.get("width"), video_stream.get("height")) != (WIDTH, HEIGHT):
        raise RuntimeError(f"unexpected E15U03 final resolution: {video_stream}")
    if video_stream.get("codec_name") != "h264":
        raise RuntimeError(f"unexpected E15U03 video codec: {video_stream}")
    if audio_stream.get("codec_name") != "aac":
        raise RuntimeError(f"unexpected E15U03 audio codec: {audio_stream}")

    report = {
        "status": "DETERMINISTIC_TIMELINE_REPAIR_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v2_deterministic_5_5_5_av_retime",
        "provider_recalled": False,
        "source_supplier_run_id": SOURCE_SUPPLIER_RUN_ID,
        "source_supplier_artifact_id": SOURCE_SUPPLIER_ARTIFACT_ID,
        "source_supplier_artifact_name": SOURCE_SUPPLIER_ARTIFACT_NAME,
        "source_supplier_head_sha": SOURCE_SUPPLIER_HEAD_SHA,
        "source_supplier_task_id": SOURCE_SUPPLIER_TASK_ID,
        "source_prompt_sha256": SOURCE_PROMPT_SHA256,
        "source_video_sha256": SOURCE_VIDEO_SHA256,
        "source_reference_sha256": list(SOURCE_REFERENCE_SHA256),
        "source_c01_identity_sha256": SOURCE_C01_IDENTITY_SHA256,
        "canonical_visible_text": list(CANONICAL_VISIBLE_TEXT),
        "source_cut_frames": {
            "shot1_to_shot2": SHOT1_SOURCE_END_FRAME,
            "shot2_to_shot3": SHOT2_SOURCE_END_FRAME,
        },
        "source_frame_counts": {
            "shot1": SHOT1_SOURCE_FRAMES,
            "shot2": SHOT2_SOURCE_FRAMES,
            "shot3": SHOT3_SOURCE_FRAMES,
        },
        "target_frame_counts": {
            "shot1": TARGET_SHOT_FRAMES,
            "shot2": TARGET_SHOT_FRAMES,
            "shot3": TARGET_SHOT_FRAMES,
        },
        "video_pts_factors": [
            SHOT1_VIDEO_PTS_FACTOR,
            SHOT2_VIDEO_PTS_FACTOR,
            SHOT3_VIDEO_PTS_FACTOR,
        ],
        "audio_atempo_factors": [
            SHOT1_AUDIO_TEMPO,
            SHOT2_AUDIO_TEMPO,
            SHOT3_AUDIO_TEMPO,
        ],
        "final_probe": probe,
        "final_video_sha256": _sha256(final_video),
        "final_video_size_bytes": final_video.stat().st_size,
        "github_sha": os.environ.get("GITHUB_SHA"),
    }

    root.mkdir(parents=True, exist_ok=True)
    (root / "E15U03_v2_repair_report.json").write_text(
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
