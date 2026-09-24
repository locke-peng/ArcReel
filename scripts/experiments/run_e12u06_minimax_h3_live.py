"""One-shot paid supplier smoke test for E12U06 on the H3 doc-pack experiment branch."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import (
    assert_provider_prompt_matches_preview,
    compile_reference_video_provider_prompt,
    provider_prompt_sha256,
)

UNIT_ID = "E12U06"
MODEL = "minimax_h3_zm_u24"
DURATION_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p"
CANONICAL_REFERENCE_SHA256 = "7b296bcbd21fdc1ef4792649c6062355c568bf64c2756a9319d86048d38a3762"
PROMPT = "subject_definitions:\n<Subject 1> is the summit stage environment defined by <Picture 1>; preserve its spatial layout, architecture, main screen, side-stage entrance, lighting identity, and stable event visual anchors.\n\nsummary:\n[reference generation] Create one continuous 10-second target video using <Subject 1>. Preserve the referenced summit stage while moving from a failed main-screen state to a non-readable identity-loading state, then to the opening stage-wing side door positioned directly at the edge of the stage and the rising spotlight in the authored two-shot progression.\n\nretention_analysis:\n<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - the referenced environment, layout, architecture, main screen, and the stage-wing side door physically attached to the stage edge are retained as stable spatial anchors.\n\ndetailed_description:\nThe target video uses live-action conference drama with controlled lighting changes and restrained camera movement. The environment remains spatially consistent across the two shots. The identity-loading state is represented only by blank geometric placeholders and neutral progress shapes, never by readable language, names, titles, portraits, headshots, logos, letters, numbers, or glyph-like marks.\n[Shot 1] A tight centered 50mm view in <Subject 1> holds on the main screen with a static camera. The error display cuts to a completely black screen, then a minimalist identity-title loading skeleton begins to appear using only empty horizontal bars and abstract rectangular placeholders. These placeholders remain plainly non-linguistic and contain no readable characters or portrait imagery throughout the shot.\n[Shot 2] At 00:05.000, the shot cuts to a centered medium 35mm view in <Subject 1>. The stage-wing side door is built directly into the wing immediately beside the performance area, physically touching the stage edge rather than sitting down a backstage corridor or in a separate hallway. The doorway must read as part of the stage architecture, with only a very short threshold between the door and the stage floor. The camera slowly pushes forward by about 0.4 meters as this door opens gradually and a focused stage light rises at the stage edge, so anyone emerging from the doorway would step almost immediately onto the side of the stage. Do not depict a remote backstage corridor, detached doorway, long passage, lobby, or separate entrance zone. Any portion of the main screen still visible in the background remains black or shows only the same blank non-text loading placeholders, with no readable characters or portrait imagery.\n\noverall_soundscape:\nA low electronic tone accompanies the screen transition. The second shot holds near-silence before applause, preserving the tense pause immediately before the entrance.\n\nnon_diegetic_music:\nN/A"


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


def _make_runtime_reference(path: Path) -> None:
    """Build a text-free summit-stage reference with the E12U06 spatial anchors."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (10, 14, 25))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 520, 1280, 719), fill=(31, 34, 43))
    draw.polygon([(80, 520), (1200, 520), (1120, 675), (160, 675)], fill=(45, 48, 58))
    draw.rectangle((210, 95, 1010, 455), fill=(2, 3, 5), outline=(85, 92, 110), width=8)
    draw.rectangle((1050, 255, 1210, 520), fill=(18, 20, 28), outline=(105, 112, 132), width=6)
    draw.rectangle((1070, 285, 1188, 518), fill=(5, 6, 9))
    draw.polygon([(1128, 265), (1005, 520), (1250, 520)], fill=(64, 66, 72))
    for x in (325, 470, 615, 760):
        draw.rectangle((x, 230, x + 85, 246), fill=(62, 67, 77))
    image.save(path, format="PNG", optimize=True)


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://api.minimaxi.com/v1"

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    reference = project / "fixtures" / "AI峰会.png"
    _make_runtime_reference(reference)

    request_assets = [Entry(Ref("scene", "AI峰会"))]
    payload = {"prompt_compiler": "h3_ref2va", "reference_image_labels": ["AI峰会"]}
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
        provider_prompt=runtime.provider_prompt, expected_sha256=preview_sha
    )
    if preview.provider_prompt != runtime.provider_prompt:
        raise RuntimeError("preview/runtime prompt text mismatch")

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
    generator = MediaGenerator(
        project,
        video_backend=backend,
        video_provider_id="autodl",
    )
    generator.ledger = _NullLedger()

    output_path, version, _video_ref, _video_uri = await generator.generate_video_async(
        prompt=runtime.provider_prompt,
        resource_type="reference_videos",
        resource_id=UNIT_ID,
        reference_images=[reference],
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
        "status": "PASS",
        "unit_id": UNIT_ID,
        "branch_head": os.environ.get("GITHUB_SHA"),
        "provider": "autodl",
        "model": MODEL,
        "generation_mode": runtime.generation_mode,
        "duration_requested_seconds": DURATION_SECONDS,
        "provider_duration_seconds": provider_duration,
        "ffprobe_video_duration_seconds": probed_duration,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "reference_count": 1,
        "canonical_reference_sha256": CANONICAL_REFERENCE_SHA256,
        "runtime_reference_kind": "text-free summit-stage surrogate generated inside GitHub Actions",
        "runtime_reference_sha256": _sha256(reference),
        "source_prompt_chars": len(PROMPT),
        "provider_prompt_chars": len(runtime.provider_prompt),
        "provider_prompt_sha256": preview_sha,
        "preview_runtime_prompt_equal": True,
        "version": version,
        "version_duration_seconds": record.get("duration_seconds"),
        "video_size_bytes": output_path.stat().st_size,
        "video_sha256": _sha256(output_path),
    }
    root.mkdir(parents=True, exist_ok=True)
    report_path = root / "E12U06_live_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "E12U06_final_provider_prompt.txt").write_text(runtime.provider_prompt, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
