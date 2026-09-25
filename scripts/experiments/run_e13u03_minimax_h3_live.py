"""Paid E13U03 acceptance: 3 deterministic 5s plates, C03/C01 identity locks, unreadable-log guard, detached audio."""

from __future__ import annotations

import asyncio
import base64
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

UNIT_ID = "E13U03"
DURATION_SECONDS = 15
SHOT_SECONDS = 5
PLATE_PROVIDER_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"
FINAL_WIDTH = 864
FINAL_HEIGHT = 480
MODEL = "minimax_h3_zm_u24"

DIALOGUE = "打开底层日志"
C01_ID = "C01"
C03_ID = "C03"

SCENE_BRIDGE = Path("scripts/experiments/fixtures/e13u03/E13U03_scene_bridge.jpg")
SCENE_BRIDGE_SHA256 = "2221bc97ca6fcc6249021f45b93f1e6107b8c9b02115a179856685dc01bfec67"
C03_REF = Path("scripts/experiments/fixtures/e4u02/C03_LuNian_current_face.jpg")
C03_REF_SHA256 = "c92b71c3fe707088dd340d41de9a202e2ab7d02392fef4913b2df6959c4932b0"
C01_BRIDGE_PART_GLOB = "e13u01_stage_c01_bridge.jpg.b64.part.*"
C01_BRIDGE_SHA256 = "fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135"

ZERO_TEXT_AVOID = (
    "Avoid: readable text, letters, digits, subtitles, captions, dialogue transcription, "
    "watermarks, logos, UI labels, pseudo-text, code glyphs, BGM."
)

AUDIO_SEED_PROMPT = f"""subject_definitions:
<Subject 1> is a neutral production reference used only to anchor room acoustics for a three-part 15-second soundtrack.

summary:
Create one continuous 15-second soundtrack matching three exact five-second story beats. The visual seed is disposable. 00:00-00:05 is a bright school technology classroom with a sudden burst of surprised student gasps and chair movement, no intelligible student speech. 00:05-00:10 is a quiet professional AI summit control area: one adult woman speaks exactly one Mandarin command, then keyboard sounds begin. 00:10-00:15 contains rapid electronic log-scrolling sounds and subtle interface beeps, with no speech. No non-diegetic music.

retention_analysis:
<Subject 1>: partially_preserved - use only plausible indoor acoustics; visual content does not matter.

detailed_description:
[Audio Shot 1] 00:00-00:05. School technology classroom ambience. At about 00:01, several children make a brief non-verbal surprised gasp while a chair shifts as one child sits upright suddenly. No intelligible words.
[Audio Shot 2] 00:05-00:10. Clean hard acoustic transition to a large summit control zone. At about 00:05.6, one calm adult woman says exactly: <d>[Chinese] {DIALOGUE}</d>. Immediately after, restrained keyboard typing begins. No other speech.
[Audio Shot 3] 00:10-00:15. No speech. Fast electronic data-scrolling texture, subtle UI beeps, and low equipment hum.

overall_soundscape:
Natural school room tone followed by summit control-room ambience. Dialogue occurs only once in Audio Shot 2. No extra intelligible speech.

non_diegetic_music:
N/A"""

SHOT1_PROMPT = f"""subject_definitions:
<Subject 1> is the LEFT scene panel from <Picture 1>: a bright contemporary school technology classroom with rows of desks, a front projection screen, robotics equipment, large windows, neutral daylight, and no required readable signage.
<Subject 2> is canonical child identity {C03_ID}, derived from <Picture 2>. Preserve the exact current-age face, dark hair, eye geometry, brows, nose, mouth, cheek shape, skin tone, school-age proportions, and recognizable identity.

summary:
[reference generation; visual-only plate] Create a 10-second horizontal school reaction plate. The FIRST five seconds are the canonical target: <Subject 2> is seated at a classroom desk watching a live summit feed and suddenly sits upright in shock. A few classmates react around her without blocking her face. The camera performs a slow push-in. The projector image may show only a soft, defocused white-suited adult silhouette against blue-black event lighting; it contains ZERO readable text. Preserve the classroom layout from <Picture 1> and the exact {C03_ID} identity from <Picture 2>.

retention_analysis:
<Subject 1>: fully_preserved environment - keep the bright classroom, rows of desks, front screen, robotics/technology teaching atmosphere, windows, and daylight.
<Subject 2>: fully_preserved identity - no recast, no older teenager, no alternate child face, no face drift.

detailed_description:
IDENTITY CONTRACT — HIGHEST PRIORITY: the foreground child is canonical {C03_ID}. Preserve her exact recognizable face throughout.
SCENE CONTRACT — HIGHEST PRIORITY: use the LEFT classroom panel of <Picture 1>; do not replace it with an auditorium, office, home, or generic classroom.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text anywhere. The projector feed is defocused and non-linguistic. No subtitles, captions, names, logos, timestamps, UI labels, or pseudo-text.
[Target Plate] 00:00-00:05. Medium shot, eye level, 50mm. At 00:00 the child is already seated and looking toward the front projection. Around 00:01 she suddenly straightens her back and sits upright, eyes widening as recognition lands. One or two nearby classmates make small surprised movements while staying secondary and slightly out of focus. Slow 0.35-meter push-in. Hold her reaction through 00:05.
[Extension] 00:05-00:10. Maintain the same composition and identity with only subtle breathing and gaze movement; no new action and no new text.

overall_soundscape:
N/A for this visual plate; canonical audio is muxed later.

non_diegetic_music:
N/A
{ZERO_TEXT_AVOID}"""

SHOT2_PROMPT = f"""subject_definitions:
<Subject 1> is the RIGHT scene panel from <Picture 1>: the AI summit technical control area with professional monitors, switchers, keyboards, cool blue-black event lighting, and the same summit visual language established earlier.
<Subject 2> is canonical adult identity {C01_ID}, derived from the RIGHT portrait panel in <Picture 2>. Preserve the exact face topology, dark tied-back hair, eye geometry, brows, nose, mouth, cheek/jaw structure, skin tone, white professional pantsuit, body proportions, gray structured handbag, and recognizable identity.

summary:
[reference generation; visual-only plate] Create a 10-second summit control-console plate. The FIRST five seconds are the canonical target: <Subject 2> approaches the malfunctioning control console, reaches it immediately, places one hand near the keyboard, and begins operating it with calm professional focus. No dialogue transcript exists in this visual prompt. All monitor surfaces are abstract technical geometry only and contain ZERO readable text.

retention_analysis:
<Subject 1>: fully_preserved environment - preserve the summit control-console topology, multiple professional displays, keyboard/switcher surfaces, dark technical zone, and cool event lighting.
<Subject 2>: fully_preserved identity - exact canonical {C01_ID} face and white professional suit. No recast, face substitution, or alternate wardrobe.

detailed_description:
IDENTITY CONTRACT — HIGHEST PRIORITY: the woman is canonical {C01_ID}, matching <Picture 2>. Preserve her exact face in every frame.
SCENE CONTRACT — HIGHEST PRIORITY: the console belongs to the same AI summit environment as the preceding units; no home office, no laboratory replacement, no generic laptop-only desk.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text. Every monitor uses only blurred panels, simple colored rectangles, horizontal light bars, waveform-like shapes, and icon-free abstract status blocks. No code, letters, numbers, captions, subtitles, logos, labels, or pseudo-glyphs.
[Target Plate] 00:00-00:05. Near-medium 50mm shot, eye level. At 00:00 she is one controlled step from the console. By 00:01.5 she reaches it. She sets her handbag close to her side without losing it, places her left hand near the keyboard, and begins typing with restrained precision while looking at the monitors. Static camera with a very slight push-in. Hold focused operation through 00:05.
[Extension] 00:05-00:10. Maintain the same identity and console position with subtle typing only. No new characters and no readable text.

overall_soundscape:
N/A for this visual plate; canonical dialogue and keyboard audio are muxed later.

non_diegetic_music:
N/A
{ZERO_TEXT_AVOID}"""

SHOT3_PROMPT = f"""subject_definitions:
<Subject 1> is a purpose-built no-text log reference from <Picture 1>. Its display contains only horizontal luminous bars of different lengths on a dark technical interface; these bars represent fast system-log rows but are NOT letters, numbers, code, or glyphs. The adjacent face region is canonical adult identity {C01_ID}.
<Subject 2> is the same canonical {C01_ID} woman, reinforced by <Picture 2>. Preserve exact facial identity and white professional styling.

summary:
[reference generation; visual-only plate] Create a 10-second close technical inspection plate. The FIRST five seconds are the canonical target: abstract log rows scroll rapidly upward while the canonical woman's focused eyes scan across them. The display must remain purely geometric and completely unreadable. No actual code, words, numbers, symbols, or pseudo-text may appear.

retention_analysis:
<Subject 1> display: fully_preserved semantic geometry - dark panel plus horizontal luminous bars only, no linguistic marks.
<Subject 1> face + <Subject 2>: fully_preserved identity - same canonical {C01_ID} woman as the previous plate.

detailed_description:
LOG SEMANTIC CONTRACT — HIGHEST PRIORITY: Canonical only requires that system logs scroll rapidly; Canonical provides NO literal log strings. Therefore render the log state exclusively as moving horizontal light bars and rectangular row blocks. Do not invent code or text.
IDENTITY CONTRACT — HIGHEST PRIORITY: preserve the exact canonical {C01_ID} eyes, brow line, face, hair, and skin tone.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable or glyph-like text. No Chinese, English, digits, code, punctuation strings, command lines, labels, captions, subtitles, watermarks, or pseudo-writing.
[Target Plate] 00:00-00:05. Tight technical close-up. The left two-thirds of frame show dark monitor rows made only from horizontal cyan-white light bars scrolling rapidly upward. The right third contains the woman's eyes and upper face in crisp focus; her gaze makes two small, precise scanning movements across the display. Very slight 0.15-meter push-in. The screen remains geometric and unreadable for the entire shot.
[Extension] 00:05-00:10. Maintain the same geometric scrolling and identity with no new elements.

overall_soundscape:
N/A for this visual plate; canonical electronic audio is muxed later.

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


def _assert_source_assets() -> None:
    expected = {
        SCENE_BRIDGE: SCENE_BRIDGE_SHA256,
        C03_REF: C03_REF_SHA256,
    }
    for path, expected_sha in expected.items():
        if not path.is_file():
            raise RuntimeError(f"missing E13U03 source asset: {path}")
        actual = _sha256(path)
        if actual != expected_sha:
            raise RuntimeError(f"E13U03 source SHA mismatch for {path}: {actual} != {expected_sha}")


def _decode_c01_bridge(path: Path) -> None:
    parts = sorted(Path(".github/live-tests").glob(C01_BRIDGE_PART_GLOB))
    if not parts:
        raise RuntimeError("C01 bridge chunks are missing")
    raw = "".join("".join(part.read_text(encoding="utf-8").split()) for part in parts)
    data = base64.b64decode(raw, validate=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    actual = _sha256(path)
    if actual != C01_BRIDGE_SHA256:
        raise RuntimeError(f"C01 bridge SHA mismatch: {actual} != {C01_BRIDGE_SHA256}")


def _cover(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    scale = max(width / source.width, height / source.height)
    resized = source.resize(
        (round(source.width * scale), round(source.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _make_school_reference(scene_bridge: Path, c03: Path, output: Path) -> None:
    with Image.open(scene_bridge) as bridge_image, Image.open(c03) as c03_image:
        bridge = bridge_image.convert("RGB")
        child = c03_image.convert("RGB")
        school = bridge.crop((0, 0, round(bridge.width * 0.52), bridge.height))
        canvas = Image.new("RGB", (960, 540), (8, 10, 14))
        canvas.paste(_cover(school, (610, 500)), (20, 20))
        canvas.paste(_cover(child, (280, 500)), (660, 20))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="JPEG", quality=90, optimize=True)


def _make_console_reference(scene_bridge: Path, c01_bridge: Path, output: Path) -> None:
    with Image.open(scene_bridge) as bridge_image, Image.open(c01_bridge) as c01_image:
        bridge = bridge_image.convert("RGB")
        c01 = c01_image.convert("RGB")
        console = bridge.crop((round(bridge.width * 0.52), 0, bridge.width, bridge.height))
        character = c01.crop((640, 0, 940, 540))
        canvas = Image.new("RGB", (960, 540), (6, 8, 12))
        canvas.paste(_cover(console, (610, 500)), (20, 20))
        canvas.paste(_cover(character, (280, 500)), (660, 20))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="JPEG", quality=90, optimize=True)


def _make_log_reference(c01_bridge: Path, output: Path) -> None:
    with Image.open(c01_bridge) as c01_image:
        c01 = c01_image.convert("RGB")
        character = c01.crop((640, 0, 940, 540))
        canvas = Image.new("RGB", (960, 540), (3, 8, 14))
        draw = ImageDraw.Draw(canvas)
        # Geometric-only system-log representation: horizontal bars, never glyphs.
        y = 55
        lengths = (430, 520, 360, 470, 295, 545, 405, 500, 330, 455, 520, 385)
        for idx, length in enumerate(lengths):
            x = 40 + (idx % 3) * 8
            draw.rounded_rectangle(
                (x, y, x + length, y + 12),
                radius=4,
                fill=(65 + (idx % 2) * 25, 160, 190),
            )
            y += 34
        canvas.paste(_cover(character, (300, 500)), (640, 20))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="JPEG", quality=92, optimize=True)


def _make_audio_seed_reference(scene_bridge: Path, output: Path) -> None:
    with Image.open(scene_bridge) as source_image:
        source = source_image.convert("RGB")
        canvas = Image.new("RGB", (960, 540), (7, 9, 12))
        canvas.paste(_cover(source, (900, 500)), (30, 20))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="JPEG", quality=82, optimize=True)


def _extract_audio(video: Path, audio: Path) -> None:
    audio.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "32000",
            "-c:a",
            "pcm_s16le",
            str(audio),
        ],
        check=True,
    )
    if not audio.is_file() or audio.stat().st_size <= 0:
        raise RuntimeError("failed to extract E13U03 canonical soundtrack")


def _author_final_video(plates: list[Path], audio: Path, output: Path) -> None:
    if len(plates) != 3:
        raise RuntimeError("E13U03 requires exactly three visual plates")
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
            str(plates[0]),
            "-i",
            str(plates[1]),
            "-i",
            str(plates[2]),
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
        raise RuntimeError("failed to author E13U03 final video")
    os.replace(temp, output)


def _assert_visual_prompt_contract(prompt: str, label: str) -> None:
    if "<d>" in prompt or "</d>" in prompt:
        raise RuntimeError(f"dialogue tag leaked into {label}")
    if DIALOGUE in prompt:
        raise RuntimeError(f"dialogue transcript leaked into {label}")
    if any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in prompt
    ):
        raise RuntimeError(f"CJK leaked into {label}")
    if "ZERO readable text" not in prompt:
        raise RuntimeError(f"zero-text contract missing from {label}")
    if prompt.rstrip().splitlines()[-1] != ZERO_TEXT_AVOID:
        raise RuntimeError(f"final avoid line is not last in {label}")


def _assert_contracts() -> None:
    _assert_source_assets()
    if f"<d>[Chinese] {DIALOGUE}</d>" not in AUDIO_SEED_PROMPT:
        raise RuntimeError("audio seed is missing canonical E13U03 dialogue")
    for label, prompt in (
        ("shot1", SHOT1_PROMPT),
        ("shot2", SHOT2_PROMPT),
        ("shot3", SHOT3_PROMPT),
    ):
        _assert_visual_prompt_contract(prompt, label)
    if "horizontal luminous bars" not in SHOT3_PROMPT:
        raise RuntimeError("shot3 log semantic guard is missing")
    if "Canonical provides NO literal log strings" not in SHOT3_PROMPT:
        raise RuntimeError("shot3 must explicitly forbid invented log content")


async def _generate(
    *,
    project: Path,
    prompt: str,
    resource_id: str,
    duration_seconds: int,
    api_key: str,
    base_url: str,
    reference_images: list[Path],
) -> tuple[Path, int, dict[str, Any]]:
    definition = json.loads(
        Path("scripts/experiments/autodl_minimax_h3_endpoint.json").read_text(encoding="utf-8")
    )
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
        prompt=prompt.strip(),
        resource_type="reference_videos",
        resource_id=resource_id,
        reference_images=reference_images,
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=duration_seconds,
        resolution=RESOLUTION,
        generate_audio=True,
        poll_timeout_seconds=900,
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"provider returned no video artifact for {resource_id}")
    versions_path = project / "versions" / "versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8"))
    record = versions["reference_videos"][resource_id]["versions"][-1]
    return output_path, version, record


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://autodl.art"

    _assert_contracts()

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    refs = project / "fixtures"
    c01_bridge = refs / "C01_stage_identity_bridge.jpg"
    school_ref = refs / "E13U03_school_C03_reference.jpg"
    console_ref = refs / "E13U03_console_C01_reference.jpg"
    log_ref = refs / "E13U03_log_C01_reference.jpg"
    audio_ref = refs / "E13U03_audio_seed_reference.jpg"
    soundtrack = refs / "E13U03_canonical_soundtrack.wav"

    _decode_c01_bridge(c01_bridge)
    _make_school_reference(SCENE_BRIDGE, C03_REF, school_ref)
    _make_console_reference(SCENE_BRIDGE, c01_bridge, console_ref)
    _make_log_reference(c01_bridge, log_ref)
    _make_audio_seed_reference(SCENE_BRIDGE, audio_ref)

    audio_seed_video, audio_seed_version, audio_seed_record = await _generate(
        project=project,
        prompt=AUDIO_SEED_PROMPT,
        resource_id=f"{UNIT_ID}_AUDIO_SEED",
        duration_seconds=DURATION_SECONDS,
        api_key=api_key,
        base_url=base_url,
        reference_images=[audio_ref],
    )
    _extract_audio(audio_seed_video, soundtrack)

    plate_specs = [
        ("SHOT1", SHOT1_PROMPT, [school_ref, C03_REF]),
        ("SHOT2", SHOT2_PROMPT, [console_ref, c01_bridge]),
        ("SHOT3", SHOT3_PROMPT, [log_ref, c01_bridge]),
    ]
    raw_plates: list[Path] = []
    plate_reports: list[dict[str, Any]] = []
    for suffix, prompt, images in plate_specs:
        output, version, record = await _generate(
            project=project,
            prompt=prompt,
            resource_id=f"{UNIT_ID}_{suffix}",
            duration_seconds=PLATE_PROVIDER_SECONDS,
            api_key=api_key,
            base_url=base_url,
            reference_images=images,
        )
        raw_copy = root / f"{UNIT_ID}_{suffix}_provider_raw.mp4"
        shutil.copy2(output, raw_copy)
        raw_plates.append(raw_copy)
        plate_reports.append(
            {
                "shot": suffix,
                "version": version,
                "provider_duration_seconds": record.get("provider_duration_seconds"),
                "provider_prompt_sha256": provider_prompt_sha256(prompt.strip()),
                "video_sha256": _sha256(raw_copy),
                "video_size_bytes": raw_copy.stat().st_size,
            }
        )

    final_video = project / "reference_videos" / f"{UNIT_ID}.mp4"
    await asyncio.to_thread(_author_final_video, raw_plates, soundtrack, final_video)
    final_duration = await probe_existing_video_duration_seconds(final_video)

    report = {
        "status": "GENERATED_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v1_three_plate_dialogue_detached_log_semantic_guard",
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "model": MODEL,
        "duration_requested_seconds": DURATION_SECONDS,
        "final_authored_duration_seconds": final_duration,
        "shot_seconds": SHOT_SECONDS,
        "plate_provider_seconds": PLATE_PROVIDER_SECONDS,
        "aspect_ratio": ASPECT_RATIO,
        "provider_resolution": RESOLUTION,
        "final_resolution": f"{FINAL_WIDTH}x{FINAL_HEIGHT}",
        "canonical_shots": {
            "shot1": "school livestream: C03 sits upright suddenly",
            "shot2": "C01 reaches malfunctioning control console; dialogue audio-only",
            "shot3": "system logs scroll rapidly; C01 gaze scans",
        },
        "canonical_dialogue": DIALOGUE,
        "canonical_visible_text": [],
        "visual_prompts_contain_cjk": [
            any(
                "\u3400" <= char <= "\u4dbf"
                or "\u4e00" <= char <= "\u9fff"
                or "\uf900" <= char <= "\ufaff"
                for char in prompt
            )
            for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT)
        ],
        "dialogue_detached_from_visual_prompts": all(
            DIALOGUE not in prompt and "<d>" not in prompt
            for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT)
        ),
        "log_literal_strings_invented": False,
        "audio_seed_prompt_sha256": provider_prompt_sha256(AUDIO_SEED_PROMPT.strip()),
        "reference_sha256": {
            "scene_bridge": _sha256(SCENE_BRIDGE),
            "c03_current": _sha256(C03_REF),
            "c01_bridge": _sha256(c01_bridge),
            "school_reference": _sha256(school_ref),
            "console_reference": _sha256(console_ref),
            "log_reference": _sha256(log_ref),
            "soundtrack": _sha256(soundtrack),
        },
        "audio_seed": {
            "version": audio_seed_version,
            "provider_duration_seconds": audio_seed_record.get("provider_duration_seconds"),
            "video_sha256": _sha256(audio_seed_video),
        },
        "plates": plate_reports,
        "final": {
            "video_size_bytes": final_video.stat().st_size,
            "video_sha256": _sha256(final_video),
        },
    }

    root.mkdir(parents=True, exist_ok=True)
    (root / "E13U03_v1_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E13U03_audio_seed_provider_prompt.txt").write_text(
        AUDIO_SEED_PROMPT.strip(), encoding="utf-8"
    )
    for suffix, prompt, _images in plate_specs:
        (root / f"E13U03_{suffix.lower()}_provider_prompt.txt").write_text(
            prompt.strip(), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
