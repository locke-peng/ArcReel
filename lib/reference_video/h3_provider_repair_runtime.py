"""Phase 5 provider-repair source projection and deterministic shot reassembly.

This module owns no repair policy and no provider networking. It resolves the exact
accepted source-version facts bound by a persisted Repair Ticket, derives a shot-only H3
prompt from the previously accepted provider prompt, and deterministically replaces only
that Canonical shot window while preserving the accepted Unit audio track.

Provider submission/poll/resume remains in ArcReel's existing video backend stack.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from lib.path_safety import safe_join
from lib.reference_video.execution_checkpoint import StagedProviderMedia
from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import H3RepairTicket
from lib.reference_video.h3_shot_repair_executor import H3ShotRepairRequest
from lib.resource_paths import resource_relative_path
from lib.version_manager import VersionManager

_SHOT_HEADER_RE = re.compile(r"^\[Shot\s+(\d+)\](?:\s+At\s+(\d{2}:\d{2}\.\d{3}))?\s*$")


@dataclass(frozen=True)
class H3RepairSourceVersion:
    """Current accepted Unit version facts required to execute one approved repair."""

    media_path: Path
    media_sha256: str
    version: int
    provider_prompt: str
    provider_prompt_sha256: str
    provider_id: str
    provider_model: str
    backend_model: str
    endpoint_guard: str | None
    generation_type: str
    aspect_ratio: str
    resolution: str | None
    generate_audio: bool
    service_tier: str
    seed: int | None
    reference_images: tuple[Path, ...]
    reference_audio_files: tuple[Path, ...]
    reference_audio_targets: tuple[int, ...] | None


@dataclass(frozen=True)
class H3VideoStreamFacts:
    duration_seconds: float
    fps: float
    width: int
    height: int
    has_audio: bool


def _required_text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"source H3 version is missing {key}")
    return value.strip()


def _optional_text(record: Mapping[str, object], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"source H3 version has invalid {key}")
    return value.strip()


def _ticket_source_version_record(
    *,
    project_path: Path,
    versions: VersionManager,
    ticket: H3RepairTicket,
) -> tuple[int, dict[str, object], Path]:
    """Resolve current source first, otherwise one uniquely matching history-only version."""

    info = versions.get_versions("reference_videos", ticket.unit_id)
    current = int(info.get("current_version") or 0)
    if current <= 0:
        raise RuntimeError(f"reference video Unit {ticket.unit_id} has no current version")
    records = [
        item
        for item in info.get("versions", [])
        if isinstance(item, dict) and isinstance(item.get("version"), int)
    ]
    current_matches = [
        item for item in records if int(item.get("version") or 0) == current
    ]
    if len(current_matches) != 1:
        raise RuntimeError(f"reference video Unit {ticket.unit_id} current version is ambiguous")

    current_media = safe_join(
        project_path,
        resource_relative_path("reference_videos", ticket.unit_id),
        require_file=True,
    )
    if sha256_file(current_media) == ticket.source_media_sha256:
        return current, current_matches[0], current_media

    history_matches: list[tuple[int, dict[str, object], Path]] = []
    for record in records:
        raw_file = record.get("file")
        if not isinstance(raw_file, str) or not raw_file.strip():
            continue
        try:
            history_media = safe_join(project_path, raw_file, require_file=True)
        except (FileNotFoundError, ValueError):
            continue
        if sha256_file(history_media) == ticket.source_media_sha256:
            history_matches.append((int(record["version"]), record, history_media))

    if len(history_matches) != 1:
        raise RuntimeError(
            f"Repair Ticket source media is not a unique current/history version: {ticket.unit_id}"
        )
    return history_matches[0]


def _resolve_version_provider_media(
    *,
    project_path: Path,
    record: Mapping[str, object],
) -> tuple[tuple[Path, ...], tuple[Path, ...], tuple[int, ...] | None, tuple[str, ...]]:
    raw_media = record.get("execution_provider_media")
    if not isinstance(raw_media, list):
        raise RuntimeError("source H3 version is missing execution_provider_media")

    parsed = tuple(StagedProviderMedia.from_dict(item) for item in raw_media)
    if tuple(item.index for item in parsed) != tuple(range(len(parsed))):
        raise RuntimeError("source H3 provider media indexes are not contiguous")

    image_paths: list[Path] = []
    image_sha: list[str] = []
    audio_paths: list[Path] = []
    audio_targets: list[int | None] = []

    for item in parsed:
        source = safe_join(project_path, item.source_locator, require_file=True)
        if source.stat().st_size != item.size_bytes or sha256_file(source) != item.sha256:
            raise RuntimeError(
                f"source H3 provider media changed after accepted generation: {item.source_locator}"
            )
        if item.role == "reference_image":
            image_paths.append(source)
            image_sha.append(item.sha256)
        elif item.role == "reference_audio":
            audio_paths.append(source)
            audio_targets.append(item.target_index)

    targets: tuple[int, ...] | None = None
    if audio_targets and all(value is not None for value in audio_targets):
        targets = tuple(int(value) for value in audio_targets if value is not None)

    return tuple(image_paths), tuple(audio_paths), targets, tuple(image_sha)


def resolve_h3_repair_source_version(
    *,
    project_path: Path,
    ticket: H3RepairTicket,
) -> H3RepairSourceVersion:
    """Resolve and re-hash the exact current Unit/version facts bound by the ticket."""

    project_path = project_path.resolve()
    versions = VersionManager(project_path)
    version, record, media_path = _ticket_source_version_record(
        project_path=project_path,
        versions=versions,
        ticket=ticket,
    )
    media_sha = sha256_file(media_path)
    if media_sha != ticket.source_media_sha256:
        raise RuntimeError("resolved Unit media SHA no longer matches approved Repair Ticket")
    prompt = record.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise RuntimeError("source H3 version is missing provider prompt")
    prompt_sha = provider_prompt_sha256(prompt)
    if ticket.provider_prompt_sha256 is None or prompt_sha != ticket.provider_prompt_sha256:
        raise RuntimeError("current Unit provider prompt SHA no longer matches approved Repair Ticket")

    reference_images, reference_audio_files, reference_audio_targets, reference_sha = (
        _resolve_version_provider_media(project_path=project_path, record=record)
    )
    if reference_sha != ticket.reference_sha256:
        raise RuntimeError("current Unit reference-image SHA set no longer matches approved Repair Ticket")

    raw_generate_audio = record.get("execution_generate_audio")
    if not isinstance(raw_generate_audio, bool):
        raise RuntimeError("source H3 version is missing execution_generate_audio")
    raw_seed = record.get("execution_seed")
    if raw_seed is not None and (not isinstance(raw_seed, int) or isinstance(raw_seed, bool)):
        raise RuntimeError("source H3 version has invalid execution_seed")

    return H3RepairSourceVersion(
        media_path=media_path,
        media_sha256=media_sha,
        version=version,
        provider_prompt=prompt,
        provider_prompt_sha256=prompt_sha,
        provider_id=_required_text(record, "execution_provider_id"),
        provider_model=_required_text(record, "execution_provider_model_id"),
        backend_model=_required_text(record, "execution_backend_model_id"),
        endpoint_guard=_optional_text(record, "execution_endpoint_guard"),
        generation_type=_required_text(record, "execution_capability"),
        aspect_ratio=_required_text(record, "execution_aspect_ratio"),
        resolution=_optional_text(record, "execution_resolution"),
        generate_audio=raw_generate_audio,
        service_tier=_required_text(record, "execution_service_tier"),
        seed=raw_seed,
        reference_images=reference_images,
        reference_audio_files=reference_audio_files,
        reference_audio_targets=reference_audio_targets,
    )


def _format_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    minutes, rem = divmod(total_ms, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _section(prompt: str, header: str, next_header: str | None) -> list[str]:
    lines = prompt.splitlines()
    try:
        start = lines.index(header) + 1
    except ValueError as exc:
        raise RuntimeError(f"accepted H3 provider prompt is missing section {header}") from exc
    if next_header is None:
        end = len(lines)
    else:
        try:
            end = lines.index(next_header, start)
        except ValueError as exc:
            raise RuntimeError(f"accepted H3 provider prompt is missing section {next_header}") from exc
    return lines[start:end]


def build_h3_shot_repair_prompt(
    *,
    source_provider_prompt: str,
    request: H3ShotRepairRequest,
) -> str:
    """Project one accepted multi-shot H3 prompt into exactly one approved shot request."""

    subject = _section(source_provider_prompt, "subject_definitions:", "summary:")
    summary = _section(source_provider_prompt, "summary:", "retention_analysis:")
    retention = _section(source_provider_prompt, "retention_analysis:", "detailed_description:")
    detailed = _section(source_provider_prompt, "detailed_description:", "overall_soundscape:")

    headers = [(index, match) for index, line in enumerate(detailed) if (match := _SHOT_HEADER_RE.match(line))]
    if not headers:
        raise RuntimeError("accepted H3 provider prompt contains no shot headers")

    target_index: int | None = None
    wanted_ts = _format_timestamp(request.start_seconds)
    for index, match in headers:
        timestamp = match.group(2)
        if request.start_seconds <= 1e-9:
            if match.group(1) == "1" and timestamp is None:
                target_index = index
                break
        elif timestamp == wanted_ts:
            target_index = index
            break
    if target_index is None:
        raise RuntimeError(
            f"accepted H3 provider prompt has no shot starting at {wanted_ts} for {request.shot_id}"
        )

    next_indexes = [index for index, _match in headers if index > target_index]
    target_end = min(next_indexes) if next_indexes else len(detailed)
    first_header = min(index for index, _match in headers)
    prelude = [line for line in detailed[:first_header] if line.strip()]
    body = detailed[target_index + 1 : target_end]
    while body and not body[-1].strip():
        body.pop()

    mode = "REF2VA" if any("[REF2VA]" in line for line in summary) else "T2VA"
    duration = request.duration_seconds
    action_note = {
        H3RepairAction.REGENERATE_SHOT: "Regenerate only the approved shot; do not add extra beats or shots.",
        H3RepairAction.RECOMPILE_DIALOGUE_DETACHED: (
            "Regenerate only the approved shot with dialogue kept as spoken audio; never visualize dialogue as "
            "subtitles, captions, labels, or readable text."
        ),
        H3RepairAction.REGENERATE_WITH_IDENTITY_BRIDGE: (
            "Regenerate only the approved shot and preserve the referenced character identity with maximum "
            "continuity from the accepted source Unit."
        ),
    }.get(request.repair_action, "Regenerate only the approved shot.")

    repair_summary = (
        f"[{mode}] Create exactly one {duration:.3f}-second 16:9 repair shot. "
        f"Approved Canonical shot: {request.shot_id}; source Unit window "
        f"{request.start_seconds:.3f}s-{request.end_seconds:.3f}s. "
        "Do not generate preceding or following shots."
    )
    detailed_lines = [
        *prelude,
        "[Shot 1]",
        *body,
        f"Provider repair constraint: {action_note}",
        (
            "The output duration must match the approved shot window exactly; do not borrow or repay timing "
            "from adjacent shots."
        ),
    ]

    prompt = "\n".join(
        [
            "subject_definitions:",
            *subject,
            "",
            "summary:",
            repair_summary,
            "",
            "retention_analysis:",
            *retention,
            "",
            "detailed_description:",
            *detailed_lines,
            "",
            "overall_soundscape:",
            (
                "Provider audio is non-authoritative for this repair. ArcReel preserves the accepted source "
                "Unit audio during deterministic reassembly."
            ),
            "",
            "non_diegetic_music:",
            "N/A",
        ]
    ).strip()
    if not prompt:
        raise RuntimeError("shot-scoped H3 repair prompt is empty")
    return prompt


def probe_h3_video_stream(path: Path) -> H3VideoStreamFacts:
    """Return stream facts required for deterministic repair reassembly."""

    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,r_frame_rate,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise RuntimeError("ffprobe returned no stream list")
    video = next(
        (stream for stream in streams if isinstance(stream, Mapping) and stream.get("codec_type") == "video"),
        None,
    )
    if not isinstance(video, Mapping):
        raise RuntimeError("repair media has no video stream")
    raw_rate = str(video.get("r_frame_rate") or "")
    try:
        numerator, denominator = raw_rate.split("/", 1)
        fps = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError) as exc:
        raise RuntimeError("repair media has invalid frame rate") from exc
    raw_format = payload.get("format")
    if not isinstance(raw_format, Mapping):
        raise RuntimeError("ffprobe returned no format facts")
    duration = float(raw_format.get("duration") or 0.0)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if duration <= 0 or fps <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("repair media has invalid duration/fps/dimensions")
    has_audio = any(
        isinstance(stream, Mapping) and stream.get("codec_type") == "audio" for stream in streams
    )
    return H3VideoStreamFacts(
        duration_seconds=duration,
        fps=fps,
        width=width,
        height=height,
        has_audio=has_audio,
    )


def run_h3_ffmpeg_command(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def assemble_h3_shot_window(
    source_unit_media: Path,
    provider_shot_media: Path,
    output_unit_media: Path,
    request: H3ShotRepairRequest,
    *,
    probe_media: Callable[[Path], H3VideoStreamFacts] = probe_h3_video_stream,
    run_command: Callable[[Sequence[str]], None] = run_h3_ffmpeg_command,
) -> None:
    """Replace exactly one Canonical shot window and preserve source Unit audio."""

    source = probe_media(source_unit_media)
    repair = probe_media(provider_shot_media)
    tolerance = 1.0 / source.fps
    if request.start_seconds < 0 or request.end_seconds > source.duration_seconds + tolerance:
        raise RuntimeError("approved repair window is outside source Unit duration")
    if request.duration_seconds <= 0 or repair.duration_seconds <= 0:
        raise RuntimeError("repair shot duration is invalid")
    if output_unit_media.resolve() == source_unit_media.resolve():
        raise ValueError("repair assembly output must not overwrite the accepted source Unit in place")

    output_unit_media.parent.mkdir(parents=True, exist_ok=True)
    temp = output_unit_media.with_name(f".{output_unit_media.name}.assembling.tmp")

    filters: list[str] = []
    labels: list[str] = []
    if request.start_seconds > tolerance:
        filters.append(
            f"[0:v]trim=start=0:end={request.start_seconds:.9f},setpts=PTS-STARTPTS[vpre]"
        )
        labels.append("[vpre]")

    pts_factor = request.duration_seconds / repair.duration_seconds
    filters.append(
        f"[1:v]trim=start=0:end={repair.duration_seconds:.9f},setpts=(PTS-STARTPTS)*{pts_factor:.12f},"
        f"scale={source.width}:{source.height}:flags=lanczos,fps={source.fps:.12f},format=yuv420p[vrepair]"
    )
    labels.append("[vrepair]")

    if request.end_seconds < source.duration_seconds - tolerance:
        filters.append(
            f"[0:v]trim=start={request.end_seconds:.9f}:end={source.duration_seconds:.9f},"
            "setpts=PTS-STARTPTS[vpost]"
        )
        labels.append("[vpost]")

    if len(labels) == 1:
        filters.append(f"{labels[0]}null[v]")
    else:
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[v]")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_unit_media),
        "-i",
        str(provider_shot_media),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
    ]
    if source.has_audio:
        command.extend(["-map", "0:a?", "-c:a", "copy"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-r",
            f"{source.fps:.12f}",
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{source.duration_seconds:.9f}",
            "-movflags",
            "+faststart",
            str(temp),
        ]
    )

    try:
        run_command(command)
        if not temp.is_file() or temp.stat().st_size == 0:
            raise RuntimeError("deterministic H3 shot reassembly produced no output")
        temp.replace(output_unit_media)
    finally:
        temp.unlink(missing_ok=True)
