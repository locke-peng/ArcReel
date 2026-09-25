"""Paid E13U01 acceptance: exact identity screen + E12 continuity + C01 identity + dialogue-detached audio."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256

UNIT_ID = "E13U01"
DURATION_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"

AUDIO_SEED_MODEL = "minimax_h3_zm_u24"
FINAL_MODEL = "minimax_h3_image_audio_to_video_v2_15s"

VISIBLE_TEXT_NAME = "沈知意"
VISIBLE_TEXT_TITLE = "天枢联合创始人"
HOST_DIALOGUE = "欢迎沈知意"

CHARACTER_ID = "C01"
CHARACTER_NAME = "沈知意"
BRIDGE_B64 = Path(".github/live-tests/e13u01_stage_c01_bridge.jpg.b64")
BRIDGE_SHA256 = "156f4429ec41493f5445dcfeadba9989b626413bc666d62291f3b026b70ec7b1"

FINAL_AVOID_LINE = (
    "Avoid: BGM, subtitles, captions, dialogue transcription, speech bubbles, lower-thirds, "
    "watermarks, logos, timestamps, pseudo-text, and any visible text except the exact approved "
    "screen strings."
)

AUDIO_SEED_PROMPT = f"""subject_definitions:
<Subject 1> is a dark professional AI summit stage environment derived from <Picture 1>. The image is used only to anchor an auditorium-like acoustic and stage atmosphere for an audio seed.

summary:
Create one continuous 10-second conference moment. The visual content of this seed is disposable; the important output is clean production audio. During the first five seconds, an off-screen professional female summit host delivers exactly one Mandarin line and the audience immediately breaks into strong applause. During the second five seconds, applause continues and gradually settles. No non-diegetic music.

retention_analysis:
<Subject 1>: partially_preserved - keep only a plausible dark summit-stage ambience. No readable screen content is required for this seed.

detailed_description:
[Shot 1] 00:00-00:05. Dark AI summit stage ambience. An OFF-SCREEN female host speaks clearly in natural Mandarin: <d>[Chinese] {HOST_DIALOGUE}</d>. The host is not shown. Immediately after the line, a large indoor audience erupts into authentic applause.
[Shot 2] 00:05-00:10. Keep the same auditorium acoustic. No further speech. Applause continues with natural crowd decay.

overall_soundscape:
Clear off-screen female host speech followed by strong indoor conference applause. Preserve natural room reflections. No extra speech.

non_diegetic_music:
N/A"""

FINAL_PROMPT = f"""subject_definitions:
<Subject 1> is the exact summit identity-screen design derived from <Picture 1>. Its black LED background and the two approved white Chinese strings must be reproduced exactly: "{VISIBLE_TEXT_NAME}" and "{VISIBLE_TEXT_TITLE}". These are the only readable strings permitted anywhere in the complete target video.
<Subject 2> is a continuity-and-identity reference board derived from <Picture 2>. Its LEFT panel is the authoritative E12U06 final-stage state: the stage-wing side door is open directly at the immediate stage edge, the threshold is short, the blue-black summit lighting is preserved, the main screen remains in its established position, and the rising white spotlight originates at the stage edge. Its RIGHT panel is canonical character {CHARACTER_ID} {CHARACTER_NAME} in her white professional suit; preserve this exact face, dark hair, hairline, eyes, brows, nose, mouth, cheek/jaw structure, skin tone, white suit silhouette, and recognizable identity.
<Audio 1> is the synchronized source soundtrack. Reuse its host line and applause as audible sound only. Never transcribe, subtitle, caption, quote, or otherwise visualize any spoken content from <Audio 1>.

summary:
[reference generation + audio reuse] Create one continuous 10-second horizontal cinematic sequence in exactly two authored 5-second shots. SCREEN-TEXT LOCK — HIGHEST PRIORITY: [Shot 1] shows the exact two approved strings from <Picture 1>, "{VISIBLE_TEXT_NAME}" and "{VISIBLE_TEXT_TITLE}", and no other readable text, digits, logos, watermarks, glyphs, pseudo-text, captions, or subtitles. CHARACTER IDENTITY LOCK — HIGHEST PRIORITY: [Shot 2] depicts canonical {CHARACTER_ID} {CHARACTER_NAME} matching the RIGHT panel of <Picture 2>; never cast a different woman and never change her face. CONTINUITY LOCK — HIGHEST PRIORITY: [Shot 2] directly continues the LEFT panel of <Picture 2>, which is the accepted final spatial state of E12U06; preserve the same side door, immediate stage-edge threshold, stage geometry, screen location, blue-black lighting, and spotlight origin. AUDIO/TEXT SEPARATION — HIGHEST PRIORITY: copy <Audio 1> as audible sound while keeping all speech non-visual.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - reproduce the black screen and exactly the two approved Chinese strings from <Picture 1>; do not invent a portrait, avatar, logo, third line, English translation, separator label, timestamp, progress indicator, or extra glyph.
<Subject 2> LEFT panel (appears in [Shot 2]): fully_preserved spatial continuity - preserve the E12U06 stage-wing side door physically attached to the immediate stage edge, short threshold, dark wall panels, stage floor, main-screen position, blue accent light, and white spotlight source. Do not move the entrance into a corridor or separate backstage zone.
<Subject 2> RIGHT panel (appears in [Shot 2]): fully_preserved character identity - canonical {CHARACTER_ID} {CHARACTER_NAME} must retain the same recognizable facial topology, hairstyle family, white professional suit, body proportions, and calm controlled presence.
<Audio 1>: fully_copy - reuse the host line and applause as synchronized sound. Spoken words remain audio-only and never become visible text.

detailed_description:
GLOBAL VISIBLE-TEXT CONTRACT — HIGHEST PRIORITY: the complete 10-second video permits only two readable strings, exactly "{VISIBLE_TEXT_NAME}" and "{VISIBLE_TEXT_TITLE}". They may appear only on the giant summit screen in [Shot 1]. No other readable Chinese, English, digits, timestamps, captions, subtitles, lower-thirds, logos, watermarks, UI labels, glyph-like pseudo-writing, or dialogue transcription may appear anywhere.
CHARACTER IDENTITY CONTRACT — HIGHEST PRIORITY: the woman in [Shot 2] is canonical {CHARACTER_ID} {CHARACTER_NAME} from the RIGHT panel of <Picture 2>. Preserve the exact face identity and white professional suit. No generic businesswoman, no alternate actress, no face drift, no additional principal person.
E12U06 CONTINUITY CONTRACT — HIGHEST PRIORITY: [Shot 2] begins from the accepted E12U06 final spatial state shown in the LEFT panel of <Picture 2>. The open side door remains directly attached to the stage wing at the immediate stage edge; the threshold connects directly to the stage floor; the blue-black event lighting and spotlight source stay in the same physical positions. Do not create a long backstage corridor, detached doorway, lobby, or alternate stage.
AUDIO/TEXT SEPARATION CONTRACT — HIGHEST PRIORITY: <Audio 1> supplies all target audio. Do not transcribe, quote, typeset, subtitle, caption, or visualize any spoken content from <Audio 1>. Keep the lower portion of every frame free of caption strips and graphic overlays.

[Shot 1] 00:00-00:05. Tight, centered 50mm view of the giant summit LED screen. The screen is black and displays exactly two clean white Chinese lines matching <Picture 1>: first line "{VISIBLE_TEXT_NAME}", second line "{VISIBLE_TEXT_TITLE}". Keep the typography stable and readable for the shot. No portrait, headshot, logo, decorative badge, English text, third line, digits, progress bars, or pseudo-text. Camera locked off. Follow the first five seconds of <Audio 1>: the off-screen host line is audible, then applause erupts. The spoken line itself never appears as subtitles.

[Shot 2] 00:05-00:10. Clean hard cut to the stage-wing side door and stage edge matching the LEFT panel of <Picture 2>. Canonical <Subject 2> {CHARACTER_NAME}, matching the RIGHT panel of <Picture 2>, steps out from the already-open side door and moves one to two controlled steps directly into the established white spotlight at the stage edge. Medium 35mm framing, eye level, slow 0.4-meter push-in. Her white suit catches the cool spotlight while the blue-black stage architecture remains unchanged. No other principal person enters frame. Any distant main-screen surface is either out of focus or shows only the same two approved strings; no new readable text. Applause from <Audio 1> continues naturally. End with {CHARACTER_NAME} fully readable as the same canonical woman, poised in the spotlight.

overall_soundscape:
<Audio 1> is reused as the synchronized soundtrack: one off-screen female host line in the first shot, followed by strong summit applause continuing through the entrance. No replacement dialogue is synthesized from this visual prompt.

non_diegetic_music:
N/A
{FINAL_AVOID_LINE}"""


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


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for font_path in candidates:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size=size)
    raise RuntimeError("No CJK font found; install fonts-noto-cjk before E13U01 live test")


def _decode_bridge(path: Path) -> None:
    raw = "".join(BRIDGE_B64.read_text(encoding="utf-8").split())
    data = base64.b64decode(raw, validate=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    actual = _sha256(path)
    if actual != BRIDGE_SHA256:
        raise RuntimeError(f"E13U01 bridge SHA mismatch: {actual} != {BRIDGE_SHA256}")


def _make_screen_anchor(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (2, 3, 5))
    draw = ImageDraw.Draw(image)
    name_font = _font(92)
    title_font = _font(56)

    name_box = draw.textbbox((0, 0), VISIBLE_TEXT_NAME, font=name_font)
    title_box = draw.textbbox((0, 0), VISIBLE_TEXT_TITLE, font=title_font)
    name_w = name_box[2] - name_box[0]
    title_w = title_box[2] - title_box[0]

    draw.text(((1280 - name_w) / 2, 220), VISIBLE_TEXT_NAME, font=name_font, fill=(245, 245, 245))
    draw.text(((1280 - title_w) / 2, 365), VISIBLE_TEXT_TITLE, font=title_font, fill=(235, 235, 235))
    image.save(path, format="PNG", optimize=True)


def _make_audio_seed_reference(bridge: Path, path: Path) -> None:
    with Image.open(bridge) as image:
        source = image.convert("RGB")
        # Use only the LEFT continuity panel so the audio-seed visual cannot contaminate C01 identity.
        left = source.crop((0, 0, round(source.width * 0.65), source.height))
        canvas = Image.new("RGB", (1280, 720), (5, 7, 12))
        scale = min(1180 / left.width, 620 / left.height)
        resized = left.resize(
            (round(left.width * scale), round(left.height * scale)),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(resized, ((1280 - resized.width) // 2, (720 - resized.height) // 2))
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path, format="JPEG", quality=90, optimize=True)


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
        raise RuntimeError("failed to extract E13U01 dialogue/applause audio seed")


def _assert_contracts() -> None:
    if f"<d>[Chinese] {HOST_DIALOGUE}</d>" not in AUDIO_SEED_PROMPT:
        raise RuntimeError("audio seed is missing the canonical host dialogue")
    if "<d>" in FINAL_PROMPT or "</d>" in FINAL_PROMPT:
        raise RuntimeError("dialogue tag leaked into E13U01 final visual provider prompt")
    if HOST_DIALOGUE in FINAL_PROMPT:
        raise RuntimeError("host dialogue transcript leaked into E13U01 final visual provider prompt")
    if "<Audio 1>" not in FINAL_PROMPT:
        raise RuntimeError("E13U01 final prompt is missing <Audio 1>")
    if FINAL_PROMPT.rstrip().splitlines()[-1] != FINAL_AVOID_LINE:
        raise RuntimeError("E13U01 final avoid line is not the last provider-prompt line")
    for required in (
        "SCREEN-TEXT LOCK",
        "CHARACTER IDENTITY LOCK",
        "CONTINUITY LOCK",
        "AUDIO/TEXT SEPARATION",
        "E12U06 final spatial state",
        "C01",
        VISIBLE_TEXT_NAME,
        VISIBLE_TEXT_TITLE,
    ):
        if required not in FINAL_PROMPT:
            raise RuntimeError(f"E13U01 final prompt missing required contract: {required}")


async def _generate(
    *,
    project: Path,
    model: str,
    definition_path: Path,
    prompt: str,
    resource_id: str,
    api_key: str,
    base_url: str,
    reference_images: list[Path] | None = None,
    start_image: Path | None = None,
    end_image: Path | None = None,
    reference_audio_files: list[Path] | None = None,
) -> tuple[Path, int, dict[str, Any]]:
    definition_text = await asyncio.to_thread(definition_path.read_text, encoding="utf-8")
    definition = json.loads(definition_text)
    backend = DeclarativeVideoBackend(
        api_key=api_key,
        base_url=base_url,
        model=model,
        definition=definition,
        provider="autodl",
    )
    generator = MediaGenerator(project, video_backend=backend, video_provider_id="autodl")
    generator.ledger = _NullLedger()

    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "resource_type": "reference_videos",
        "resource_id": resource_id,
        "aspect_ratio": ASPECT_RATIO,
        "duration_seconds": DURATION_SECONDS,
        "resolution": RESOLUTION,
        "generate_audio": True,
        "poll_timeout_seconds": 900,
    }
    if reference_images is not None:
        kwargs["reference_images"] = reference_images
    if start_image is not None:
        kwargs["start_image"] = start_image
    if end_image is not None:
        kwargs["end_image"] = end_image
    if reference_audio_files is not None:
        kwargs["reference_audio_files"] = reference_audio_files

    output_path, version, _video_ref, _video_uri = await generator.generate_video_async(**kwargs)
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
    bridge = refs / "E13U01_stage_C01_bridge.jpg"
    screen = refs / "E13U01_exact_screen.png"
    seed_reference = refs / "E13U01_audio_seed_stage.jpg"
    seed_audio = refs / "E13U01_host_applause_audio.wav"

    _decode_bridge(bridge)
    _make_screen_anchor(screen)
    _make_audio_seed_reference(bridge, seed_reference)

    seed_prompt = AUDIO_SEED_PROMPT.strip()
    seed_video, seed_version, seed_record = await _generate(
        project=project,
        model=AUDIO_SEED_MODEL,
        definition_path=Path("scripts/experiments/autodl_minimax_h3_endpoint.json"),
        prompt=seed_prompt,
        resource_id=f"{UNIT_ID}_AUDIO_SEED",
        api_key=api_key,
        base_url=base_url,
        reference_images=[seed_reference],
    )
    _extract_audio(seed_video, seed_audio)

    final_prompt = FINAL_PROMPT.strip()
    final_video, final_version, final_record = await _generate(
        project=project,
        model=FINAL_MODEL,
        definition_path=Path("scripts/experiments/autodl_minimax_h3_image_audio_endpoint.json"),
        prompt=final_prompt,
        resource_id=UNIT_ID,
        api_key=api_key,
        base_url=base_url,
        start_image=screen,
        end_image=bridge,
        reference_audio_files=[seed_audio],
    )

    seed_duration = await probe_existing_video_duration_seconds(seed_video)
    final_duration = await probe_existing_video_duration_seconds(final_video)

    report = {
        "status": "GENERATED_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v1_screen_identity_continuity_dialogue_detached",
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "audio_seed_model": AUDIO_SEED_MODEL,
        "final_model": FINAL_MODEL,
        "duration_requested_seconds": DURATION_SECONDS,
        "audio_seed_ffprobe_seconds": seed_duration,
        "final_ffprobe_seconds": final_duration,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "canonical_visible_text": [VISIBLE_TEXT_NAME, VISIBLE_TEXT_TITLE],
        "canonical_character": f"{CHARACTER_ID}_{CHARACTER_NAME}",
        "continuity_source": "accepted E12U06 v4 final-stage state embedded in LEFT bridge panel",
        "dialogue_detached_from_final_visual_prompt": True,
        "final_prompt_contains_d_tag": "<d>" in final_prompt,
        "final_prompt_contains_host_dialogue": HOST_DIALOGUE in final_prompt,
        "audio_seed_prompt_sha256": provider_prompt_sha256(seed_prompt),
        "final_provider_prompt_sha256": provider_prompt_sha256(final_prompt),
        "reference_sha256": {
            "bridge": _sha256(bridge),
            "screen": _sha256(screen),
            "audio_seed_reference": _sha256(seed_reference),
            "audio": _sha256(seed_audio),
        },
        "audio_seed": {
            "version": seed_version,
            "provider_duration_seconds": seed_record.get("provider_duration_seconds"),
            "video_sha256": _sha256(seed_video),
            "video_size_bytes": seed_video.stat().st_size,
        },
        "final": {
            "version": final_version,
            "provider_duration_seconds": final_record.get("provider_duration_seconds"),
            "video_sha256": _sha256(final_video),
            "video_size_bytes": final_video.stat().st_size,
        },
    }

    root.mkdir(parents=True, exist_ok=True)
    (root / "E13U01_v1_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E13U01_audio_seed_provider_prompt.txt").write_text(seed_prompt, encoding="utf-8")
    (root / "E13U01_final_provider_prompt.txt").write_text(final_prompt, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
