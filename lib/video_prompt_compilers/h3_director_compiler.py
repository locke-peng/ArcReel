"""Canonical Director -> MiniMax H3 deterministic compiler.

V6 bridge:
- structured multi-shot timing
- per-shot dialogue ownership
- cross-shot continuous dialogue via <scenetrans>
- T2VA when no actual provider references exist
- Ref2VA when references exist
- soundscape / music propagation
- live / depicted / referenced entity role constraints

This module is intentionally stdlib-only.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any, Literal

from lib.reference_video.h3_production_policy import (
    H3ProductionPolicyError,
    validate_h3_canonical_unit,
)

H3_MIN_DURATION_SECONDS = 4
H3_MAX_DURATION_SECONDS = 15
H3_MAX_REFERENCE_IMAGES = 9
H3_DEFAULT_MAX_PROMPT_CHARS = 500_000

GenerationMode = Literal["t2va", "ref2va"]


class H3DirectorCompileError(ValueError):
    pass



_LEGACY_DIALOGUE_RE = re.compile(
    r"@\[(?P<speaker>[^\]\r\n]+)\][ \t]*(?:[：:][ \t]*)?\{(?P<text>[^{}\r\n]*)\}"
)
_LEGACY_MENTION_RE = re.compile(r"@\[(?P<name>[^\]\r\n]+)\]")
_H3_SECTION_RE = re.compile(
    r"(?m)^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):\s*$"
)


def _legacy_inline_body(text: str) -> str:
    """Render ArcReel dialogue markers in place so shot ownership is not lost."""
    speaker_ids: dict[str, str] = {}

    def dialogue_repl(match: re.Match[str]) -> str:
        speaker = match.group("speaker").strip()
        sid = speaker_ids.setdefault(speaker, f"S{len(speaker_ids) + 1}")
        dialogue = match.group("text")
        return f"{speaker} ({sid}) says: <d>[Chinese] {dialogue}</d>"

    rendered = _LEGACY_DIALOGUE_RE.sub(dialogue_repl, text)
    rendered = _LEGACY_MENTION_RE.sub(lambda m: m.group("name").strip(), rendered)
    return rendered.strip()


def compile_h3_text_t2va_prompt(
    *,
    source_prompt: str,
    duration_seconds: int,
    overall_soundscape: str = "N/A",
    non_diegetic_music: str = "N/A",
    max_prompt_chars: int = H3_DEFAULT_MAX_PROMPT_CHARS,
) -> str:
    """Compile legacy free-form ArcReel text into an H3 T2VA prompt.

    Existing [Shot N] / timestamps are preserved verbatim; dialogue is converted in
    place instead of being hoisted to the end of the unit.
    """
    if not source_prompt or not source_prompt.strip():
        raise H3DirectorCompileError("source_prompt must not be blank")
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        raise H3DirectorCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; got {duration}s"
        )
    required = {
        "subject_definitions",
        "summary",
        "retention_analysis",
        "detailed_description",
        "overall_soundscape",
        "non_diegetic_music",
    }
    found = {m.group(1) for m in _H3_SECTION_RE.finditer(source_prompt)}
    if required.issubset(found):
        prompt = source_prompt.strip()
    else:
        body = _legacy_inline_body(source_prompt)
        detailed = body if re.search(r"(?m)^\[Shot\s+\d+\]", body) else f"[Shot 1] {body}"
        prompt = "\n".join(
            [
                "subject_definitions:",
                "T2VA mode: no provider reference image is attached; do not invent Picture/Subject bindings.",
                "",
                "summary:",
                f"[T2VA] Create one continuous {duration}-second target video and follow the authored shot timing, "
                "actions, camera instructions, performance, and dialogue exactly.",
                "",
                "retention_analysis:",
                "T2VA: no visual reference retention requirement.",
                "",
                "detailed_description:",
                detailed,
                "",
                "overall_soundscape:",
                overall_soundscape.strip() or "N/A",
                "",
                "non_diegetic_music:",
                non_diegetic_music.strip() or "N/A",
            ]
        ).strip()
    if len(prompt) > int(max_prompt_chars):
        raise H3DirectorCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {max_prompt_chars}"
        )
    return prompt


@dataclass(frozen=True)
class DirectorReference:
    source_name: str
    label: str
    index: int
    kind: str = "unknown"

    @property
    def subject(self) -> str:
        return f"<Subject {self.index}>"

    @property
    def picture(self) -> str:
        return f"<Picture {self.index}>"


@dataclass(frozen=True)
class CanonicalDirectorBundle:
    unit: Mapping[str, Any]
    registries: Mapping[str, Any]

    @classmethod
    def resolve(
        cls,
        payload: Mapping[str, Any],
        *,
        unit_id: str | None,
    ) -> "CanonicalDirectorBundle":
        """Accept full episode payload, {unit, registries}, or a unit-only object."""
        registries = payload.get("registries")
        if not isinstance(registries, Mapping):
            registries = {}

        if isinstance(payload.get("unit"), Mapping):
            unit = payload["unit"]
        elif isinstance(payload.get("units"), Sequence) and not isinstance(payload.get("units"), (str, bytes)):
            units = [x for x in payload["units"] if isinstance(x, Mapping)]
            if unit_id is None:
                if len(units) != 1:
                    raise H3DirectorCompileError(
                        "canonical_director with multiple units requires unit_id"
                    )
                unit = units[0]
            else:
                found = [x for x in units if str(x.get("unit_id") or "") == unit_id]
                if len(found) != 1:
                    raise H3DirectorCompileError(
                        f"canonical_director does not contain exactly one unit {unit_id!r}"
                    )
                unit = found[0]
        else:
            unit = payload

        resolved_id = str(unit.get("unit_id") or "").strip()
        if unit_id and resolved_id and resolved_id != unit_id:
            raise H3DirectorCompileError(
                f"canonical director unit mismatch: requested {unit_id!r}, got {resolved_id!r}"
            )
        return cls(unit=unit, registries=registries)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _character_name(entity_id: str, registries: Mapping[str, Any]) -> str:
    characters = _mapping(registries.get("characters"))
    entry = _mapping(characters.get(entity_id))
    return str(entry.get("name") or entity_id)


def _scene_name(scene_id: str, registries: Mapping[str, Any]) -> str:
    scenes = _mapping(registries.get("scenes"))
    entry = scenes.get(scene_id)
    if isinstance(entry, str):
        return scene_id
    if isinstance(entry, Mapping):
        return str(entry.get("name") or scene_id)
    return scene_id


def _entity_names(ids: Sequence[object], registries: Mapping[str, Any]) -> list[str]:
    return [_character_name(str(x), registries) for x in ids]


def _format_ts(seconds: float) -> str:
    if seconds < 0:
        raise H3DirectorCompileError("shot timestamp must be >= 0")
    total_ms = int(round(seconds * 1000))
    minutes, rem = divmod(total_ms, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _camera_sentence(shot: Mapping[str, Any]) -> str:
    lens = shot.get("lens_mm")
    lens_text = f"{int(lens)}mm lens" if isinstance(lens, (int, float)) and not isinstance(lens, bool) else ""

    pos = str(shot.get("camera_position_code") or "")
    pos_map = {
        "CAM-EYE": "eye-level camera",
        "CAM-LOW": "low-angle camera",
        "CAM-HIGH": "high-angle camera",
    }
    position = pos_map.get(pos, "")

    motion = _mapping(shot.get("camera_motion"))
    motion_type = str(motion.get("type") or "static")
    direction = str(motion.get("direction") or "none")
    amplitude = str(motion.get("amplitude") or "none")
    speed = str(motion.get("speed") or "normal")

    amp = {
        "very_small": "extremely subtle",
        "small": "small",
        "medium": "moderate",
        "large": "large",
        "none": "",
    }.get(amplitude, amplitude.replace("_", " "))
    speed_text = {
        "slow": "slow",
        "normal": "",
        "fast": "fast",
        "static": "",
    }.get(speed, speed)

    if motion_type == "static":
        move = "static shot"
    elif motion_type == "push_in":
        move = " ".join(x for x in [speed_text, amp, "push-in"] if x)
    elif motion_type == "pull_out":
        move = " ".join(x for x in [speed_text, amp, "pull-out"] if x)
    elif motion_type == "truck":
        d = {"left": "left", "right": "right", "parallel": "laterally"}.get(direction, direction)
        move = " ".join(x for x in [speed_text, amp, "truck", d] if x)
    elif motion_type == "tracking":
        d = "following the subject" if direction == "follow_subject" else direction.replace("_", " ")
        move = " ".join(x for x in [speed_text, amp, "tracking shot", d] if x)
    else:
        move = motion_type.replace("_", " ")

    parts = [x for x in (lens_text, position, move) if x]
    return "Camera: " + ", ".join(parts) + "." if parts else ""


def _screen_text_lines(shot: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in _list(shot.get("screen_text")):
        if not isinstance(item, Mapping):
            continue
        legibility = str(item.get("legibility") or "")
        kind = str(item.get("kind") or "screen text")
        text = item.get("text")
        semantic = str(item.get("semantic") or "")
        if legibility == "exact":
            if not isinstance(text, str) or not text:
                raise H3DirectorCompileError(
                    f"exact screen text in {shot.get('shot_id')} requires non-empty text"
                )
            lines.append(f'On-screen {kind}: render exactly "{text}" and keep it clearly readable.')
        elif legibility == "blurred_unreadable":
            detail = f" ({semantic})" if semantic else ""
            lines.append(f"On-screen {kind}{detail}: visible as UI/content but deliberately unreadable.")
        elif legibility == "semantic_only":
            detail = f": {semantic}" if semantic else ""
            lines.append(f"On-screen {kind}{detail}; communicate the state without requiring readable text.")
    return lines


def _dialogue_groups(unit: Mapping[str, Any]) -> tuple[dict[str, str], set[tuple[str, str]], set[str]]:
    """Return group-by-shot, continuation boundaries, and continuation target shots."""
    group_for_shot: dict[str, str] = {}
    boundaries: set[tuple[str, str]] = set()
    targets: set[str] = set()
    for group in _list(unit.get("cross_shot_dialogue")):
        if not isinstance(group, Mapping) or not group.get("continuous"):
            continue
        shot_ids = [str(x) for x in _list(group.get("shot_ids")) if str(x)]
        gid = str(group.get("dialogue_group_id") or "")
        for sid in shot_ids:
            if gid:
                group_for_shot[sid] = gid
        for left, right in zip(shot_ids, shot_ids[1:]):
            boundaries.add((left, right))
            targets.add(right)
    return group_for_shot, boundaries, targets


def _speaker_map(unit: Mapping[str, Any]) -> dict[str, str]:
    order = [str(x) for x in _list(unit.get("speaker_semantic_order")) if str(x)]
    for shot in _list(unit.get("shots")):
        if not isinstance(shot, Mapping):
            continue
        for item in _list(shot.get("dialogue")):
            if not isinstance(item, Mapping):
                continue
            sid = str(item.get("speaker_id") or "")
            if sid and sid not in order:
                order.append(sid)
    return {entity_id: f"S{i}" for i, entity_id in enumerate(order, start=1)}


def _reference_map(
    *,
    source_names: Sequence[str],
    labels: Sequence[str],
    kinds: Mapping[str, str] | None,
) -> tuple[DirectorReference, ...]:
    if len(source_names) != len(labels):
        raise H3DirectorCompileError("reference labels must match actual provider reference count")
    if len(source_names) > H3_MAX_REFERENCE_IMAGES:
        raise H3DirectorCompileError(
            f"MiniMax H3 supports at most {H3_MAX_REFERENCE_IMAGES} reference images"
        )
    kind_map = kinds or {}
    refs = []
    for i, (source, label) in enumerate(zip(source_names, labels, strict=True), start=1):
        source = str(source).strip()
        label = str(label).strip()
        if not source or not label:
            raise H3DirectorCompileError("reference source names and labels must not be blank")
        refs.append(DirectorReference(source, label, i, str(kind_map.get(source, "unknown"))))
    return tuple(refs)


def _subject_for_entity(
    entity_id: str,
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> str | None:
    name = _character_name(entity_id, registries)
    normalized = {name.casefold(), entity_id.casefold()}
    for ref in references:
        if ref.source_name.casefold() in normalized or ref.label.casefold() in normalized:
            return ref.subject
    return None


def _subject_definitions(
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> str:
    if references:
        lines = []
        for ref in references:
            identity = ref.label
            if ref.label != ref.source_name:
                identity += f" (ArcReel asset: {ref.source_name})"
            if ref.kind == "scene":
                lines.append(
                    f"{ref.subject} is the environment from {ref.picture}, corresponding to {identity}. "
                    "Preserve spatial layout, architecture, major props, and stable visual anchors."
                )
            elif ref.kind == "character":
                lines.append(
                    f"{ref.subject} is the character from {ref.picture}, corresponding to {identity}. "
                    "Preserve identity, face, hairstyle, costume, body proportions, and stable visual traits."
                )
            elif ref.kind in {"object", "prop", "product"}:
                lines.append(
                    f"{ref.subject} is the object from {ref.picture}, corresponding to {identity}. "
                    "Preserve shape, material, proportions, and identifying visual details."
                )
            else:
                lines.append(
                    f"{ref.subject} is the reusable visible subject from {ref.picture}, corresponding to {identity}. "
                    "Preserve its stable identity and reference-defining attributes."
                )
        return "\n".join(lines)

    active = _entity_names(_list(unit.get("active_subject_ids")), registries)
    scene_id = str(unit.get("scene_id") or "")
    lines = ["T2VA mode: no provider reference image is attached; do not invent Picture/Subject bindings."]
    if active:
        lines.append("Live characters in this unit: " + ", ".join(active) + ".")
    if scene_id:
        lines.append("Scene: " + _scene_name(scene_id, registries) + ".")
    return "\n".join(lines)


def _role_constraints(unit: Mapping[str, Any], registries: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    active = _entity_names(_list(unit.get("active_subject_ids")), registries)
    depicted = _entity_names(_list(unit.get("depicted_subject_ids")), registries)
    referenced = _entity_names(_list(unit.get("referenced_entity_ids")), registries)
    if active:
        lines.append("Live characters physically present in the scene: " + ", ".join(active) + ".")
    if depicted:
        lines.append(
            "Embedded-media-only subjects: "
            + ", ".join(depicted)
            + ". They may appear only inside photographs, screens, posters, or other embedded media; "
              "do not render them as live people in the physical scene."
        )
    if referenced:
        lines.append(
            "Referenced-only entities: "
            + ", ".join(referenced)
            + ". They are mentioned or represented by UI/contact state only; do not visually spawn them."
        )
    return lines


def _retention_analysis(
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> str:
    lines = []
    for ref in references:
        lines.append(
            f"{ref.subject}: fully_preserved - retain the identity and stable visual attributes of {ref.label}."
        )
    level = str(unit.get("continuity_level") or "")
    if level in {"hard", "locked"}:
        lines.append(
            f"Continuity level {level}: preserve the structured continuity_in → continuity_out state across this unit."
        )
    if not lines:
        lines.append("T2VA: no visual reference retention requirement.")
    return "\n".join(lines)


def _dialogue_line(
    *,
    speaker_id: str,
    text: str,
    delivery: str,
    speaker_map: Mapping[str, str],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
    continuation: bool,
) -> str:
    sid = speaker_map.get(speaker_id)
    if sid is None:
        raise H3DirectorCompileError(f"dialogue speaker {speaker_id!r} missing from speaker map")
    name = _character_name(speaker_id, registries)
    subject = _subject_for_entity(speaker_id, registries, references)
    who = f"{subject} ({sid})" if subject else f"{name} ({sid})"
    verb = "continues the same utterance" if continuation else "says"
    delivery_text = f", delivery: {delivery}" if delivery else ""
    # Dialogue must remain verbatim. Never auto-append punctuation: fragments may end in ，.
    return f"{who} {verb}{delivery_text}: <d>[Chinese] {text}</d>"


def _shot_lines(
    *,
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> list[str]:
    shots = [x for x in _list(unit.get("shots")) if isinstance(x, Mapping)]
    if not shots:
        raise H3DirectorCompileError("canonical director unit requires non-empty shots")

    speaker_ids = _speaker_map(unit)
    group_for_shot, boundaries, continuation_targets = _dialogue_groups(unit)
    result: list[str] = []

    previous_shot_id: str | None = None
    for index, shot in enumerate(shots, start=1):
        shot_id = str(shot.get("shot_id") or f"Shot-{index}")
        start = float(shot.get("start_sec") or 0)
        if index == 1:
            if abs(start) > 1e-6:
                raise H3DirectorCompileError("first canonical shot must start at 0")
            result.append("[Shot 1]")
        else:
            if previous_shot_id is not None and (previous_shot_id, shot_id) in boundaries:
                result.append("<scenetrans>")
            result.append(f"[Shot {index}] At {_format_ts(start)}")

        action = str(shot.get("action") or "").strip()
        if action:
            result.append(action)

        camera = _camera_sentence(shot)
        if camera:
            result.append(camera)

        emotion = str(shot.get("emotion_motion") or "").strip()
        if emotion:
            result.append(f"Performance / emotional beat: {emotion}.")

        result.extend(_screen_text_lines(shot))

        if shot_id in continuation_targets:
            gid = group_for_shot.get(shot_id)
            suffix = f" ({gid})" if gid else ""
            result.append(
                "Audio continuity"
                + suffix
                + ": continue the same speaker and the same sentence seamlessly across the cut; "
                  "no restart, no pause, no speaker remapping."
            )

        direction = shot.get("dialogue_direction")
        direction_map = direction if isinstance(direction, Mapping) else {}
        direction_scalar = direction if isinstance(direction, str) else ""

        for item in _list(shot.get("dialogue")):
            if not isinstance(item, Mapping):
                continue
            speaker_id = str(item.get("speaker_id") or "")
            text = str(item.get("text") or "")
            if not speaker_id or not text:
                continue
            delivery = str(direction_map.get(speaker_id) or direction_scalar or "")
            result.append(
                _dialogue_line(
                    speaker_id=speaker_id,
                    text=text,
                    delivery=delivery,
                    speaker_map=speaker_ids,
                    registries=registries,
                    references=references,
                    continuation=shot_id in continuation_targets,
                )
            )
        previous_shot_id = shot_id

    return result


def compile_h3_director_prompt(
    *,
    canonical_director: Mapping[str, Any],
    unit_id: str | None,
    duration_seconds: int,
    reference_source_names: Sequence[str] = (),
    reference_image_labels: Sequence[str] = (),
    reference_kinds: Mapping[str, str] | None = None,
    max_prompt_chars: int = H3_DEFAULT_MAX_PROMPT_CHARS,
) -> tuple[str, GenerationMode]:
    """Compile Canonical Director data into an H3 execution prompt."""
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        raise H3DirectorCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; got {duration}s"
        )
    bundle = CanonicalDirectorBundle.resolve(canonical_director, unit_id=unit_id)
    unit = bundle.unit
    registries = bundle.registries

    try:
        validate_h3_canonical_unit(unit, provider_duration_seconds=duration)
    except H3ProductionPolicyError as exc:
        raise H3DirectorCompileError(str(exc)) from exc

    unit_duration = unit.get("duration_sec")
    if isinstance(unit_duration, (int, float)) and not isinstance(unit_duration, bool):
        if abs(float(unit_duration) - duration) > 1e-6:
            raise H3DirectorCompileError(
                f"canonical director duration {unit_duration}s does not match provider duration {duration}s"
            )

    refs = _reference_map(
        source_names=reference_source_names,
        labels=reference_image_labels,
        kinds=reference_kinds,
    )
    mode: GenerationMode = "ref2va" if refs else "t2va"

    subject_definitions = _subject_definitions(unit, registries, refs)
    active = _entity_names(_list(unit.get("active_subject_ids")), registries)
    summary = (
        f"[{mode.upper()}] Create one {duration}-second 16:9 video as a structured multi-shot unit. "
        f"Live characters: {', '.join(active) if active else 'none explicitly declared'}. "
        "Follow the shot timing, staging, camera movement, performance, text legibility, and dialogue exactly."
    )
    retention = _retention_analysis(unit, registries, refs)

    detailed: list[str] = []
    detailed.extend(_role_constraints(unit, registries))
    detailed.extend(_shot_lines(unit=unit, registries=registries, references=refs))

    notes = _mapping(unit.get("director_notes"))
    ambience = str(
        _mapping(unit.get("sound_design")).get("ambience")
        or notes.get("ambience")
        or "N/A"
    ).strip() or "N/A"
    music = str(
        _mapping(unit.get("sound_design")).get("music")
        or notes.get("music")
        or "N/A"
    ).strip() or "N/A"

    prompt = "\n".join(
        [
            "subject_definitions:",
            subject_definitions,
            "",
            "summary:",
            summary,
            "",
            "retention_analysis:",
            retention,
            "",
            "detailed_description:",
            "\n".join(detailed),
            "",
            "overall_soundscape:",
            ambience,
            "",
            "non_diegetic_music:",
            music,
        ]
    ).strip()
    if len(prompt) > int(max_prompt_chars):
        raise H3DirectorCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {max_prompt_chars}"
        )
    return prompt, mode
