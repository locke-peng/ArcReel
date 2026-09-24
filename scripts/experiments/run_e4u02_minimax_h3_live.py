"""Paid supplier acceptance for E4U02 v3: C03 identity + text/dialogue locks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import (
    assert_provider_prompt_matches_preview,
    compile_reference_video_provider_prompt,
    provider_prompt_sha256,
)

UNIT_ID = "E4U02"
MODEL = "minimax_h3_zm_u24"
DURATION_SECONDS = 15
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"

ONLY_VISIBLE_TEXT = "给念念打电话"
DIALOGUE_1 = "妈妈，我想你"
DIALOGUE_2 = "妈妈，我在忙"

CHARACTER_ID = "C03"
CHARACTER_NAME = "陆念"
YOUNG_CHARACTER_NAME = "幼年陆念"
YOUNG_CHARACTER_REF = Path("scripts/experiments/fixtures/e4u02/C03_LuNian_young_face.jpg")
CURRENT_CHARACTER_REF = Path("scripts/experiments/fixtures/e4u02/C03_LuNian_current_face.jpg")
SHARED_IDENTITY_REF = CURRENT_CHARACTER_REF
FINAL_AVOID_LINE = "Avoid: BGM、文字字幕、水印"
YOUNG_CHARACTER_SHA256 = "6f0fe84b8e150abce613499536dd614302598767836083209a2aa5e58d60ecde"
CURRENT_CHARACTER_SHA256 = "c92b71c3fe707088dd340d41de9a202e2ab7d02392fef4913b2df6959c4932b0"

PROMPT = f"""subject_definitions:
<Subject 1> is the smartphone/alarm-screen reference derived from <Picture 1>. Preserve the dark phone body, minimal alarm-card layout, and exact Chinese alarm label “{ONLY_VISIBLE_TEXT}”. This phrase is the only readable text permitted anywhere in the complete video.
<Subject 2> is {YOUNG_CHARACTER_NAME}, the official younger-age visual reference for canonical character {CHARACTER_ID} {CHARACTER_NAME}, derived from <Picture 2>. Preserve this exact face identity, dark hair, hairline, eye geometry, brows, nose, mouth, cheek shape, skin tone, and recognizable child likeness in [Shot 2].
<Subject 3> is canonical character {CHARACTER_ID} {CHARACTER_NAME}, derived from <Picture 3>. Preserve this exact face identity, dark hair, hairline, eye geometry, brows, nose, mouth, cheek/jaw shape, skin tone, and recognizable likeness in [Shot 3].
<Subject 2> and <Subject 3> are the SAME PERSON at two ages. They are one canonical character lineage, not two unrelated girls. Use the age-specific reference assigned to each shot; never swap, blend, replace, or invent either face.

summary:
[reference generation] Create one continuous 15-second horizontal cinematic memory sequence in three authored 5-second shots. CHARACTER IDENTITY LOCK — HIGHEST PRIORITY: [Shot 2] must use <Subject 2> from <Picture 2> as the younger {CHARACTER_ID} {CHARACTER_NAME}; [Shot 3] must use <Subject 3> from <Picture 3> as the later-age {CHARACTER_ID} {CHARACTER_NAME}. The two are the same person at different ages. Never generate a generic child, never substitute a different girl, never swap the two age references, and never allow identity drift. VISIBLE-TEXT LOCK — HIGHEST PRIORITY: across every frame, the ONLY readable or legible language is the exact Chinese phrase “{ONLY_VISIBLE_TEXT}”, allowed only on the smartphone alarm label in [Shot 1]. Do not create any other readable letters, Chinese characters, words, numbers, clock digits, status-bar text, labels, buttons, titles, logos, watermarks, captions, subtitles, karaoke text, speech bubbles, or glyph-like pseudo-text. DIALOGUE CHANNEL LOCK — HIGHEST PRIORITY: Dialogue enclosed by <d> is AUDIO-ONLY. Never typeset, transcribe, caption, subtitle, echo, or otherwise visualize any content from <d>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - preserve the phone composition and reproduce only the exact alarm label “{ONLY_VISIBLE_TEXT}”; every other UI field is abstract, icon-only, blank, blurred, or non-linguistic.
<Subject 2> (appears in [Shot 2]): fully_preserved identity - preserve <Picture 2> as the authoritative younger-age face for {CHARACTER_ID} {CHARACTER_NAME}. Keep facial topology, proportions, eyes, brows, nose, mouth, cheeks, hairline, dark hair, and skin tone recognizable. Do not age it upward and do not replace it with another child.
<Subject 3> (appears in [Shot 3]): fully_preserved identity - preserve <Picture 3> as the authoritative later-age face for {CHARACTER_ID} {CHARACTER_NAME}. Keep facial topology, proportions, eyes, brows, nose, mouth, cheek/jaw relationship, hairline, dark hair, and skin tone recognizable. Do not replace it with another child.
Shared identity master: <Picture 4> is the authoritative common facial identity for both ages of C03. For Shot 2, age-specific appearance comes from <Picture 2> but the facial identity remains anchored to <Picture 4>. For Shot 3, age-specific appearance comes from <Picture 3> and the facial identity remains anchored to <Picture 4>.
Cross-age continuity: <Subject 2> and <Subject 3> must read as the SAME PERSON at two ages. Preserve their shared identity cues while respecting each age-specific reference. No face substitution, no random child casting, no identity swap, no identity morph into a third face.

detailed_description:
CHARACTER IDENTITY CONTRACT — HIGHEST PRIORITY: the child in both memory shots is canonical {CHARACTER_ID} {CHARACTER_NAME}. [Shot 2] is locked to the official {YOUNG_CHARACTER_NAME} reference <Picture 2>. [Shot 3] is locked to the official {CHARACTER_NAME} reference <Picture 3>. The viewer must recognize these as two ages of the same person. Do not synthesize either child from prose alone when an assigned visual reference exists. Do not merge the two references into a new face. Do not let hair, eyes, nose, mouth, cheek structure, or overall likeness drift away from the assigned reference.
GLOBAL VISIBLE-TEXT CONTRACT — HIGHEST PRIORITY: “{ONLY_VISIBLE_TEXT}” is the sole readable text allowed in the complete 15-second output. It is allowed only inside the phone screen in [Shot 1]. Every other visible surface must be text-free. Do not show digits, extra UI labels, names, notifications, status-bar numerals, captions, subtitles, titles, watermarks, logos, or invented glyph-like writing. The spoken strings “{DIALOGUE_1}” and “{DIALOGUE_2}” are strictly audio-only and forbidden from appearing visually.
DIALOGUE CHANNEL CONTRACT — HIGHEST PRIORITY: every <d> block controls speech/audio only. Never render any <d> content as on-screen text. No subtitle track, burned-in subtitle, closed-caption styling, lower-third, dialogue card, speech bubble, karaoke line, or textual transcription is permitted. During 00:05-00:15 the lower 30% of the frame contains natural scene imagery only, with no graphic overlay or readable glyphs.

[Shot 1] 00:00-00:05. Tight macro close-up of <Subject 1> on a dark bedside surface at night, vibrating gently. Cool-white screen light against a blue-black room. The alarm interface is intentionally minimal: one centered readable label, exactly “{ONLY_VISIBLE_TEXT}”. All other UI is abstract, icon-only, blank, blurred, or non-linguistic; specifically no readable time digits or secondary labels. Static 50mm close-up, shallow depth of field. No speech. Soft alarm vibration/electronic tone.

[Shot 2] 00:05-00:10. Clean hard cut to a warm, softened phone-memory flashback. <Subject 2>, the official {YOUNG_CHARACTER_NAME} reference from <Picture 2>, is the only child face permitted in this shot. Preserve the reference identity and young-child proportions. She holds a phone with its screen turned away from camera or fully defocused so no UI can be read. She looks upset and calls for her mother. No captions or subtitles. <Subject 2> says in an emotional natural child voice, <d>[Chinese] {DIALOGUE_1}</d>. Slight 50mm push-in, shallow depth of field, subtle telephone-room tone. The spoken words remain audio-only.

[Shot 3] 00:10-00:15. Clean hard cut to a later memory of THE SAME PERSON. <Subject 3>, the official canonical {CHARACTER_ID} {CHARACTER_NAME} reference from <Picture 3>, is the only child face permitted in this shot. Preserve the reference identity exactly; do not reuse a generic face from Shot 2 and do not invent a third face. She glances away with mild impatience while holding the phone low; any screen surface is turned away, dark, or heavily defocused. No readable text anywhere in frame. <Subject 3> says in a casual distracted child voice, <d>[Chinese] {DIALOGUE_2}</d>. Static 50mm medium close-up. End on the child's averted gaze. The spoken words remain audio-only.

overall_soundscape:
Shot 1: restrained alarm vibration/electronic tone and quiet night ambience. Shot 2: natural child speech from <d> plus faint phone-room tone. Shot 3: natural child speech from <d> plus faint phone-room tone. The <d> strings are audio-only and must never be visualized.

non_diegetic_music:
N/A
${FINAL_AVOID_LINE}"""


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


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
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://api.minimaxi.com/v1"

    _assert_identity_fixtures()

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    refs_dir = project / "fixtures"
    phone = refs_dir / "phone_alarm_exact_text.png"
    _make_phone_reference(phone)

    request_assets = [
        Entry(Ref("object", "E4U02手机闹钟")),
        Entry(Ref("character", YOUNG_CHARACTER_NAME)),
        Entry(Ref("character", f"{CHARACTER_ID}_{CHARACTER_NAME}")),
        Entry(Ref("character", f"{CHARACTER_ID}_{CHARACTER_NAME}_identity_master")),
    ]
    payload = {
        "prompt_compiler": "h3_ref2va",
        "reference_image_labels": [
            "E4U02手机闹钟",
            YOUNG_CHARACTER_NAME,
            f"{CHARACTER_ID}_{CHARACTER_NAME}",
            f"{CHARACTER_ID}_{CHARACTER_NAME}_identity_master",
        ],
    }

    preview = compile_reference_video_provider_prompt(
        source_prompt=PROMPT,
        fallback_prompt=PROMPT,
        model_name=MODEL,
        duration_seconds=DURATION_SECONDS,
        request_assets=request_assets,
        payload=payload,
        max_prompt_chars=500000,
        unit_id=UNIT_ID,
    )
    if preview.provider_prompt != PROMPT.strip():
        raise RuntimeError("E4U02 v3 prompt changed during compilation")

    preview_sha = provider_prompt_sha256(preview.provider_prompt)
    runtime = compile_reference_video_provider_prompt(
        source_prompt=PROMPT,
        fallback_prompt=PROMPT,
        model_name=MODEL,
        duration_seconds=DURATION_SECONDS,
        request_assets=request_assets,
        payload=payload,
        max_prompt_chars=500000,
        unit_id=UNIT_ID,
    )
    assert_provider_prompt_matches_preview(
        provider_prompt=runtime.provider_prompt,
        expected_sha256=preview_sha,
    )
    if preview.provider_prompt != runtime.provider_prompt:
        raise RuntimeError("preview/runtime prompt text mismatch")

    if runtime.provider_prompt.count(ONLY_VISIBLE_TEXT) < 4:
        raise RuntimeError("visible-text whitelist is not reinforced strongly enough")
    for spoken in (DIALOGUE_1, DIALOGUE_2):
        if f"<d>[Chinese] {spoken}</d>" not in runtime.provider_prompt:
            raise RuntimeError(f"missing audio dialogue tag: {spoken}")
    for required_rule in (
        "CHARACTER IDENTITY LOCK",
        "SAME PERSON",
        "never swap",
        "No face substitution",
        "AUDIO-ONLY",
        "Never render any <d> content as on-screen text",
        "sole readable text allowed",
        "forbidden from appearing visually",
        "shared canonical C03",
        FINAL_AVOID_LINE,
    ):
        if required_rule not in runtime.provider_prompt:
            raise RuntimeError(f"missing E4U02 v3 guard: {required_rule}")

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
        prompt=runtime.provider_prompt,
        resource_type="reference_videos",
        resource_id=UNIT_ID,
        reference_images=[phone, YOUNG_CHARACTER_REF, CURRENT_CHARACTER_REF, SHARED_IDENTITY_REF],
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
        "repair_version": "v3_identity_lock",
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "model": MODEL,
        "generation_mode": runtime.generation_mode,
        "duration_requested_seconds": DURATION_SECONDS,
        "provider_duration_seconds": provider_duration,
        "ffprobe_video_duration_seconds": probed_duration,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "reference_count": 4,
        "character_identity_lock": f"{CHARACTER_ID}_{CHARACTER_NAME}",
        "young_variant_asset": YOUNG_CHARACTER_NAME,
        "same_character_lineage": True,
        "only_legal_visible_text": ONLY_VISIBLE_TEXT,
        "dialogue_visualization_forbidden": [DIALOGUE_1, DIALOGUE_2],
        "provider_prompt_chars": len(runtime.provider_prompt),
        "provider_prompt_sha256": preview_sha,
        "preview_runtime_prompt_equal": True,
        "reference_sha256": {
            "phone": _sha256(phone),
            "young_character": _sha256(YOUNG_CHARACTER_REF),
            "current_character": _sha256(CURRENT_CHARACTER_REF),
            "shared_identity_master": _sha256(SHARED_IDENTITY_REF),
        },
        "version": version,
        "version_duration_seconds": record.get("duration_seconds"),
        "video_size_bytes": output_path.stat().st_size,
        "video_sha256": _sha256(output_path),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "E4U02_v3_identity_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E4U02_v3_identity_final_provider_prompt.txt").write_text(
        runtime.provider_prompt,
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
