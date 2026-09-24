"""Paid E4U02 acceptance: C03 identity lock with dialogue detached into <Audio 1>."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256

UNIT_ID = "E4U02"
MODEL = "minimax_h3_image_audio_to_video_v2_15s"
DURATION_SECONDS = 15
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"

ONLY_VISIBLE_TEXT = "给念念打电话"
FORBIDDEN_DIALOGUE_1 = "妈妈，我想你"
FORBIDDEN_DIALOGUE_2 = "妈妈，我在忙"

CHARACTER_ID = "C03"
YOUNG_CHARACTER_REF = Path("scripts/experiments/fixtures/e4u02/C03_LuNian_young_face.jpg")
CURRENT_CHARACTER_REF = Path("scripts/experiments/fixtures/e4u02/C03_LuNian_current_face.jpg")
YOUNG_CHARACTER_SHA256 = "6f0fe84b8e150abce613499536dd614302598767836083209a2aa5e58d60ecde"
CURRENT_CHARACTER_SHA256 = "c92b71c3fe707088dd340d41de9a202e2ab7d02392fef4913b2df6959c4932b0"

FINAL_AVOID_LINE = (
    "Avoid: BGM, subtitles, captions, dialogue transcription, speech bubbles, "
    "lower-thirds, watermarks, logos, timestamps, and any visible text except the approved phone label."
)

PROMPT = f"""subject_definitions:
<Subject 1> is the smartphone alarm interface derived from <Picture 1>. Preserve the dark phone body, minimal alarm-card layout, and the exact approved phone label "{ONLY_VISIBLE_TEXT}". This is the only readable text permitted anywhere in the complete video.
<Subject 2> is the younger-age appearance of canonical character C03, derived from the LEFT portrait in <Picture 2>. Preserve the younger child age, dark hair, eye geometry, brows, nose, mouth, cheek structure, skin tone, and recognizable facial identity.
<Subject 3> is the later-age appearance of the SAME canonical character C03, derived from the RIGHT portrait in <Picture 2>. Preserve the later child age, dark hair, eye geometry, brows, nose, mouth, cheek/jaw structure, skin tone, and recognizable facial identity.
<Picture 2> is a two-age identity bridge for one canonical character: LEFT is the younger age and RIGHT is the later age. The two portraits are the SAME PERSON at different ages, never two unrelated girls.
<Audio 1> is the synchronized source soundtrack for the complete target video. Reuse this audio signal as the target soundtrack. Its spoken content is audio-only and must never be rendered as visible text.

summary:
[reference generation + audio reuse] Create one continuous 15-second horizontal cinematic memory sequence in three authored 5-second shots. CHARACTER IDENTITY LOCK — HIGHEST PRIORITY: both memory shots depict one canonical C03 person. [Shot 2] uses the LEFT younger portrait from <Picture 2>; [Shot 3] uses the RIGHT later portrait from <Picture 2>. Never cast a generic child, never swap the two ages, and never create a third face. VISIBLE-TEXT LOCK — HIGHEST PRIORITY: the exact approved phone label "{ONLY_VISIBLE_TEXT}" from <Subject 1> is the sole readable text in the entire output and may appear only on the phone in [Shot 1]. AUDIO/TEXT SEPARATION — HIGHEST PRIORITY: copy <Audio 1> as audible sound while keeping every spoken passage non-visual. Do not create subtitles, captions, dialogue transcription, karaoke text, lower-thirds, speech bubbles, or glyph-like pseudo-text.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - preserve the phone layout and reproduce only the exact approved label from <Picture 1>; all other interface fields remain abstract, icon-only, blank, blurred, or non-linguistic.
<Subject 2> (appears in [Shot 2]): fully_preserved - preserve the LEFT younger-age C03 portrait from <Picture 2>, including the recognizable facial identity and child proportions.
<Subject 3> (appears in [Shot 3]): fully_preserved - preserve the RIGHT later-age C03 portrait from <Picture 2>, including the recognizable facial identity and later child proportions.
<Picture 2> (cross-age identity bridge): fully_preserved - use its LEFT and RIGHT portraits as two ages of one canonical identity. No face substitution, random recasting, identity swap, or morph into a third face.
<Audio 1>: fully_copy - reuse <Audio 1> as the complete synchronized target soundtrack. Its speech remains audible only; no verbal content from the audio is converted into visible text.

detailed_description:
CHARACTER IDENTITY CONTRACT — HIGHEST PRIORITY: [Shot 2] and [Shot 3] are the same C03 child at two ages. Match the LEFT and RIGHT portraits in <Picture 2> respectively. Preserve the shared eyes, brow family, nose, mouth, cheek structure, dark-hair family, skin tone, and overall likeness so the age change reads as one person growing older.
GLOBAL VISIBLE-TEXT CONTRACT — HIGHEST PRIORITY: the approved phone label "{ONLY_VISIBLE_TEXT}" is the sole readable text allowed in the complete 15-second output. Every other visible surface must be text-free. No clock digits, secondary phone labels, names, notifications, status-bar numerals, subtitles, captions, titles, watermarks, logos, or invented glyph-like writing.
AUDIO/TEXT SEPARATION CONTRACT — HIGHEST PRIORITY: <Audio 1> supplies the soundtrack directly. Do not transcribe, quote, typeset, subtitle, caption, or otherwise visualize any spoken content from <Audio 1>. During 00:05-00:15 the lower 35 percent of frame contains natural scene imagery only, with no graphic overlay, caption strip, or readable glyphs.

[Shot 1] 00:00-00:05. Tight macro close-up of <Subject 1> on a dark bedside surface at night, vibrating gently. Cool-white screen light against a blue-black room. The alarm interface is intentionally minimal: one centered readable label, exactly "{ONLY_VISIBLE_TEXT}". All other UI is abstract, icon-only, blank, blurred, or non-linguistic; specifically no readable time digits or secondary labels. Static 50mm close-up, shallow depth of field. Follow the first five seconds of <Audio 1> exactly.

[Shot 2] 00:05-00:10. Clean hard cut to a warm phone-memory flashback. <Subject 2>, matching the LEFT younger C03 portrait from <Picture 2>, is the only child face permitted. She holds a phone against her cheek with its screen fully turned away or defocused. Her expression is upset and emotionally dependent. Synchronize her natural phone-call lip motion and performance to the first child-speech passage already present in <Audio 1>; do not print or display what is spoken. Slight 50mm push-in, shallow depth of field. No graphic overlay and no visible text.

[Shot 3] 00:10-00:15. Clean hard cut to a later memory of THE SAME PERSON. <Subject 3>, matching the RIGHT later-age C03 portrait from <Picture 2>, is the only child face permitted. She glances away with mild impatience while holding the phone low; the screen is turned away, dark, or heavily defocused. Synchronize her natural lip motion and performance to the later child-speech passage already present in <Audio 1>; do not print or display what is spoken. Static 50mm medium close-up. End on the child's averted gaze. No graphic overlay and no visible text.

overall_soundscape:
<Audio 1> is reused as the complete synchronized soundtrack. Do not synthesize replacement dialogue from prompt text, because no dialogue transcript is present in this visual prompt. Keep the soundtrack audible while keeping all spoken content non-visual.

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
    raise RuntimeError("No CJK font found; install fonts-noto-cjk before running E4U02 live test")


def _make_phone_reference(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (9, 14, 24))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((410, 55, 870, 665), radius=46, fill=(18, 21, 28), outline=(76, 84, 102), width=5)
    draw.rounded_rectangle((442, 100, 838, 620), radius=30, fill=(235, 240, 246))
    draw.rounded_rectangle((495, 210, 785, 430), radius=24, fill=(251, 252, 253), outline=(194, 202, 213), width=3)
    draw.ellipse((610, 155, 670, 215), outline=(96, 105, 120), width=5)
    draw.line((640, 165, 640, 185), fill=(96, 105, 120), width=4)
    draw.line((640, 185, 655, 195), fill=(96, 105, 120), width=4)
    font = _font(44)
    bbox = draw.textbbox((0, 0), ONLY_VISIBLE_TEXT, font=font)
    width = bbox[2] - bbox[0]
    draw.text(((1280 - width) / 2, 285), ONLY_VISIBLE_TEXT, font=font, fill=(20, 24, 31))
    draw.rounded_rectangle((530, 485, 750, 525), radius=20, fill=(205, 212, 221))
    image.save(path, format="PNG", optimize=True)


def _assert_identity_fixtures() -> None:
    expected = {
        YOUNG_CHARACTER_REF: YOUNG_CHARACTER_SHA256,
        CURRENT_CHARACTER_REF: CURRENT_CHARACTER_SHA256,
    }
    for fixture, expected_sha in expected.items():
        if not fixture.is_file():
            raise RuntimeError(f"canonical character fixture missing: {fixture}")
        actual_sha = _sha256(fixture)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"canonical character fixture SHA mismatch for {fixture}: {actual_sha} != {expected_sha}"
            )


def _make_identity_bridge(path: Path) -> None:
    _assert_identity_fixtures()
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (1280, 720), (236, 236, 236))
    targets = ((40, 40, 620, 680), (660, 40, 1240, 680))
    for source_path, box in zip((YOUNG_CHARACTER_REF, CURRENT_CHARACTER_REF), targets, strict=True):
        with Image.open(source_path) as source:
            portrait = source.convert("RGB")
            target_w = box[2] - box[0]
            target_h = box[3] - box[1]
            scale = max(target_w / portrait.width, target_h / portrait.height)
            resized = portrait.resize(
                (round(portrait.width * scale), round(portrait.height * scale)),
                Image.Resampling.LANCZOS,
            )
            left = max(0, (resized.width - target_w) // 2)
            top = max(0, (resized.height - target_h) // 2)
            crop = resized.crop((left, top, left + target_w, top + target_h))
            canvas.paste(crop, (box[0], box[1]))
    canvas.save(path, format="JPEG", quality=96, optimize=True)


def _assert_provider_prompt_contract() -> None:
    if "<d>" in PROMPT or "</d>" in PROMPT:
        raise RuntimeError("dialogue tags leaked into E4U02 detached visual prompt")
    for spoken in (FORBIDDEN_DIALOGUE_1, FORBIDDEN_DIALOGUE_2):
        if spoken in PROMPT:
            raise RuntimeError(f"dialogue text leaked into E4U02 detached visual prompt: {spoken}")
    if "<Audio 1>" not in PROMPT:
        raise RuntimeError("E4U02 detached prompt is missing <Audio 1>")
    if PROMPT.count(ONLY_VISIBLE_TEXT) < 4:
        raise RuntimeError("visible-text whitelist is not reinforced strongly enough")
    if PROMPT.rstrip().splitlines()[-1] != FINAL_AVOID_LINE:
        raise RuntimeError("final avoid line is not the last provider-prompt line")


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://autodl.art"

    audio_env = os.environ.get("E4U02_AUDIO_REF", "").strip()
    if not audio_env:
        raise RuntimeError("E4U02_AUDIO_REF is required for dialogue-detached supplier acceptance")
    audio_ref = Path(audio_env)
    if not audio_ref.is_file() or audio_ref.stat().st_size <= 0:
        raise RuntimeError(f"E4U02 audio reference is missing: {audio_ref}")

    _assert_identity_fixtures()
    _assert_provider_prompt_contract()

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    refs_dir = project / "fixtures"
    phone = refs_dir / "phone_alarm_exact_text.png"
    identity_bridge = refs_dir / "C03_two_age_identity_bridge.jpg"
    _make_phone_reference(phone)
    _make_identity_bridge(identity_bridge)

    provider_prompt = PROMPT.strip()
    prompt_sha = provider_prompt_sha256(provider_prompt)

    definition = json.loads(
        Path("scripts/experiments/autodl_minimax_h3_image_audio_endpoint.json").read_text(encoding="utf-8")
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
        prompt=provider_prompt,
        resource_type="reference_videos",
        resource_id=UNIT_ID,
        start_image=phone,
        end_image=identity_bridge,
        reference_audio_files=[audio_ref],
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=DURATION_SECONDS,
        resolution=RESOLUTION,
        generate_audio=True,
        poll_timeout_seconds=900,
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("provider returned no video artifact")

    versions_path = project / "versions" / "versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8"))
    record = versions["reference_videos"][UNIT_ID]["versions"][-1]
    provider_duration = record.get("provider_duration_seconds")
    if type(provider_duration) is not int or provider_duration <= 0:
        raise RuntimeError(f"provider_duration_seconds was not persisted: {provider_duration!r}")

    probed_duration = await probe_existing_video_duration_seconds(output_path)
    report = {
        "status": "GENERATED_PENDING_VISUAL_REVIEW",
        "unit_id": UNIT_ID,
        "repair_version": "v4_dialogue_detached",
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "model": MODEL,
        "duration_requested_seconds": DURATION_SECONDS,
        "provider_duration_seconds": provider_duration,
        "ffprobe_video_duration_seconds": probed_duration,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "image_reference_count": 2,
        "audio_reference_count": 1,
        "character_identity_lock": CHARACTER_ID,
        "same_character_lineage": True,
        "only_legal_visible_text": ONLY_VISIBLE_TEXT,
        "dialogue_text_detached_from_provider_prompt": True,
        "provider_prompt_contains_d_tag": "<d>" in provider_prompt,
        "provider_prompt_contains_forbidden_dialogue": any(
            spoken in provider_prompt for spoken in (FORBIDDEN_DIALOGUE_1, FORBIDDEN_DIALOGUE_2)
        ),
        "provider_prompt_chars": len(provider_prompt),
        "provider_prompt_sha256": prompt_sha,
        "reference_sha256": {
            "phone": _sha256(phone),
            "identity_bridge": _sha256(identity_bridge),
            "young_character": _sha256(YOUNG_CHARACTER_REF),
            "current_character": _sha256(CURRENT_CHARACTER_REF),
            "audio": _sha256(audio_ref),
        },
        "version": version,
        "version_duration_seconds": record.get("duration_seconds"),
        "video_size_bytes": output_path.stat().st_size,
        "video_sha256": _sha256(output_path),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "E4U02_v4_dialogue_detached_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E4U02_v4_dialogue_detached_final_provider_prompt.txt").write_text(
        provider_prompt,
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
