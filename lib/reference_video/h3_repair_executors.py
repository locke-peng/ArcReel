"""Deterministic H3 post-provider repair executors.

These executors operate only on already-generated media. They never import a provider,
never read provider credentials, and never infer canonical facts. All coordinates,
timeline segments, and exact text must be supplied by the validated RepairRequest.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from lib.reference_video.h3_media_pipeline import (
    EvidenceChain,
    EvidenceNode,
    H3MediaPipelineError,
    RepairAction,
    RepairRegion,
    RepairRequest,
    sha256_file,
    validate_repair_request,
)

FPS = 24


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def _probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(proc.stdout)


def _extract_frames(source: Path, frames_dir: Path, *, fps: int) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"fps={fps}",
            str(frames_dir / "frame_%06d.png"),
        ]
    )


def _encode_frames(source: Path, frames_dir: Path, output: Path, *, fps: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def _active_regions(
    regions: tuple[RepairRegion, ...],
    *,
    frame_index: int,
    fps: int,
) -> tuple[RepairRegion, ...]:
    t = frame_index / fps
    return tuple(region for region in regions if region.start_sec <= t < region.end_sec)


def execute_pixel_sanitization(request: RepairRequest, *, fps: int = FPS) -> Path:
    validate_repair_request(request)
    if request.action != RepairAction.DETERMINISTIC_PIXEL_SANITIZATION:
        raise H3MediaPipelineError("pixel executor received incompatible repair action")

    with tempfile.TemporaryDirectory(prefix="h3_pixel_repair_") as temp_name:
        frames = Path(temp_name) / "frames"
        _extract_frames(request.source_path, frames, fps=fps)
        for index, frame_path in enumerate(sorted(frames.glob("frame_*.png"))):
            image = Image.open(frame_path).convert("RGB")
            for region in _active_regions(request.regions, frame_index=index, fps=fps):
                rect = (region.x, region.y, region.x + region.width, region.y + region.height)
                crop = image.crop(rect).filter(ImageFilter.GaussianBlur(radius=18))
                image.paste(crop, rect[:2])
            image.save(frame_path, format="PNG")
        _encode_frames(request.source_path, frames, request.output_path, fps=fps)
    return request.output_path


def _atempo_chain(rate: float) -> str:
    if rate <= 0:
        raise H3MediaPipelineError("audio tempo must be positive")
    values: list[float] = []
    while rate < 0.5:
        values.append(0.5)
        rate /= 0.5
    while rate > 2.0:
        values.append(2.0)
        rate /= 2.0
    values.append(rate)
    return ",".join(f"atempo={value:.12f}" for value in values)


def execute_av_retime(request: RepairRequest, *, fps: int = FPS) -> Path:
    validate_repair_request(request)
    if request.action != RepairAction.DETERMINISTIC_AV_RETIME:
        raise H3MediaPipelineError("retime executor received incompatible repair action")

    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, segment in enumerate(request.timeline):
        source_duration = segment.source_end_sec - segment.source_start_sec
        pts_factor = segment.target_duration_sec / source_duration
        tempo = source_duration / segment.target_duration_sec
        filters.append(
            f"[0:v]trim=start={segment.source_start_sec:.9f}:end={segment.source_end_sec:.9f},"
            f"setpts=(PTS-STARTPTS)*{pts_factor:.12f},fps={fps}[v{index}]"
        )
        filters.append(
            f"[0:a]atrim=start={segment.source_start_sec:.9f}:end={segment.source_end_sec:.9f},"
            f"asetpts=PTS-STARTPTS,{_atempo_chain(tempo)}[a{index}]"
        )
        concat_inputs.extend((f"[v{index}]", f"[a{index}]"))
    filters.append(
        "".join(concat_inputs)
        + f"concat=n={len(request.timeline)}:v=1:a=1[v][a]"
    )

    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(request.source_path),
            "-filter_complex",
            ";".join(filters),
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
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(request.output_path),
        ]
    )
    return request.output_path


def execute_text_plate(
    request: RepairRequest,
    *,
    width: int,
    height: int,
    duration_seconds: float,
    font_path: Path,
    fps: int = FPS,
) -> Path:
    validate_repair_request(request)
    if request.action != RepairAction.DETERMINISTIC_TEXT_PLATE:
        raise H3MediaPipelineError("text-plate executor received incompatible repair action")
    if not font_path.is_file():
        raise H3MediaPipelineError(f"font asset is not pinned or missing: {font_path}")

    with tempfile.TemporaryDirectory(prefix="h3_text_plate_") as temp_name:
        still = Path(temp_name) / "plate.png"
        image = Image.new("RGB", (width, height), (2, 3, 5))
        draw = ImageDraw.Draw(image)
        font_size = max(24, min(width, height) // 10)
        font = ImageFont.truetype(str(font_path), size=font_size)
        lines = request.exact_text
        boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        heights = [box[3] - box[1] for box in boxes]
        total_height = sum(heights) + max(0, len(lines) - 1) * font_size // 2
        y = (height - total_height) / 2
        for line, box, line_height in zip(lines, boxes, heights, strict=True):
            line_width = box[2] - box[0]
            draw.text(((width - line_width) / 2, y), line, font=font, fill=(245, 245, 245))
            y += line_height + font_size // 2
        image.save(still, format="PNG")

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-t",
                f"{duration_seconds:.6f}",
                "-i",
                str(still),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                "-movflags",
                "+faststart",
                str(request.output_path),
            ]
        )
    return request.output_path


def execute_deterministic_repair(
    request: RepairRequest,
    *,
    fps: int = FPS,
    text_plate: dict[str, object] | None = None,
) -> Path:
    if request.action == RepairAction.DETERMINISTIC_PIXEL_SANITIZATION:
        return execute_pixel_sanitization(request, fps=fps)
    if request.action == RepairAction.DETERMINISTIC_AV_RETIME:
        return execute_av_retime(request, fps=fps)
    if request.action == RepairAction.DETERMINISTIC_TEXT_PLATE:
        if text_plate is None:
            raise H3MediaPipelineError("text plate execution requires explicit render parameters")
        return execute_text_plate(request, fps=fps, **text_plate)
    raise H3MediaPipelineError(f"no deterministic executor for {request.action.value}")


def append_repair_evidence(
    *,
    chain: EvidenceChain,
    request: RepairRequest,
    output_path: Path,
    metadata: dict[str, object] | None = None,
) -> EvidenceChain:
    chain.validate()
    if not chain.nodes:
        raise H3MediaPipelineError("repair evidence requires an upstream provider root")
    if sha256_file(request.source_path) != chain.nodes[-1].artifact_sha256:
        raise H3MediaPipelineError("repair source bytes do not match latest evidence node")

    node = EvidenceNode.create(
        stage=request.action.value,
        artifact_path=output_path,
        parent_sha256=(chain.nodes[-1].artifact_sha256,),
        metadata={
            "action": request.action.value,
            "source_sha256": chain.nodes[-1].artifact_sha256,
            "probe": _probe(output_path),
            **dict(metadata or {}),
        },
    )
    updated = EvidenceChain(unit_id=chain.unit_id, nodes=chain.nodes + (node,))
    updated.validate()
    return updated
