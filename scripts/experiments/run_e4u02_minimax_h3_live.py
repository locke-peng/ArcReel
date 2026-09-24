"""Paid supplier acceptance test for E4U02 v2 visible-text/dialogue-visualization repair."""
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

PROMPT = f"""subject_definitions:
<Subject 1> is the smartphone/alarm-screen reference derived from <Picture 1>. Preserve the dark phone body, cool-white alarm-card layout, and the exact six-character Chinese alarm label “{ONLY_VISIBLE_TEXT}”. This exact label is the only readable text permitted anywhere in the entire video.
<Subject 2> is the younger-child memory reference derived from <Picture 2>. Preserve the child's identity and clothing. The reference contains no readable text.
<Subject 3> is the older-child memory reference derived from <Picture 3>. Preserve the child's identity and clothing. The reference contains no readable text.

summary:
[reference generation] Create one continuous 15-second horizontal cinematic memory sequence in three authored 5-second shots. Highest-priority visible-text contract: across every frame, the ONLY readable or legible language is the exact Chinese phrase “{ONLY_VISIBLE_TEXT}”, and it may appear only on the smartphone alarm label in [Shot 1]. Do not create any other readable letters, Chinese characters, words, numbers, clock digits, status-bar text, labels, buttons, titles, logos, watermarks, captions, subtitles, karaoke text, speech bubbles, or glyph-like pseudo-text. Dialogue enclosed by <d> is AUDIO-ONLY. Never typeset, transcribe, caption, subtitle, echo, or otherwise visualize any content from <d>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - preserve the referenced phone composition and reproduce only the exact alarm label “{ONLY_VISIBLE_TEXT}”; replace every other UI field with non-linguistic abstract shapes/icons.
<Subject 2> (appears in [Shot 2]): fully_preserved - preserve identity and childlike proportions; no visible text.
<Subject 3> (appears in [Shot 3]): fully_preserved - preserve identity and the older-child look; no visible text.

detailed_description:
GLOBAL VISIBLE-TEXT CONTRACT — HIGHEST PRIORITY: “{ONLY_VISIBLE_TEXT}” is the sole readable text allowed in the complete 15-second output. It is allowed only inside the phone screen in [Shot 1]. Every other visible surface must be text-free. Do not show digits, extra UI labels, names, notifications, status-bar numerals, captions, subtitles, titles, watermarks, logos, or invented glyph-like writing. The spoken strings “{DIALOGUE_1}” and “{DIALOGUE_2}” are strictly audio-only and are forbidden from appearing visually.
DIALOGUE CHANNEL CONTRACT — HIGHEST PRIORITY: every <d> block controls speech/audio only. Never render any <d> content as on-screen text. No subtitle track, burned-in subtitle, closed-caption styling, lower-third, dialogue card, speech bubble, karaoke line, or textual transcription is permitted.

[Shot 1] 00:00-00:05. Tight macro close-up of <Subject 1> on a dark bedside surface at night, vibrating gently. Cool-white screen light against a blue-black room. The alarm interface is intentionally minimal: one centered readable label, exactly “{ONLY_VISIBLE_TEXT}”. All other UI is abstract, icon-only, blank, blurred, or non-linguistic; specifically no readable time digits or secondary labels. Static 50mm close-up, shallow depth of field. No speech. Soft alarm vibration/electronic tone.
[Shot 2] 00:05-00:10. Clean hard cut to a warm, softened phone-memory flashback. <Subject 2> holds a phone with its screen turned away from camera or fully defocused so no UI can be read. The child looks upset and calls for her mother. No captions or subtitles. <Subject 2> says in an emotional natural child voice, <d>[Chinese] {DIALOGUE_1}</d>. Slight 50mm push-in, shallow depth of field, subtle telephone-room tone. The spoken words must remain audio-only.
[Shot 3] 00:10-00:15. Clean hard cut to a later memory. <Subject 3> glances away with mild impatience while holding the phone low; any screen surface is turned away, dark, or heavily defocused. No readable text anywhere in frame. <Subject 3> says in a casual distracted child voice, <d>[Chinese] {DIALOGUE_2}</d>. Static 50mm medium close-up. End on the child's averted gaze. The spoken words must remain audio-only.

overall_soundscape:
Shot 1: restrained alarm vibration/electronic tone and quiet night ambience. Shot 2: natural child speech from <d> plus faint phone-room tone. Shot 3: natural child speech from <d> plus faint phone-room tone. The <d> strings are audio-only and must never be visualized.

non_diegetic_music:
N/A"""


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
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError("No CJK font found; install fonts-noto-cjk before running E4U02 live test")


def _make_phone_reference(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (9, 14, 24))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((410, 55, 870, 665), radius=46, fill=(18, 21, 28), outline=(76, 84, 102), width=5)
    draw.rounded_rectangle((442, 100, 838, 620), radius=30, fill=(235, 240, 246))
    draw.rounded_rectangle((495, 210, 785, 430), radius=24, fill=(251, 252, 253), outline=(194, 202, 213), width=3)
    # Non-linguistic icon-only decoration.
    draw.ellipse((610, 155, 670, 215), outline=(96, 105, 120), width=5)
    draw.line((640, 165, 640, 185), fill=(96, 105, 120), width=4)
    draw.line((640, 185, 655, 195), fill=(96, 105, 120), width=4)
    font = _font(44)
    bbox = draw.textbbox((0, 0), ONLY_VISIBLE_TEXT, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((1280 - w) / 2, 285), ONLY_VISIBLE_TEXT, font=font, fill=(20, 24, 31))
    # Abstract controls without text/numbers.
    draw.rounded_rectangle((530, 485, 750, 525), radius=20, fill=(205, 212, 221))
    image.save(path, format="PNG", optimize=True)


def _make_child_reference(path: Path, *, older: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (213, 196, 175) if not older else (191, 184, 176))
    draw = ImageDraw.Draw(image)
    cx = 640
    # Deliberately text-free identity surrogate: face, hair, clothing, phone.
    draw.ellipse((cx - 120, 150, cx + 120, 390), fill=(224, 186, 156), outline=(94, 73, 62), width=4)
    draw.pieslice((cx - 135, 120, cx + 135, 365), 180, 360, fill=(50, 37, 33))
    draw.ellipse((cx - 55, 245, cx - 35, 263), fill=(45, 38, 35))
    draw.ellipse((cx + 35, 245, cx + 55, 263), fill=(45, 38, 35))
    draw.arc((cx - 45, 275, cx + 45, 330), 20 if older else 200, 160 if older else 340, fill=(110, 67, 62), width=4)
    draw.rounded_rectangle((cx - 180, 390, cx + 180, 700), radius=50, fill=(112, 134, 158) if not older else (153, 122, 114))
    draw.rounded_rectangle((cx + 150, 320, cx + 230, 500), radius=16, fill=(28, 32, 39), outline=(75, 80, 90), width=3)
    image.save(path, format="PNG", optimize=True)


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://api.minimaxi.com/v1"

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    refs_dir = project / "fixtures"
    phone = refs_dir / "phone_alarm_exact_text.png"
    young = refs_dir / "young_child_text_free.png"
    older = refs_dir / "older_child_text_free.png"
    _make_phone_reference(phone)
    _make_child_reference(young, older=False)
    _make_child_reference(older, older=True)

    request_assets = [
        Entry(Ref("object", "E4U02手机闹钟")),
        Entry(Ref("character", "幼年陆念")),
        Entry(Ref("character", "陆念")),
    ]
    payload = {
        "prompt_compiler": "h3_ref2va",
        "reference_image_labels": ["E4U02手机闹钟", "幼年陆念", "陆念"],
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
    # Six-section prompt is intentionally pre-authored; compilation must be idempotent.
    if preview.provider_prompt != PROMPT.strip():
        raise RuntimeError("E4U02 v2 prompt changed during compilation")

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

    # Static acceptance guards before a paid provider call.
    if runtime.provider_prompt.count(ONLY_VISIBLE_TEXT) < 4:
        raise RuntimeError("visible-text whitelist is not reinforced strongly enough")
    for spoken in (DIALOGUE_1, DIALOGUE_2):
        if f"<d>[Chinese] {spoken}</d>" not in runtime.provider_prompt:
            raise RuntimeError(f"missing audio dialogue tag: {spoken}")
    for required_rule in (
        "AUDIO-ONLY",
        "Never render any <d> content as on-screen text",
        "sole readable text allowed",
        "forbidden from appearing visually",
    ):
        if required_rule not in runtime.provider_prompt:
            raise RuntimeError(f"missing E4U02 v2 guard: {required_rule}")

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
        reference_images=[phone, young, older],
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
        "repair_version": "v2",
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "model": MODEL,
        "generation_mode": runtime.generation_mode,
        "duration_requested_seconds": DURATION_SECONDS,
        "provider_duration_seconds": provider_duration,
        "ffprobe_video_duration_seconds": probed_duration,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "reference_count": 3,
        "only_legal_visible_text": ONLY_VISIBLE_TEXT,
        "dialogue_visualization_forbidden": [DIALOGUE_1, DIALOGUE_2],
        "provider_prompt_chars": len(runtime.provider_prompt),
        "provider_prompt_sha256": preview_sha,
        "preview_runtime_prompt_equal": True,
        "reference_sha256": {
            "phone": _sha256(phone),
            "young_child": _sha256(young),
            "older_child": _sha256(older),
        },
        "version": version,
        "version_duration_seconds": record.get("duration_seconds"),
        "video_size_bytes": output_path.stat().st_size,
        "video_sha256": _sha256(output_path),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "E4U02_v2_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E4U02_v2_final_provider_prompt.txt").write_text(
        runtime.provider_prompt,
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
