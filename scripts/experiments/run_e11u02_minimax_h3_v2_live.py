"""Paid E11U02 acceptance: identity-safe framing, dialogue-detached audio, three deterministic 5s plates."""

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

from lib.audio_utils import probe_existing_video_duration_seconds
from lib.custom_provider.declarative_backend import DeclarativeVideoBackend
from lib.media_generator import MediaGenerator
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256

UNIT_ID = "E11U02"
DURATION_SECONDS = 15
SHOT_SECONDS = 5
PLATE_PROVIDER_SECONDS = 10
ASPECT_RATIO = "16:9"
RESOLUTION = "480p横"
FINAL_WIDTH = 864
FINAL_HEIGHT = 480
MODEL = "minimax_h3_zm_u24"

DIALOGUE_1 = "通过了"
DIALOGUE_2 = "明天见真章"
DIALOGUE_3 = "陆氏会合作吗"

SCENE_BRIDGE_B64 = Path("scripts/experiments/fixtures/e11u02/E11U02_scene_bridge.jpg.b64")
SCENE_BRIDGE_SHA256 = "90ad97c07213d6d9fe1dee15a676b560055ec30fdcd8f041c42f23a643ac201b"

ZERO_TEXT_AVOID = (
    "Avoid: readable text, letters, digits, subtitles, captions, dialogue transcription, "
    "watermarks, logos, UI labels, pseudo-text, code glyphs, BGM."
)

AUDIO_SEED_PROMPT = f"""subject_definitions:
<Subject 1> is a neutral indoor production reference used only to anchor room acoustics for a three-part 15-second soundtrack.

summary:
Create one continuous 15-second soundtrack matching three exact five-second story beats. 00:00-00:05 is a modern AI laboratory after a successful test: one researcher speaks one short Mandarin confirmation and the team gives a brief restrained cheer. 00:05-00:10 is the same laboratory: one adult man speaks one Mandarin line while placing an event badge on a table; quiet room tone only. 00:10-00:15 is a busy AI summit media entrance: one off-camera reporter asks one Mandarin question while camera shutters fire. No non-diegetic music.

retention_analysis:
<Subject 1>: partially_preserved - use only plausible professional indoor acoustics; visual content does not matter.

detailed_description:
[Audio Shot 1] 00:00-00:05. Laboratory keyboard and equipment hum. At about 00:01.2, one young researcher says exactly: <d>[Chinese] {DIALOGUE_1}</d>. Immediately after, a short group cheer and relieved exhale. No other intelligible words.
[Audio Shot 2] 00:05-00:10. Hard acoustic cut to a quieter laboratory tabletop moment. At about 00:06.0, one adult man says exactly: <d>[Chinese] {DIALOGUE_2}</d>. Subtle badge/lanyard contact with the tabletop. No other speech.
[Audio Shot 3] 00:10-00:15. Hard acoustic cut to a summit media zone. At about 00:10.8, one off-camera reporter asks exactly: <d>[Chinese] {DIALOGUE_3}</d>. Several camera shutter bursts and restrained crowd murmur follow. No answer is spoken.

overall_soundscape:
Professional laboratory ambience followed by a media-entry ambience. Exactly three authored Mandarin utterances, one per shot, with no extra intelligible speech.

non_diegetic_music:
N/A"""

SHOT1_PROMPT = f"""subject_definitions:
<Subject 1> is the LEFT scene panel from <Picture 1>: a contemporary high-end AI laboratory with cool blue-white lighting, workstations, glass/metal material language, and stable architecture.

summary:
[reference generation; visual-only plate] Create a 10-second laboratory success plate. The FIRST five seconds are the canonical target: a small research team completes the reviewed build and a PHYSICAL non-linguistic hardware status indicator changes from unstable amber pulses to one steady green light state. The target camera angle deliberately excludes all monitor faces, display walls, signage, posters, badges, labels, and printed surfaces. No named principal face is shown close enough to establish a new facial identity. No dialogue transcript exists in this visual prompt. ZERO readable text.

retention_analysis:
<Subject 1>: partially_preserved environment - retain the laboratory's cool lighting, workstation topology, glass/metal material language, and professional AI-lab atmosphere, but rotate the camera toward a clean equipment test bay so all screens and printed material are outside the target framing.

detailed_description:
SCENE CONTRACT — HIGHEST PRIORITY: this is the same Tianshu-style AI laboratory established by <Picture 1>, not a classroom, home office, or generic server room.
IDENTITY-SAFE FRAMING — HIGHEST PRIORITY: two or three supporting researchers are seen from medium distance, rear angle, or three-quarter rear. No face close-up and no attempt to establish a new canonical identity.
NO-SCREEN FRAMING — HIGHEST PRIORITY: target composition contains no visible monitor face, display wall, television, laptop screen, poster, wall graphic, sign, badge, paper label, printed document, or readable surface.
STATE CONTRACT — HIGHEST PRIORITY: communicate "model stable" only through a physical equipment indicator module: several small amber light pulses are irregular at first, then resolve into one continuous steady green luminous ring or bar. No characters, numbers, glyphs, waveform labels, or UI are used.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text and ZERO glyph-like pseudo-text anywhere in frame.
[Target Plate] 00:00-00:05. Medium-wide 35mm static shot with a subtle 0.2-meter push. Researchers complete one final keyboard or hardware-switch action on a control surface whose display face is not visible to camera. By about 00:01.5, the physical indicator module changes from irregular amber pulses to one steady green light. One researcher gives a small relieved hand gesture while the others visibly relax. Hold the stable green hardware state through 00:05.
[Extension] 00:05-00:10. Maintain the same screen-free framing, steady green hardware indicator, and restrained team relief with no new action.

overall_soundscape:
N/A for this visual plate; canonical audio is muxed later.

non_diegetic_music:
N/A
{ZERO_TEXT_AVOID}"""

SHOT2_PROMPT = f"""subject_definitions:
<Subject 1> is the LEFT scene panel from <Picture 1>: the same contemporary AI laboratory, used only for material and lighting reference.

summary:
[reference generation; visual-only plate] Create a 10-second close tabletop plate. The FIRST five seconds are the canonical target: a man's hand and forearm enter from frame edge and place a formal summit guest badge with a plain lanyard beside a woman's resting hand. Faces remain completely outside frame. The BADGE BACKSIDE faces camera for the entire target shot and is a single unprinted matte surface. The printed front side always faces the table and is never visible. The lanyard is a plain solid cord with no writing, logos, or pattern. The framing contains no monitor, screen, paper, keyboard labels, signage, or other text-bearing object. ZERO readable text.

retention_analysis:
<Subject 1>: partially_preserved environment - retain only the laboratory's cool professional lighting and clean materials; use a simplified clean tabletop background with all screens and printed surfaces excluded.

detailed_description:
IDENTITY-SAFE FRAMING — HIGHEST PRIORITY: show hands and forearms only. No faces, no heads, no facial reflections, no portrait photographs, and no generated portrait identities. The receiving woman's sleeve is clean cool-white professional tailoring. The placing man's sleeve is dark tech-navy tailoring with a minimal modern watch.
PROP CONTRACT — HIGHEST PRIORITY: one formal summit guest badge and plain lanyard are placed beside the woman's hand. The badge's unprinted BACKSIDE faces camera at all times; the printed front remains face-down against the table. The visible badge surface is one blank matte rectangle with no color blocks, no emblem, no border text, no icon, and no decoration.
LANYARD CONTRACT — HIGHEST PRIORITY: plain dark solid cord only, completely unprinted and unpatterned.
NO-SCREEN FRAMING — HIGHEST PRIORITY: no monitors, laptops, tablets, displays, papers, documents, signs, or other text-bearing objects are visible.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text and ZERO glyph-like pseudo-text.
[Target Plate] 00:00-00:05. Close 70mm tabletop shot, static. At 00:00 the woman's hand rests on a clean matte table. At about 00:01, the man's hand enters from upper right holding the badge by the plain cord, rotates the badge so the blank backside faces camera and the printed front faces downward, sets it gently beside her hand, then withdraws. The woman's fingers pause, acknowledging the gesture without picking it up. Hold through 00:05.
[Extension] 00:05-00:10. Maintain the badge face-down position and hands with only subtle breathing-level movement; no faces, screens, paper, or text.

overall_soundscape:
N/A for this visual plate; canonical dialogue is muxed later.

non_diegetic_music:
N/A
{ZERO_TEXT_AVOID}"""

SHOT3_PROMPT = f"""subject_definitions:
<Subject 1> is the RIGHT scene panel from <Picture 1>: a premium AI summit venue used only for lighting, scale, and event atmosphere.
<Subject 2> is an adult man represented only by canonical wardrobe/profile cues: tall controlled posture, graphite-to-deep-navy business suit, cold-white shirt, understated watch. His face must not be established.
<Subject 3> is an adult woman represented only by canonical wardrobe/profile cues: warm ivory/champagne tailored outfit, soft camel or dusty-rose accent, elegant small business handbag, minimal metal jewelry. Her face must not be established.

summary:
[reference generation; visual-only plate] Create a 10-second summit media-entry plate. The FIRST five seconds are the canonical target: <Subject 2> and <Subject 3> enter a narrow media arrival corridor together while reporters and cameras react. The target corridor is intentionally built from PLAIN BLACK ACOUSTIC DRAPES and neutral floor lighting only. No branded wall, no sponsor backdrop, no LED screen, no event banner, no signs, no visible event badges, and no wall graphics exist in target framing. Camera performs a restrained lateral follow. Preserve the pair as identity-safe rear or three-quarter-rear figures; do not invent new canonical faces. ZERO readable text.

retention_analysis:
<Subject 1>: partially_preserved environment - preserve only premium summit scale, cool event lighting, media density, and camera-flash atmosphere; replace all branded or graphic surfaces with plain black acoustic drapes and neutral architectural panels.
<Subject 2>: profile-cue-preserved - preserve dark business wardrobe, tall controlled posture, and male silhouette; face remains hidden.
<Subject 3>: profile-cue-preserved - preserve warm light-luxury palette, tailored silhouette, handbag/jewelry cues; face remains hidden.

detailed_description:
SCENE CONTRACT — HIGHEST PRIORITY: premium AI summit MEDIA ARRIVAL CORRIDOR, not the laboratory and not the main-stage performance shot.
BLACK-DRAPE CONTRACT — HIGHEST PRIORITY: both sides and rear background use plain black acoustic curtains or blank neutral architectural panels only. No sponsor wall, no event title, no logo wall, no projection, no LED screen, no poster, no banner, no directional sign, no booth graphic.
IDENTITY-SAFE FRAMING — HIGHEST PRIORITY: <Subject 2> and <Subject 3> remain rear or three-quarter rear throughout. Their faces are fully occluded by angle. Do not create front-facing portrait identities.
BADGE/DEVICE CONTRACT — HIGHEST PRIORITY: no visible event badges or printed credentials on any principal. Reporters' camera rear displays are turned away from camera or black/off. Microphones have plain black windscreens with no labels.
TEXT CONTRACT — HIGHEST PRIORITY: ZERO readable text and ZERO glyph-like pseudo-text anywhere in frame.
[Target Plate] 00:00-00:05. Medium 35mm rear entrance shot. The pair enter the black-drape media corridor from frame left and move toward the interior. A restrained lateral camera move follows them by about one meter. Reporters on both sides raise cameras; two or three flash bursts fire. The pair do not stop and do not answer. Hold movement through 00:05.
[Extension] 00:05-00:10. Maintain the same rear-angle movement, black-drape corridor, blank surfaces, and media density with no new action.

overall_soundscape:
N/A for this visual plate; canonical reporter audio is muxed later.

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


def _decode_scene_bridge(output: Path) -> None:
    raw = "".join(SCENE_BRIDGE_B64.read_text(encoding="utf-8").split())
    data = base64.b64decode(raw, validate=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    actual = _sha256(output)
    if actual != SCENE_BRIDGE_SHA256:
        raise RuntimeError(f"E11U02 scene bridge SHA mismatch: {actual} != {SCENE_BRIDGE_SHA256}")


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
        raise RuntimeError("failed to extract E11U02 canonical soundtrack")


def _author_final_video(plates: list[Path], audio: Path, output: Path) -> None:
    if len(plates) != 3:
        raise RuntimeError("E11U02 requires exactly three visual plates")
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
        raise RuntimeError("failed to author E11U02 final video")
    os.replace(temp, output)


def _has_cjk(value: str) -> bool:
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in value
    )


def _assert_visual_prompt_contract(prompt: str, label: str) -> None:
    if "<d>" in prompt or "</d>" in prompt:
        raise RuntimeError(f"dialogue tag leaked into {label}")
    if any(dialogue in prompt for dialogue in (DIALOGUE_1, DIALOGUE_2, DIALOGUE_3)):
        raise RuntimeError(f"dialogue transcript leaked into {label}")
    if _has_cjk(prompt):
        raise RuntimeError(f"CJK leaked into {label}")
    if "ZERO readable text" not in prompt:
        raise RuntimeError(f"zero-text contract missing from {label}")
    if prompt.rstrip().splitlines()[-1] != ZERO_TEXT_AVOID:
        raise RuntimeError(f"final avoid line is not last in {label}")


def _assert_contracts() -> None:
    if not SCENE_BRIDGE_B64.is_file():
        raise RuntimeError("missing E11U02 scene bridge fixture")
    for dialogue in (DIALOGUE_1, DIALOGUE_2, DIALOGUE_3):
        if f"<d>[Chinese] {dialogue}</d>" not in AUDIO_SEED_PROMPT:
            raise RuntimeError(f"audio seed missing canonical dialogue: {dialogue}")
    for label, prompt in (
        ("shot1", SHOT1_PROMPT),
        ("shot2", SHOT2_PROMPT),
        ("shot3", SHOT3_PROMPT),
    ):
        _assert_visual_prompt_contract(prompt, label)
    if "IDENTITY-SAFE FRAMING" not in SHOT2_PROMPT or "show hands and forearms only" not in SHOT2_PROMPT:
        raise RuntimeError("shot2 must avoid inventing C01/C06 faces")
    if "remain rear or three-quarter rear throughout" not in SHOT3_PROMPT:
        raise RuntimeError("shot3 must avoid inventing C02/C04 faces")


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
    versions_text = await asyncio.to_thread(versions_path.read_text, encoding="utf-8")
    versions = json.loads(versions_text)
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
    scene_bridge = refs / "E11U02_scene_bridge.jpg"
    soundtrack = refs / "E11U02_canonical_soundtrack.wav"
    _decode_scene_bridge(scene_bridge)

    audio_seed_video, audio_seed_version, audio_seed_record = await _generate(
        project=project,
        prompt=AUDIO_SEED_PROMPT,
        resource_id=f"{UNIT_ID}_AUDIO_SEED",
        duration_seconds=DURATION_SECONDS,
        api_key=api_key,
        base_url=base_url,
        reference_images=[scene_bridge],
    )
    _extract_audio(audio_seed_video, soundtrack)

    plate_specs = [
        ("SHOT1", SHOT1_PROMPT),
        ("SHOT2", SHOT2_PROMPT),
        ("SHOT3", SHOT3_PROMPT),
    ]
    raw_plates: list[Path] = []
    plate_reports: list[dict[str, Any]] = []
    for suffix, prompt in plate_specs:
        output, version, record = await _generate(
            project=project,
            prompt=prompt,
            resource_id=f"{UNIT_ID}_{suffix}",
            duration_seconds=PLATE_PROVIDER_SECONDS,
            api_key=api_key,
            base_url=base_url,
            reference_images=[scene_bridge],
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
        "repair_version": "v2_zero_text_physical_state_face_down_badge_black_drape",
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
            "shot1": "research team executes; model becomes stable",
            "shot2": "formal guest badge is placed beside her hand",
            "shot3": "C02/C04 enter summit media zone together",
        },
        "canonical_dialogue": [DIALOGUE_1, DIALOGUE_2, DIALOGUE_3],
        "canonical_visible_text": [],
        "visual_prompts_contain_cjk": [_has_cjk(p) for p in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT)],
        "dialogue_detached_from_visual_prompts": all(
            all(d not in prompt for d in (DIALOGUE_1, DIALOGUE_2, DIALOGUE_3)) and "<d>" not in prompt
            for prompt in (SHOT1_PROMPT, SHOT2_PROMPT, SHOT3_PROMPT)
        ),
        "identity_safe_framing": {
            "shot1": "supporting staff at medium distance; no named face close-up",
            "shot2": "hands/forearms only; C01/C06 faces intentionally absent",
            "shot3": "C02/C04 rear or three-quarter rear; faces intentionally not established",
        },
        "scene_bridge_sha256": _sha256(scene_bridge),
        "audio_seed_prompt_sha256": provider_prompt_sha256(AUDIO_SEED_PROMPT.strip()),
        "soundtrack_sha256": _sha256(soundtrack),
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
    (root / "E11U02_v2_live_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "E11U02_audio_seed_provider_prompt.txt").write_text(
        AUDIO_SEED_PROMPT.strip(), encoding="utf-8"
    )
    for suffix, prompt in plate_specs:
        (root / f"E11U02_{suffix.lower()}_provider_prompt.txt").write_text(
            prompt.strip(), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
