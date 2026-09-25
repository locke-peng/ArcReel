"""E11U02 v4: reuse accepted Shot 1/2 + audio, regenerate only Shot 3 with canonical C04 rear identity."""

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
REPAIR_VERSION = "v4_targeted_shot3_c04_rear_identity_lock"
DURATION_SECONDS = 15
SHOT_SECONDS = 5
PLATE_PROVIDER_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"
FINAL_WIDTH = 864
FINAL_HEIGHT = 480
MODEL = "minimax_h3_zm_u24"

V2_SOURCE_RUN_ID = 36148270693
V3_SOURCE_RUN_ID = 36160563284
V2_EVIDENCE_DIR = Path("v2_evidence")
V3_EVIDENCE_DIR = Path("v3_evidence")
V2_SHOT1 = V2_EVIDENCE_DIR / "E11U02_SHOT1_provider_raw.mp4"
V3_SHOT2 = V3_EVIDENCE_DIR / "E11U02_SHOT2_V3_provider_raw.mp4"
V2_SOUNDTRACK = V2_EVIDENCE_DIR / "project" / "fixtures" / "E11U02_canonical_soundtrack.wav"

C04_ANCHOR = Path("scripts/experiments/fixtures/e11u02/C04_SuWan_rear_anchor_180.jpg")
C04_ANCHOR_SHA256 = "1a6f50d353c0620f693c89f42a8128400877e1629e3a0ee97f7008a60021e6be"
REPORTER_DIALOGUE = "陆氏会合作吗"

ZERO_TEXT_AVOID = (
    "Avoid: readable text, letters, digits, subtitles, captions, dialogue transcription, "
    "watermarks, logos, UI labels, pseudo-text, code glyphs, printed marks, BGM."
)

SHOT3_PROMPT = f"""subject_definitions:
<Subject 1> is a purpose-built text-free media arrival corridor from <Picture 1>: plain black acoustic drapes on both sides, matte dark neutral floor, subtle cool overhead light, and no screen, sign, poster, banner, logo wall, printed panel, or text-bearing surface.
<Subject 2> is an adult man represented only by canonical profile cues: tall controlled posture, graphite-to-deep-navy business suit, cold-white shirt, understated watch. His face is never shown.
<Subject 3> is canonical C04 Su Wan derived from <Picture 2>. Preserve the SAME rear identity silhouette from the reference: long dark-brown wavy hair with matching length, volume, wave pattern, and rear hairline; warm ivory/cream tailored upper; light camel/champagne tailored trousers; refined slim build; elegant warm-neutral business styling. Her face is never shown.

summary:
[reference generation; visual-only plate] Create a 10-second premium technology-conference media-arrival plate. The FIRST five seconds are the canonical target: <Subject 2> and canonical <Subject 3> enter together through the plain black-drape media corridor while reporters and cameras react. The camera performs a restrained lateral follow. C04 identity continuity has highest priority: <Subject 3> must remain the same dark-brown-haired rear figure from <Picture 2>; never blonde, light-haired, short-haired, straight-haired, or recast. No dialogue transcript exists in this visual prompt. ZERO readable text.

retention_analysis:
<Subject 1>: fully_preserved environment - preserve only the text-free black acoustic drapes, dark neutral floor, cool event lighting, media density, and flash atmosphere.
<Subject 2>: profile-cue-preserved - tall male silhouette, dark business suit, controlled posture; rear or three-quarter rear only; no facial identity is invented.
<Subject 3>: fully_preserved rear identity - exact dark-brown wavy hair silhouette, warm ivory/cream upper, light camel/champagne trousers, refined proportions, and rear-view continuity from <Picture 2>. No color drift to blonde, gold, platinum, red, or light brown.

detailed_description:
C04 IDENTITY CONTRACT — HIGHEST PRIORITY: <Subject 3> is canonical C04 Su Wan. Preserve Picture 2's long DARK-BROWN WAVY HAIR, including its rear silhouette and volume, for every frame. Keep her warm ivory/cream professional upper and light camel/champagne tailored trousers. No blonde hair. No light hair. No bob. No ponytail. No alternate actress. No face substitution.
C02 SAFETY CONTRACT — HIGHEST PRIORITY: <Subject 2> stays rear or three-quarter rear for the entire target shot. Preserve only the dark tailored business silhouette and understated watch; never create a front-facing portrait face.
SCENE CONTRACT — HIGHEST PRIORITY: this is a premium media ARRIVAL CORRIDOR adjacent to the technology summit, not the main stage and not the laboratory.
BLACK-DRAPE CONTRACT — HIGHEST PRIORITY: every background surface is plain black acoustic curtain, matte dark wall, or neutral architecture. No sponsor wall, event title, projection, LED panel, poster, banner, directional sign, booth graphic, printed card, hanging card, or wall graphic exists in frame.
DEVICE CONTRACT — HIGHEST PRIORITY: reporters' camera rear displays face away from camera or remain black/off. Microphones use plain black windscreens with no markings.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text and ZERO glyph-like pseudo-text anywhere in frame.
[Target Plate] 00:00-00:05. Medium 35mm rear entrance shot. At 00:00 the pair enter from frame left, with <Subject 2> slightly ahead and canonical C04 <Subject 3> half a step beside him. A restrained lateral follow tracks them about one meter. Keep C04's dark-brown wavy hair clearly visible from the rear. Reporters on both sides raise cameras; two or three flash bursts fire. The pair do not stop and do not answer. Hold the media-entry movement through 00:05.
[Extension] 00:05-00:10. Maintain the exact same rear identities, dark-brown C04 hair, black-drape corridor, blank surfaces, and media density with no new action.

overall_soundscape:
N/A for this visual plate; the accepted detached canonical soundtrack is reused later.

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
    if not C04_ANCHOR.is_file():
        raise RuntimeError("canonical C04 rear anchor is missing")
    actual_anchor_sha = _sha256(C04_ANCHOR)
    if actual_anchor_sha != C04_ANCHOR_SHA256:
        raise RuntimeError(
            f"C04 rear anchor SHA mismatch: {actual_anchor_sha} != {C04_ANCHOR_SHA256}"
        )
    if _has_cjk(SHOT3_PROMPT):
        raise RuntimeError("CJK leaked into E11U02 v4 visual prompt")
    if "<d>" in SHOT3_PROMPT or "</d>" in SHOT3_PROMPT:
        raise RuntimeError("dialogue tag leaked into E11U02 v4 visual prompt")
    if REPORTER_DIALOGUE in SHOT3_PROMPT:
        raise RuntimeError("reporter dialogue leaked into E11U02 v4 visual prompt")
    required = (
        "canonical C04 Su Wan",
        "long DARK-BROWN WAVY HAIR",
        "warm ivory/cream professional upper",
        "light camel/champagne tailored trousers",
        "No blonde hair",
        "C02 SAFETY CONTRACT",
        "BLACK-DRAPE CONTRACT",
        "ZERO readable text",
        "ZERO glyph-like pseudo-text",
        "rear or three-quarter rear",
    )
    for phrase in required:
        if phrase not in SHOT3_PROMPT:
            raise RuntimeError(f"E11U02 v4 prompt is missing: {phrase}")
    if SHOT3_PROMPT.rstrip().splitlines()[-1] != ZERO_TEXT_AVOID:
        raise RuntimeError("E11U02 v4 final avoid line is not last")


def _assert_runtime_inputs() -> None:
    missing = [str(path) for path in (V2_SHOT1, V3_SHOT2, V2_SOUNDTRACK) if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing reused E11U02 evidence inputs: {missing}")


def _make_black_drape_reference(path: Path) -> None:
    width, height = 960, 540
    image = Image.new("RGB", (width, height), (12, 14, 18))
    draw = ImageDraw.Draw(image)

    # Ceiling.
    draw.polygon([(0, 0), (width, 0), (830, 120), (130, 120)], fill=(18, 22, 28))
    # Floor with a subtle perspective gradient and no markings.
    for y in range(120, height):
        ratio = (y - 120) / (height - 120)
        value = round(30 + 28 * ratio)
        draw.line((0, y, width, y), fill=(value, value + 2, value + 5))

    # Plain black curtains; vertical folds are geometry, never text.
    for x in range(0, 230, 18):
        shade = 8 + (x // 18 % 2) * 6
        draw.rectangle((x, 70, x + 18, height), fill=(shade, shade + 1, shade + 3))
    for x in range(730, width, 18):
        shade = 8 + (x // 18 % 2) * 6
        draw.rectangle((x, 70, x + 18, height), fill=(shade, shade + 1, shade + 3))

    # Text-free cool ceiling lights.
    draw.rectangle((350, 38, 610, 46), fill=(150, 190, 220))
    draw.rectangle((410, 85, 550, 91), fill=(110, 150, 180))

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
        raise RuntimeError("failed to author E11U02 v4 final video")
    os.replace(temp, output)


async def _generate_shot3(
    *,
    project: Path,
    api_key: str,
    base_url: str,
    references: list[Path],
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
        prompt=SHOT3_PROMPT.strip(),
        resource_type="reference_videos",
        resource_id=f"{UNIT_ID}_SHOT3_V4",
        reference_images=references,
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=PLATE_PROVIDER_SECONDS,
        resolution=RESOLUTION,
        generate_audio=True,
        poll_timeout_seconds=900,
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("provider returned no E11U02 v4 Shot 3 artifact")
    versions_path = project / "versions" / "versions.json"
    versions_text = await asyncio.to_thread(versions_path.read_text, encoding="utf-8")
    versions = json.loads(versions_text)
    record = versions["reference_videos"][f"{UNIT_ID}_SHOT3_V4"]["versions"][-1]
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
    corridor_ref = refs / "E11U02_v4_black_drape_corridor.jpg"
    _make_black_drape_reference(corridor_ref)

    shot3_output, shot3_version, shot3_record = await _generate_shot3(
        project=project,
        api_key=api_key,
        base_url=base_url,
        references=[corridor_ref, C04_ANCHOR],
    )
    shot3_raw = root / "E11U02_SHOT3_V4_provider_raw.mp4"
    shutil.copy2(shot3_output, shot3_raw)

    final_video = project / "reference_videos" / f"{UNIT_ID}.mp4"
    await asyncio.to_thread(
        _author_final_video,
        V2_SHOT1,
        V3_SHOT2,
        shot3_raw,
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
        "source_v3_run_id": V3_SOURCE_RUN_ID,
        "supplier_calls_this_attempt": 1,
        "reused_assets": {
            "shot1_v2_sha256": _sha256(V2_SHOT1),
            "shot2_v3_sha256": _sha256(V3_SHOT2),
            "soundtrack_v2_sha256": _sha256(V2_SOUNDTRACK),
        },
        "c04_identity": {
            "anchor_sha256": _sha256(C04_ANCHOR),
            "lock": "long dark-brown wavy hair; warm ivory/cream upper; light camel/champagne trousers; rear only",
        },
        "shot3": {
            "version": shot3_version,
            "provider_duration_seconds": shot3_record.get("provider_duration_seconds"),
            "provider_prompt_sha256": provider_prompt_sha256(SHOT3_PROMPT.strip()),
            "corridor_reference_sha256": _sha256(corridor_ref),
            "video_sha256": _sha256(shot3_raw),
            "video_size_bytes": shot3_raw.stat().st_size,
            "dialogue_detached": True,
            "visual_prompt_contains_cjk": _has_cjk(SHOT3_PROMPT),
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
    (root / "E11U02_v4_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E11U02_v4_shot3_provider_prompt.txt").write_text(
        SHOT3_PROMPT.strip(),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
