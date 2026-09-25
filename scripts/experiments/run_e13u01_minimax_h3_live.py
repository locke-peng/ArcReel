"""Paid supplier acceptance for E13U01: exact identity screen + C01 + E12 continuity."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256

UNIT_ID = "E13U01"
MODEL = "minimax_h3_image_audio_to_video_v2_15s"
DURATION_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"

CHARACTER_ID = "C01"
VISIBLE_NAME = "沈知意"
VISIBLE_TITLE = "天枢联合创始人"
FORBIDDEN_HOST_TRANSCRIPT = "欢迎沈知意"

STAGE_SHA256 = "250960b55d6f417d6ca8f55c66cd0a6d46771253aa3165f978244681156d1023"
BRIDGE_SHA256 = "e52d13f2c438382bf8de219af911ca28ab9ec172f15447f7846a1cc261f4a613"
AUDIO_SHA256 = "c2feb633f8621160340ff5acda6c2de0e305e1aa2839adf90e3afef4d8d830d6"

FINAL_AVOID_LINE = (
    'Avoid: subtitles, captions, dialogue transcription, speech bubbles, lower-thirds, '
    'watermarks, logos, timestamps, pseudo-text, and any readable text except "'
    + VISIBLE_NAME
    + '" and "'
    + VISIBLE_TITLE
    + '".'
)

PROMPT = f"""subject_definitions:
<Subject 1> is the accepted summit stage continuity derived from <Picture 1>. Preserve the dark stage, main LED screen position, the side-stage door physically attached to the immediate stage edge, the very short threshold, the direct connection from the doorway to the stage floor, and the established white spotlight geometry.
<Subject 2> is canonical character C01, derived from the LEFT side of <Picture 2>. Preserve this exact woman: facial identity, dark hair, center-parted loose updo, eye geometry, brows, nose, mouth, cheek and jaw structure, skin tone, slim adult proportions, and the same white tailored pantsuit.
<Subject 3> is the exact identity-title screen design derived from the RIGHT side of <Picture 2>. It is a clean black title card with exactly two readable Chinese strings: "{VISIBLE_NAME}" as the large primary line and "{VISIBLE_TITLE}" as the smaller secondary line. Preserve the text exactly, preserve the two-line hierarchy, and keep the card free of portraits, avatars, photos, extra labels, logos, numbers, and pseudo-text.
<Picture 1> is the spatial continuity anchor inherited from the accepted E12U06 final stage state. It determines where the side-stage door, stage edge, main screen, and spotlight physically belong.
<Picture 2> is a split reference with two distinct roles: LEFT supplies C01 identity and white summit costume; RIGHT supplies the exact giant-screen title layout. Do not merge the woman's portrait into the title card.
<Audio 1> is the synchronized source soundtrack containing the off-screen host introduction followed by audience applause. Reuse it as audible sound only. Never transcribe, quote, caption, subtitle, or otherwise visualize any spoken content from the audio.

summary:
[reference generation + audio reuse] Create one continuous 10-second horizontal summit reveal in two authored 5-second shots. CONTINUITY LOCK — HIGHEST PRIORITY: this is the immediate continuation of the accepted E12U06 stage state from <Picture 1>; retain the same side-stage door at the immediate stage edge, short threshold, stage-floor connection, main-screen placement, and spotlight direction. TITLE LOCK — HIGHEST PRIORITY: [Shot 1] shows <Subject 3> with exactly "{VISIBLE_NAME}" and "{VISIBLE_TITLE}" and no other readable text. CHARACTER LOCK — HIGHEST PRIORITY: [Shot 2] shows only canonical C01 <Subject 2> entering through that same side-stage door into the established spotlight. AUDIO/TEXT SEPARATION — HIGHEST PRIORITY: <Audio 1> supplies the host and applause; no spoken content may become visible text.

retention_analysis:
<Subject 1> (appears in both shots): fully_preserved spatial continuity - preserve stage geometry, screen location, side-stage door location, immediate stage-edge relationship, short threshold, direct stage-floor connection, and spotlight direction from <Picture 1>.
<Subject 2> (appears in [Shot 2]): fully_preserved identity - preserve the C01 face, hair, white tailored pantsuit, body proportions, and recognizable likeness from the LEFT side of <Picture 2>. No substitute woman and no identity drift.
<Subject 3> (appears in [Shot 1], may remain softly visible in [Shot 2] background): fully_preserved exact visible text - reproduce exactly "{VISIBLE_NAME}" and "{VISIBLE_TITLE}" from the RIGHT side of <Picture 2>. The giant screen contains text only, not a portrait or identity card.
<Audio 1>: fully_copy - reuse the synchronized off-screen host introduction and applause as sound. Its speech is never converted into visible text.

detailed_description:
GLOBAL VISIBLE-TEXT CONTRACT — HIGHEST PRIORITY: the complete 10-second output has exactly two permitted readable strings, "{VISIBLE_NAME}" and "{VISIBLE_TITLE}", both belonging only to the giant summit screen. No other letters, Chinese characters, words, numbers, clock digits, status text, exit signs, labels, logos, watermarks, captions, subtitles, invented glyphs, or pseudo-readable marks may appear.
CHARACTER IDENTITY CONTRACT — HIGHEST PRIORITY: C01 <Subject 2> must match the LEFT reference in <Picture 2>, including face topology, eyes, brows, nose, mouth, cheek/jaw relationship, dark updo, skin tone, and white summit pantsuit. Do not cast a similar woman or invent a new face.
STAGE CONTINUITY CONTRACT — HIGHEST PRIORITY: the doorway used in [Shot 2] is the same physical side-stage door seen at the end of E12U06 and in <Picture 1>. It is attached directly to the immediate stage edge with a very short threshold and direct stage-floor access. There is no backstage corridor, lobby, long hallway, independent foyer, or detached doorway.
AUDIO/TEXT SEPARATION CONTRACT — HIGHEST PRIORITY: <Audio 1> is heard but never transcribed. No subtitle track, burned-in subtitle, caption strip, dialogue card, speech bubble, lower-third, karaoke line, or transcript is visible at any time.

[Shot 1] 00:00-00:05. Tight frontal 50mm close shot of the summit's main LED screen in the same stage environment from <Picture 1>. The screen transitions from the prior minimal geometric state to the exact clean black identity-title design <Subject 3> from the RIGHT side of <Picture 2>. It displays only two centered readable lines: large "{VISIBLE_NAME}" above smaller "{VISIBLE_TITLE}". The typography is stable and fully legible for the shot. No portrait, face, avatar, headshot, profile photo, icon, badge, company logo, extra line, number, or pseudo-text appears on the screen. The off-screen host introduction and then applause are taken only from <Audio 1>. Static composition with a subtle light rise; no on-screen speaker.

[Shot 2] At 00:05.000, clean hard cut to the same stage-wing edge and side-stage door from <Picture 1>. <Subject 2> steps through the open doorway across the very short threshold directly onto the stage floor and into the already-rising white spotlight. Preserve the exact C01 face and white tailored pantsuit from the LEFT side of <Picture 2>. She is calm, composed, and focused, walking one or two measured steps into the light while the camera makes a slow small-amplitude 50mm push-in. The doorway remains visibly attached to the stage edge; do not transform it into a corridor or lobby. No unrelated person enters. If the giant screen is visible in the background, it contains only the same exact two permitted strings and remains secondary and softly out of focus. Audience applause continues from <Audio 1>. No visible text outside the giant screen.

overall_soundscape:
Reuse <Audio 1> as the synchronized soundtrack: off-screen host introduction at the reveal, followed by audience applause that carries across the cut into [Shot 2]. No spoken content from the audio is converted into visible text.

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


def _required_path(env_name: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        raise RuntimeError(f"{env_name} is required")
    path = Path(raw)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{env_name} is missing or empty: {path}")
    return path


def _assert_provider_prompt_contract() -> None:
    if "<d>" in PROMPT or "</d>" in PROMPT:
        raise RuntimeError("dialogue tags leaked into E13U01 visual provider prompt")
    if FORBIDDEN_HOST_TRANSCRIPT in PROMPT:
        raise RuntimeError("host transcript leaked into E13U01 visual provider prompt")
    if "<Audio 1>" not in PROMPT:
        raise RuntimeError("E13U01 prompt is missing <Audio 1>")
    if PROMPT.rstrip().splitlines()[-1] != FINAL_AVOID_LINE:
        raise RuntimeError("final avoid line is not the last provider-prompt line")


async def main() -> None:
    api_key = os.environ.get("MINIMAX_LIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_H3_API_KEY/MINIMAX_API_KEY secret is not configured")
    base_url = os.environ.get("MINIMAX_LIVE_BASE_URL", "").strip() or "https://autodl.art"

    stage_ref = _required_path("E13U01_STAGE_REF")
    bridge_ref = _required_path("E13U01_BRIDGE_REF")
    audio_ref = _required_path("E13U01_AUDIO_REF")

    expected = {
        stage_ref: STAGE_SHA256,
        bridge_ref: BRIDGE_SHA256,
        audio_ref: AUDIO_SHA256,
    }
    for path, expected_sha in expected.items():
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise RuntimeError(f"reference SHA mismatch for {path}: {actual_sha} != {expected_sha}")

    _assert_provider_prompt_contract()

    root = Path("live_artifacts") / UNIT_ID
    project = root / "project"
    provider_prompt = PROMPT.strip()
    prompt_sha = provider_prompt_sha256(provider_prompt)

    definition = json.loads(
        Path("scripts/experiments/autodl_minimax_h3_e13u01_endpoint.json").read_text(encoding="utf-8")
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
        start_image=stage_ref,
        end_image=bridge_ref,
        reference_audio_files=[audio_ref],
        aspect_ratio=ASPECT_RATIO,
        duration_seconds=DURATION_SECONDS,
        resolution=RESOLUTION,
        generate_audio=True,
        poll_timeout_seconds=900,
    )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("provider returned no E13U01 video artifact")

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
        "repair_version": "v1_identity_screen_continuity",
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
        "visible_text_allowlist": [VISIBLE_NAME, VISIBLE_TITLE],
        "dialogue_text_detached_from_provider_prompt": True,
        "provider_prompt_contains_d_tag": "<d>" in provider_prompt,
        "provider_prompt_contains_host_transcript": FORBIDDEN_HOST_TRANSCRIPT in provider_prompt,
        "e12u06_continuity_source_run": 35999316411,
        "provider_prompt_chars": len(provider_prompt),
        "provider_prompt_sha256": prompt_sha,
        "reference_sha256": {
            "stage_continuity": _sha256(stage_ref),
            "c01_screen_bridge": _sha256(bridge_ref),
            "audio": _sha256(audio_ref),
        },
        "version": version,
        "version_duration_seconds": record.get("duration_seconds"),
        "video_size_bytes": output_path.stat().st_size,
        "video_sha256": _sha256(output_path),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "E13U01_v1_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E13U01_v1_final_provider_prompt.txt").write_text(
        provider_prompt,
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
