"""Deterministic production compositor for E13U01 v4.

The upstream H3 v3 provider output supplies the accepted C01 entrance performance and
E12U06 stage continuity. This compositor replaces only the two classes of content that
must be exact rather than generative:

1. Shot 1 (00:00-00:05) becomes a deterministic canonical identity-title plate.
2. Shot 2 keeps the H3 pixels for C01 and stage motion, while removing the inherited
   E12 loading blocks and applying a soft follow-spot to the authored entrance path.

The source audio is preserved and trimmed to the final 10-second Unit.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

WIDTH = 864
HEIGHT = 480
FPS = 24
UNIT_SECONDS = 10
SHOT_CUT_SECONDS = 5
TITLE_LINE_1 = "沈知意"
TITLE_LINE_2 = "天枢联合创始人"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _font_path() -> str:
    return subprocess.check_output(
        ["bash", "-lc", "fc-match -f '%{file}' 'Noto Sans CJK SC' | head -n1"],
        text=True,
    ).strip()


def build_screen_plate() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(image)
    font_path = _font_path()
    line1 = ImageFont.truetype(font_path, 74)
    line2 = ImageFont.truetype(font_path, 46)
    for value, font, y in ((TITLE_LINE_1, line1, 155), (TITLE_LINE_2, line2, 285)):
        box = draw.textbbox((0, 0), value, font=font)
        x = (WIDTH - (box[2] - box[0])) // 2
        draw.text((x, y), value, font=font, fill=(245, 245, 245))
    return image


def subject_center(t: float) -> tuple[float, float]:
    """Hand-audited C01 center path in the accepted v3 provider motion."""
    keyframes = (
        (5.0, 185.0, 300.0),
        (6.0, 255.0, 275.0),
        (7.0, 315.0, 250.0),
        (8.0, 365.0, 235.0),
        (9.0, 420.0, 225.0),
        (10.0, 455.0, 220.0),
    )
    for left, right in zip(keyframes[:-1], keyframes[1:]):
        t0, x0, y0 = left
        t1, x1, y1 = right
        if t <= t1:
            ratio = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
            return x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio
    return keyframes[-1][1], keyframes[-1][2]


def _remove_loading_blocks(image: Image.Image) -> Image.Image:
    base = image.convert("RGB")
    mask = Image.new("L", base.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((645, 70, WIDTH, 300), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(7))
    black = Image.new("RGB", base.size, (3, 4, 7))
    return Image.composite(black, base, mask)


def _apply_follow_spot(image: Image.Image, t: float) -> Image.Image:
    base = image.convert("RGB")
    cx, cy = subject_center(t)

    subject_mask = Image.new("L", base.size, 0)
    sm = ImageDraw.Draw(subject_mask)
    sm.ellipse((cx - 135, cy - 210, cx + 135, cy + 210), fill=205)
    subject_mask = subject_mask.filter(ImageFilter.GaussianBlur(42))

    beam_mask = Image.new("L", base.size, 0)
    bm = ImageDraw.Draw(beam_mask)
    # A soft live follow-spot from the overhead/right rig toward C01.
    floor_y = min(HEIGHT - 25, cy + 185)
    bm.polygon(
        [
            (500, 0),
            (570, 0),
            (cx + 100, floor_y),
            (cx - 85, floor_y),
        ],
        fill=80,
    )
    beam_mask = beam_mask.filter(ImageFilter.GaussianBlur(28))

    combined = Image.new("L", base.size, 0)
    # Lighter screen blend of the two grayscale masks.
    import PIL.ImageChops

    combined = PIL.ImageChops.lighter(subject_mask, beam_mask)

    bright = ImageEnhance.Brightness(base).enhance(1.28)
    cool_white = Image.new("RGB", base.size, (238, 242, 250))
    bright = Image.blend(bright, cool_white, 0.09)
    return Image.composite(bright, base, combined)


def composite(source_video: Path, output_video: Path, evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="e13u01-v4-") as tmp:
        work = Path(tmp)
        raw_dir = work / "raw"
        processed_dir = work / "processed"
        raw_dir.mkdir()
        processed_dir.mkdir()

        _run(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_video),
            "-vf",
            f"fps={FPS},scale={WIDTH}:{HEIGHT}:flags=lanczos",
            "-t",
            f"{UNIT_SECONDS:.3f}",
            str(raw_dir / "%04d.png"),
        )

        plate = build_screen_plate()
        plate_path = evidence_dir / "E13U01_screen_plate.png"
        plate.save(plate_path)

        total_frames = FPS * UNIT_SECONDS
        cut_frame = FPS * SHOT_CUT_SECONDS
        for index in range(1, total_frames + 1):
            if index <= cut_frame:
                frame = plate.copy()
            else:
                source = raw_dir / f"{index:04d}.png"
                if not source.exists():
                    raise RuntimeError(f"missing source frame {source.name}")
                frame = Image.open(source).convert("RGB")
                t = (index - 1) / FPS
                frame = _remove_loading_blocks(frame)
                frame = _apply_follow_spot(frame, t)
            frame.save(processed_dir / f"{index:04d}.png")

        video_only = work / "video_only.mp4"
        _run(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            str(processed_dir / "%04d.png"),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{UNIT_SECONDS:.3f}",
            str(video_only),
        )

        _run(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_only),
            "-i",
            str(source_video),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-t",
            f"{UNIT_SECONDS:.3f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_video),
        )

    if not output_video.is_file() or output_video.stat().st_size <= 0:
        raise RuntimeError("E13U01 v4 compositor produced no output")

    (evidence_dir / "E13U01_v4_sha256.txt").write_text(
        f"{sha256_file(output_video)}  {output_video.name}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    composite(args.source, args.output, args.evidence_dir)


if __name__ == "__main__":
    main()
