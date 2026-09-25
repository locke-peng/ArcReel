"""E11U02 v3: reuse accepted v2 Shot 1/3 + audio, regenerate only Shot 2 with a text-free semantic-neutral object."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256

UNIT_ID = "E11U02"
REPAIR_VERSION = "v3_targeted_shot2_semantic_neutral_blank_token"
DURATION_SECONDS = 15
SHOT_SECONDS = 5
PLATE_PROVIDER_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"
FINAL_WIDTH = 864
FINAL_HEIGHT = 480
MODEL = "minimax_h3_zm_u24"

V2_SOURCE_RUN_ID = 36148270693
V2_EVIDENCE_DIR = Path("v2_evidence")
V2_SHOT1 = V2_EVIDENCE_DIR / "E11U02_SHOT1_provider_raw.mp4"
V2_SHOT3 = V2_EVIDENCE_DIR / "E11U02_SHOT3_provider_raw.mp4"
V2_SOUNDTRACK = V2_EVIDENCE_DIR / "project" / "fixtures" / "E11U02_canonical_soundtrack.wav"

DIALOGUES = ("通过了", "明天见真章", "陆氏会合作吗")

ZERO_TEXT_AVOID = (
    "Avoid: readable text, letters, digits, subtitles, captions, dialogue transcription, "
    "watermarks, logos, UI labels, pseudo-text, code glyphs, printed marks, BGM."
)

SHOT2_PROMPT = f"""subject_definitions:
<Subject 1> is a clean cool-gray worktable reference with soft professional laboratory lighting and no screen, paper, sign, label, or printed surface.

summary:
[reference generation; visual-only plate] Create a 10-second close tabletop plate. The FIRST five seconds are the canonical target. A man's dark tailored sleeve and hand enter from frame edge and place one completely featureless matte rectangular polymer token attached to a plain black cord beside a woman's resting hand in a clean white tailored sleeve. The object is a single uniform soft-gray material. It contains no colored patch, no emblem, no image, no icon, no border, no stripe, no writing, no number, no symbol, no barcode, and no decorative graphic. Faces remain fully outside frame. No dialogue transcript exists in this visual prompt. ZERO readable text.

retention_analysis:
<Subject 1>: fully_preserved background - retain only the clean tabletop, cool professional light, shallow depth of field, and text-free composition.

detailed_description:
IDENTITY-SAFE FRAMING — HIGHEST PRIORITY: show hands and forearms only. No face, head, facial reflection, portrait photograph, mirror, or background person.
OBJECT CONTRACT — HIGHEST PRIORITY: one flat rectangular polymer token, approximately palm-sized, uniform soft gray from edge to edge, attached by a small metal ring to one plain black cord. Both visible surfaces are completely blank. No blue patch, no colored panel, no graphic, no logo, no letters, no digits, no icon, no pattern, and no decorative element.
CORD CONTRACT — HIGHEST PRIORITY: plain black solid cord only, completely unprinted and unpatterned.
NO-SCREEN CONTRACT — HIGHEST PRIORITY: no monitor, laptop, tablet, phone screen, display, poster, paper, document, wall sign, printed object, or other text-bearing surface exists anywhere in frame.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text and ZERO glyph-like pseudo-text.
[Target Plate] 00:00-00:05. Close 70mm tabletop shot, static. At 00:00 the woman's hand rests on the clean table. At about 00:01, the man's hand enters from upper right holding the plain black cord and featureless rectangular polymer token, sets the token gently beside her hand, releases it, then withdraws. The woman's fingers pause to acknowledge the placement without picking it up. Hold the blank token and her hand through 00:05.
[Extension] 00:05-00:10. Maintain exactly the same object position, blank surfaces, hands-only framing, and text-free tabletop with only subtle breathing-level movement.

overall_soundscape:
N/A for this visual plate; canonical audio is reused from the accepted v2 audio seed and muxed later.

non_diegetic_music:
N/A
{ZERO_TEXT_AVOID}"""


class _Call:
    call_id = None

    def success(self, _result: object) -> None:
        return None


class _NullLedger:
    @asynccontextmanager
    async def record(self, **_kwargs: Any):
        yield _Call()

    async def record_provider_response(self, **_kwargs: Any) -> None:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_cjk(value: str) -> bool:
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in value
    )


def _assert_prompt_contract() -> None:
    if _has_cjk(SHOT2_PROMPT):
        raise RuntimeError("CJK leaked into E11U02 v3 visual prompt")
    if "<d>" in SHOT2_PROMPT or "</d>" in SHOT2_PROMPT:
        raise RuntimeError("dialogue tag leaked into E11U02 v3 visual prompt")
    for dialogue in DIALOGUES:
        if dialogue in SHOT2_PROMPT:
            raise RuntimeError(f"dialogue leaked into E11U02 v3 visual prompt: {dialogue}")
    forbidden_semantic_triggers = (
        "badge",
        "credential",
        "summit",
        "guest pass",
        "identity card",
        "name card",
        "lanyard",
    )
    lower = SHOT2_PROMPT.lower()
    for token in forbidden_semantic_triggers:
        if token in lower:
            raise RuntimeError(f"text-bearing semantic trigger remains in Shot 2 visual prompt: {token}")
    required = (
        "completely featureless matte rectangular polymer token",
        "uniform soft gray",
        "No blue patch",
        "plain black solid cord only",
        "NO-SCREEN CONTRACT",
        "ZERO readable text",
        "ZERO glyph-like pseudo-text",
    )
    for phrase in required:
        if phrase not in SHOT2_PROMPT:
            raise RuntimeError(f"E11U02 v3 prompt is missing: {phrase}")
    if SHOT2_PROMPT.rstrip().splitlines()[-1] != ZERO_TEXT_AVOID:
        raise RuntimeError("E11U02 v3 final avoid line is not last")


def _assert_runtime_inputs() -> None:
    missing = [str(path) for path in (V2_SHOT1, V2_SHOT3, V2_SOUNDTRACK) if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing downloaded v2 evidence inputs: {missing}")


def _make_neutral_reference(path: Path) -> None:
    width, height = 960, 540
    image = Image.new("RGB", (width, height), (190, 199, 205))
    draw = ImageDraw.Draw(image)

    # Soft text-free laboratory-like background gradient.
    for y in range(height):
        if y < 155:
            ratio = y / 155
            value = round(52 + ratio * 30)
            draw.line((0, y, width, y), fill=(value - 8, value, value + 8))
        else:
            ratio = (y - 155) / (height - 155)
            value = round(188 + ratio * 20)
            draw.line((0, y, width, y), fill=(value - 4, value, value + 4))

    # Featureless architectural blur bands only; intentionally no text-bearing geometry.
    draw.rectangle((0, 145, width, 160), fill=(120, 132, 142))
    draw.rectangle((0, 160, width, 165), fill=(160, 170, 178))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=92, optimize=True)


def _author_final_video(shot1: Path, shot2: Path, shot3: Path, audio: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f"{output.stem}_authoring.mp4")
    subprocess.run(
        [
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
            str(audio),
            "-filter_complex",
            (
                f"[0:v]trim=start=0:end={SHOT_SECONDS},setpts=PTS-STARTPTS,"
                f"scale={FINAL_WIDTH}:{FINAL_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={FINAL_WIDTH}:{FINAL_HEIGHT},format=yuv420p[v0];"
                f"[1:v]trim=start=0:end={SHOT_SECONDS},setpts=PTS-STARTPTS,"
                f"scale={FINAL_WIDTH}:{FINAL_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={FINAL_WIDTH}:{FINAL_HEIGHT},format=yuv420p[v1];"
                f"[2:v]trim=start=0:end={SHOT_SECONDS},setpts=PTS-STARTPTS,"
                f"scale={FINAL_WIDTH}:{FINAL_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={FINAL_WIDTH}:{FINAL_HEIGHT},format=yuv420p[v2];"
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
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-t",
            str(DURATION_SECONDS),
            "-movflags",
            "+faststart",
            str(temp),
        ],
        check=True,
    )
    if not temp.is_file() or temp.stat().st_size <= 0:
        raise RuntimeError("failed to author E11U02 v3 final video")
    os.replace(temp, output)


async def _generate_shot2(
    *,
    project: Path,
    api_key: str,
    base_url: str,
    reference: Path,
) -> tuple[Path, int, dict[str, Any]]:
    definition_text = await asyncio.to_thread(
        Path("scripts/experiments/autodl_minimax_h3_endpoint.json").read_text,
        encoding="utf-8",
    )
    definition = json.loads(definition_text)
    backend = DeclarativeVideoBackend(
        api_key=api_key,
        base_url=base_url,
        model=MODEL,
        definition=definition,
        provider="autodl",
    )
    generator = MediaGenerator(project, video_backend=backend, video_provider_id="autodl")
    generator.ledger = _NullLedger()
    output_path, version, _video_ref, _video_uri = await generator.generate_video_async(
        prompt=SHOT2_PROMPT.strip(),
        resource_type="reference_videos",
        resource_id=f"{UNIT_ID}_SHOT2_V3",
        reference_images=[reference],
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=PLATE_PROVIDER_SECONDS,
        resolution=RESOLUTION,
        generate_audio=True,
        poll_timeout_seconds=900,
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("provider returned no E11U02 v3 Shot 2 artifact")
    versions_path = project / "versions" / "versions.json"
    versions_text = await asyncio.to_thread(versions_path.read_text, encoding="utf-8")
    versions = json.loads(versions_text)
    record = versions["reference_videos"][f"{UNIT_ID}_SHOT2_V3"]["versions"][-1]
    return output_path, version, record


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://autodl.art"

    _assert_prompt_contract()
    _assert_runtime_inputs()

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    refs = project / "fixtures"
    neutral_ref = refs / "E11U02_v3_shot2_neutral_reference.jpg"
    _make_neutral_reference(neutral_ref)

    shot2_output, shot2_version, shot2_record = await _generate_shot2(
        project=project,
        api_key=api_key,
        base_url=base_url,
        reference=neutral_ref,
    )
    shot2_raw = root / "E11U02_SHOT2_V3_provider_raw.mp4"
    shutil.copy2(shot2_output, shot2_raw)

    final_video = project / "reference_videos" / f"{UNIT_ID}.mp4"
    await asyncio.to_thread(
        _author_final_video,
        V2_SHOT1,
        shot2_raw,
        V2_SHOT3,
        V2_SOUNDTRACK,
        final_video,
    )
    final_duration = await probe_existing_video_duration_seconds(final_video)

    report = {
        "status": "GENERATED_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": REPAIR_VERSION,
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "model": MODEL,
        "source_v2_run_id": V2_SOURCE_RUN_ID,
        "supplier_calls_this_attempt": 1,
        "reused_v2_assets": {
            "shot1_sha256": _sha256(V2_SHOT1),
            "shot3_sha256": _sha256(V2_SHOT3),
            "soundtrack_sha256": _sha256(V2_SOUNDTRACK),
        },
        "shot2": {
            "version": shot2_version,
            "provider_duration_seconds": shot2_record.get("provider_duration_seconds"),
            "provider_prompt_sha256": provider_prompt_sha256(SHOT2_PROMPT.strip()),
            "neutral_reference_sha256": _sha256(neutral_ref),
            "video_sha256": _sha256(shot2_raw),
            "video_size_bytes": shot2_raw.stat().st_size,
            "semantic_text_trigger_terms_removed": True,
            "dialogue_detached": True,
        },
        "duration_requested_seconds": DURATION_SECONDS,
        "final_authored_duration_seconds": final_duration,
        "shot_seconds": SHOT_SECONDS,
        "aspect_ratio": ASPECT_RATIO,
        "provider_resolution": RESOLUTION,
        "final_resolution": f"{FINAL_WIDTH}x{FINAL_HEIGHT}",
        "canonical_visible_text": [],
        "final": {
            "video_size_bytes": final_video.stat().st_size,
            "video_sha256": _sha256(final_video),
        },
    }

    root.mkdir(parents=True, exist_ok=True)
    (root / "E11U02_v3_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E11U02_v3_shot2_provider_prompt.txt").write_text(
        SHOT2_PROMPT.strip(),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
