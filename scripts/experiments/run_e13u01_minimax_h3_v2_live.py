"""Paid E13U01 v2 acceptance: deterministic identity screen + H3 C01 entrance + detached audio."""

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

UNIT_ID = "E13U01"
DURATION_SECONDS = 10
SHOT_SECONDS = 5
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"

AUDIO_SEED_MODEL = "minimax_h3_zm_u24"
ENTRY_VISUAL_MODEL = "minimax_h3_zm_u24"

VISIBLE_TEXT_NAME = "沈知意"
VISIBLE_TEXT_TITLE = "天枢联合创始人"
HOST_DIALOGUE = "欢迎沈知意"

CHARACTER_ID = "C01"
CHARACTER_NAME = "沈知意"
BRIDGE_B64_PART_GLOB = "e13u01_stage_c01_bridge.jpg.b64.part.*"
BRIDGE_SHA256 = "fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135"

ENTRY_FINAL_AVOID_LINE = (
    "Avoid: readable text, letters, digits, signs, subtitles, captions, dialogue transcription, "
    "logos, watermarks, LED-screen content, extra people, face drift, alternate wardrobe, BGM."
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

ENTRY_PROMPT = f"""subject_definitions:
<Subject 1> is a continuity-and-identity bridge. Its LEFT panel is the accepted final stage-wing geometry from the preceding unit: an already-open side door directly attached to the immediate stage edge, a short threshold, dark wall panels, blue-black summit lighting, and a white spotlight rising from the stage edge. Its RIGHT panel is the canonical C01 lead woman in a white professional pantsuit. Preserve her exact face topology, dark hair, hairline, eye geometry, brows, nose, mouth, cheek/jaw structure, skin tone, white suit silhouette, gray structured handbag, and recognizable identity.

summary:
[reference generation; visual-only entrance plate] Create one continuous 10-second horizontal cinematic entrance shot. At the VERY FIRST FRAME the canonical C01 woman is already visibly crossing the open side-door threshold. Within the first second she is fully through the doorway. Over the next three seconds she takes one to two calm controlled steps directly into the established white spotlight. From 00:04 onward she settles into a poised slow walk/hold in the light. Preserve the exact stage-wing geometry and exact canonical face. Frame only the side door, immediate stage edge, spotlight, and the woman. The main LED screen is completely outside frame. No readable signage, exit sign, letters, digits, logos, captions, subtitles, watermarks, or pseudo-text anywhere.

retention_analysis:
<Subject 1> LEFT panel: fully_preserved spatial continuity - preserve the same open side door, short direct threshold, dark stage-wing wall, blue-black event lighting, stage-floor relationship, and white spotlight source. Do not create a corridor, lobby, detached doorway, stairs, or alternate venue.
<Subject 1> RIGHT panel: fully_preserved character identity - preserve the canonical C01 woman's face, hairstyle family, white professional suit, body proportions, gray structured handbag, and calm controlled presence. No face substitution. No generic businesswoman, no alternate actress, no wardrobe replacement.

detailed_description:
CONTINUITY CONTRACT — HIGHEST PRIORITY: the first frame begins at the same physical side-door/stage-edge state as the accepted previous unit. The doorway is already open and directly touches the stage edge. Keep the threshold short and the spotlight source in the same relationship to the door.
CHARACTER IDENTITY CONTRACT — HIGHEST PRIORITY: use the RIGHT-panel C01 woman as the only principal person. Preserve the same recognizable face and white suit in every frame. Never recast or morph her.
FRAME CONTRACT — HIGHEST PRIORITY: medium 50mm eye-level composition focused tightly on the doorway, the woman, and the spotlight. The giant LED screen, sponsor panels, audience screens, signs, and any readable display are outside the frame. Any unavoidable distant surface is dark, blank, defocused, and non-linguistic.
TEXT CONTRACT — HIGHEST PRIORITY: this provider shot contains ZERO readable text. No Chinese, English, numbers, exit lettering, subtitles, captions, logos, watermarks, badges, labels, or pseudo-text.
AUDIO CONTRACT: visual generation only. Canonical host speech and applause are added later by ArcReel post-production. Do not infer dialogue and do not create subtitles.

[Entrance Shot] 00:00-00:10. At 00:00 the C01 woman is already crossing the open side-door threshold, not waiting backstage. By 00:01 she is fully through. She takes one to two measured steps into the existing white spotlight while carrying the gray structured handbag. Slow 0.4-meter push-in, medium framing, eye level. Blue-black summit light stays consistent with the preceding unit. The camera never pans to the LED screen. From 00:04 to 00:10 she remains poised in the spotlight with subtle natural movement, preserving face identity. No other principal person and no readable text.

overall_soundscape:
N/A for this visual plate. Canonical audio is muxed later.

non_diegetic_music:
N/A
{ENTRY_FINAL_AVOID_LINE}"""


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


def _font_path() -> str:
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("No CJK font found; install fonts-noto-cjk before E13U01 live test")


def _decode_bridge(path: Path) -> None:
    parts = sorted(Path(".github/live-tests").glob(BRIDGE_B64_PART_GLOB))
    if not parts:
        raise RuntimeError("E13U01 bridge chunks are missing")
    raw = "".join("".join(part.read_text(encoding="utf-8").split()) for part in parts)
    data = base64.b64decode(raw, validate=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    actual = _sha256(path)
    if actual != BRIDGE_SHA256:
        raise RuntimeError(f"E13U01 bridge SHA mismatch: {actual} != {BRIDGE_SHA256}")


def _make_screen_anchor(path: Path) -> None:
    from PIL import ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (2, 3, 5))
    draw = ImageDraw.Draw(image)
    name_font = ImageFont.truetype(_font_path(), size=92)
    title_font = ImageFont.truetype(_font_path(), size=56)

    name_box = draw.textbbox((0, 0), VISIBLE_TEXT_NAME, font=name_font)
    title_box = draw.textbbox((0, 0), VISIBLE_TEXT_TITLE, font=title_font)
    name_w = name_box[2] - name_box[0]
    title_w = title_box[2] - title_box[0]

    draw.text(((1280 - name_w) / 2, 220), VISIBLE_TEXT_NAME, font=name_font, fill=(245, 245, 245))
    draw.text(((1280 - title_w) / 2, 365), VISIBLE_TEXT_TITLE, font=title_font, fill=(235, 235, 235))
    image.save(path, format="PNG", optimize=True)


def _make_entry_reference(bridge: Path, path: Path) -> None:
    """Remove the LED-screen area from the H3 visual reference while retaining door/spotlight + C01."""
    with Image.open(bridge) as source_image:
        source = source_image.convert("RGB")
        # The source bridge is 960x540. Its stage reference occupies the left region and
        # its canonical C01 full-body portrait occupies the right region.
        stage = source.crop((0, 115, 455, 525))
        # Blank the small exit-sign area so it cannot seed readable signage.
        stage_draw = ImageDraw.Draw(stage)
        stage_draw.rectangle((50, 0, 145, 70), fill=(12, 13, 16))
        character = source.crop((640, 0, 940, 540))

        canvas = Image.new("RGB", (1280, 720), (5, 6, 9))

        stage_scale = min(800 / stage.width, 610 / stage.height)
        stage_resized = stage.resize(
            (round(stage.width * stage_scale), round(stage.height * stage_scale)),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(stage_resized, (35, (720 - stage_resized.height) // 2))

        char_scale = min(350 / character.width, 650 / character.height)
        char_resized = character.resize(
            (round(character.width * char_scale), round(character.height * char_scale)),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(char_resized, (895, (720 - char_resized.height) // 2))

        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path, format="JPEG", quality=96, optimize=True)


def _make_audio_seed_reference(entry_reference: Path, path: Path) -> None:
    with Image.open(entry_reference) as source_image:
        source = source_image.convert("RGB")
        stage_only = source.crop((0, 0, 860, 720))
        canvas = Image.new("RGB", (1280, 720), (5, 7, 12))
        canvas.paste(stage_only, (0, 0))
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
        raise RuntimeError("failed to extract E13U01 host/applause audio seed")


def _build_final_video(screen: Path, entry_visual: Path, audio: Path, output: Path) -> None:
    """Author the two canonical five-second shots deterministically, then mux canonical audio."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f"{output.stem}_authoring.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "24",
            "-t",
            str(SHOT_SECONDS),
            "-i",
            str(screen),
            "-i",
            str(entry_visual),
            "-i",
            str(audio),
            "-filter_complex",
            (
                "[0:v]scale=1280:720,format=yuv420p,"
                "fade=t=in:st=0:d=0.20,trim=duration=5,setpts=PTS-STARTPTS[v0];"
                "[1:v]trim=start=0:end=5,setpts=PTS-STARTPTS,"
                "scale=1280:720:force_original_aspect_ratio=increase,"
                "crop=1280:720,format=yuv420p[v1];"
                "[v0][v1]concat=n=2:v=1:a=0[v]"
            ),
            "-map",
            "[v]",
            "-map",
            "2:a:0",
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
        raise RuntimeError("failed to author E13U01 v2 final video")
    os.replace(temp, output)


def _assert_contracts() -> None:
    if f"<d>[Chinese] {HOST_DIALOGUE}</d>" not in AUDIO_SEED_PROMPT:
        raise RuntimeError("audio seed is missing canonical host dialogue")
    if "<d>" in ENTRY_PROMPT or "</d>" in ENTRY_PROMPT:
        raise RuntimeError("dialogue tag leaked into E13U01 v2 visual provider prompt")
    if HOST_DIALOGUE in ENTRY_PROMPT:
        raise RuntimeError("host dialogue leaked into E13U01 v2 visual provider prompt")
    if any("\u3400" <= char <= "\u4dbf" or "\u4e00" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff" for char in ENTRY_PROMPT):
        raise RuntimeError("CJK text leaked into E13U01 v2 H3 entrance prompt")
    if ENTRY_PROMPT.rstrip().splitlines()[-1] != ENTRY_FINAL_AVOID_LINE:
        raise RuntimeError("E13U01 v2 final avoid line is not the last entrance-prompt line")
    for required in (
        "VERY FIRST FRAME",
        "already visibly crossing",
        "main LED screen is completely outside frame",
        "ZERO readable text",
        "canonical C01",
        "CONTINUITY CONTRACT",
        "CHARACTER IDENTITY CONTRACT",
    ):
        if required not in ENTRY_PROMPT:
            raise RuntimeError(f"E13U01 v2 entrance prompt missing contract: {required}")


async def _generate(
    *,
    project: Path,
    model: str,
    prompt: str,
    resource_id: str,
    api_key: str,
    base_url: str,
    reference_images: list[Path],
) -> tuple[Path, int, dict[str, Any]]:
    definition_text = await asyncio.to_thread(
        Path("scripts/experiments/autodl_minimax_h3_endpoint.json").read_text,
        encoding="utf-8",
    )
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

    output_path, version, _video_ref, _video_uri = await generator.generate_video_async(
        prompt=prompt,
        resource_type="reference_videos",
        resource_id=resource_id,
        reference_images=reference_images,
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=DURATION_SECONDS,
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

    root = Path("live_artifacts") / f"{UNIT_ID}_V2"
    project = root / "project"
    refs = project / "fixtures"
    source_bridge = refs / "E13U01_stage_C01_bridge_source.jpg"
    entry_reference = refs / "E13U01_entry_reference.jpg"
    screen = refs / "E13U01_exact_screen.png"
    audio_seed_reference = refs / "E13U01_audio_seed_stage.jpg"
    audio = refs / "E13U01_host_applause_audio.wav"

    _decode_bridge(source_bridge)
    _make_entry_reference(source_bridge, entry_reference)
    _make_screen_anchor(screen)
    _make_audio_seed_reference(entry_reference, audio_seed_reference)

    seed_prompt = AUDIO_SEED_PROMPT.strip()
    seed_video, seed_version, seed_record = await _generate(
        project=project,
        model=AUDIO_SEED_MODEL,
        prompt=seed_prompt,
        resource_id=f"{UNIT_ID}_V2_AUDIO_SEED",
        api_key=api_key,
        base_url=base_url,
        reference_images=[audio_seed_reference],
    )
    _extract_audio(seed_video, audio)

    entry_prompt = ENTRY_PROMPT.strip()
    entry_video, entry_version, entry_record = await _generate(
        project=project,
        model=ENTRY_VISUAL_MODEL,
        prompt=entry_prompt,
        resource_id=f"{UNIT_ID}_V2_ENTRY",
        api_key=api_key,
        base_url=base_url,
        reference_images=[entry_reference],
    )

    entry_provider_duration = await probe_existing_video_duration_seconds(entry_video)
    final_video = project / "reference_videos" / f"{UNIT_ID}.mp4"
    raw_entry = root / "E13U01_v2_entry_provider_raw.mp4"
    raw_entry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(entry_video, raw_entry)
    await asyncio.to_thread(_build_final_video, screen, raw_entry, audio, final_video)
    final_duration = await probe_existing_video_duration_seconds(final_video)

    report = {
        "status": "GENERATED_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v2_deterministic_screen_h3_entry_postmux",
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "audio_seed_model": AUDIO_SEED_MODEL,
        "entry_visual_model": ENTRY_VISUAL_MODEL,
        "duration_requested_seconds": DURATION_SECONDS,
        "final_authored_duration_seconds": final_duration,
        "entry_provider_duration_seconds": entry_provider_duration,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "shot1_authoring": "deterministic 5s exact screen anchor",
        "shot2_authoring": "first 5s of H3 C01 entrance plate",
        "canonical_visible_text": [VISIBLE_TEXT_NAME, VISIBLE_TEXT_TITLE],
        "canonical_character": f"{CHARACTER_ID}_{CHARACTER_NAME}",
        "continuity_source": "accepted E12U06 v4 stage-wing geometry embedded in entrance reference",
        "dialogue_detached_from_entry_provider_prompt": True,
        "entry_provider_prompt_contains_cjk": any(
            "\u3400" <= char <= "\u4dbf" or "\u4e00" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff"
            for char in entry_prompt
        ),
        "entry_provider_prompt_contains_d_tag": "<d>" in entry_prompt,
        "entry_provider_prompt_contains_host_dialogue": HOST_DIALOGUE in entry_prompt,
        "audio_seed_prompt_sha256": provider_prompt_sha256(seed_prompt),
        "entry_provider_prompt_sha256": provider_prompt_sha256(entry_prompt),
        "reference_sha256": {
            "source_bridge": _sha256(source_bridge),
            "entry_reference": _sha256(entry_reference),
            "screen": _sha256(screen),
            "audio_seed_reference": _sha256(audio_seed_reference),
            "audio": _sha256(audio),
        },
        "audio_seed": {
            "version": seed_version,
            "provider_duration_seconds": seed_record.get("provider_duration_seconds"),
            "video_sha256": _sha256(seed_video),
        },
        "entry": {
            "version": entry_version,
            "provider_duration_seconds": entry_record.get("provider_duration_seconds"),
            "video_sha256": _sha256(raw_entry),
        },
        "final": {
            "video_size_bytes": final_video.stat().st_size,
            "video_sha256": _sha256(final_video),
        },
    }

    root.mkdir(parents=True, exist_ok=True)
    (root / "E13U01_v2_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E13U01_v2_audio_seed_provider_prompt.txt").write_text(seed_prompt, encoding="utf-8")
    (root / "E13U01_v2_entry_provider_prompt.txt").write_text(entry_prompt, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
