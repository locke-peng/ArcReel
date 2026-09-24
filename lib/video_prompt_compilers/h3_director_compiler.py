"""Canonical Director -> MiniMax H3 native prompt compiler.

The compiler follows MiniMax's official ``h3-prompt-writing`` contract instead of
inventing an ArcReel-specific prompt dialect:

* T2VA emits exactly ``integrated_multimodal_description`` ->
  ``overall_soundscape`` -> ``non_diegetic_music``.
* Ref2VA emits exactly ``subject_definitions`` -> ``summary`` ->
  ``retention_analysis`` -> ``detailed_description`` -> ``overall_soundscape`` ->
  ``non_diegetic_music``.
* Provider-facing execution prose is English.  Dialogue and exact visible scene text
  preserve their original language.
* Speaker IDs are assigned per target unit by actual first vocal event.
* Canonical v3.3 director dimensions remain first-class; fields that carry semantic
  prose may provide an ``*_en`` execution form.  Non-English execution prose fails
  before provider submission rather than being silently forwarded.

The module is deterministic and stdlib-only so prompt preview/runtime hashes remain
stable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3_DEFAULT_MAX_PROMPT_CHARS,
    H3_MAX_DURATION_SECONDS,
    H3_MAX_REFERENCE_IMAGES,
    H3_MIN_DURATION_SECONDS,
    validate_h3_native_ref2va_prompt,
    validate_h3_native_t2va_prompt,
)

GenerationMode = Literal["t2va", "ref2va"]
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_BASE_SECTION_RE = re.compile(
    r"(?m)^(integrated_multimodal_description|overall_soundscape|non_diegetic_music):[ \t]*"
)
_REF_SECTION_RE = re.compile(
    r"(?m)^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):[ \t]*"
)
_LEGACY_DIALOGUE_RE = re.compile(
    r"@\[(?P<speaker>[^\]\r\n]+)\][ \t]*(?:[：:][ \t]*)?\{(?P<text>[^{}\r\n]*)\}"
)
_LEGACY_MENTION_RE = re.compile(r"@\[(?P<name>[^\]\r\n]+)\]")
_SHOT_HEADER_RE = re.compile(
    r"(?m)^\[Shot\s+(?P<number>\d+)\](?:\s+At\s+(?P<minutes>\d{2}):(?P<seconds>\d{2})\.(?P<millis>\d{3}))?"
)
_NO_MUSIC_SENTINELS = {
    "n/a", "none", "no music", "no score", "without music", "无配乐", "无音乐", "无bgm",
}
_SILENCE_SENTINELS = {"n/a", "silence", "silent", "complete silence", "静音", "全片静音"}
_TRANSITION_MAP = {
    "cut": "the shot cuts to the next view",
    "hard_cut": "the shot cuts cleanly to the next view",
    "硬切": "the shot cuts cleanly to the next view",
    "dissolve": "the shot cross-dissolves into the next view",
    "cross_dissolve": "the shot cross-dissolves into the next view",
    "溶接": "the shot cross-dissolves into the next view",
    "fade": "the shot fades into the next view",
    "fade_in_out": "the shot fades through the transition into the next view",
    "淡入淡出": "the shot fades through the transition into the next view",
    "褪色淡入": "the image fades into the next view",
    "wipe": "a wipe transition reveals the next view",
}


class H3DirectorCompileError(ValueError):
    """Raised when Canonical Director data cannot produce a native H3 prompt."""


@dataclass(frozen=True)
class DirectorReference:
    source_name: str
    label: str
    picture_index: int
    subject_index: int
    kind: str = "unknown"

    @property
    def subject(self) -> str:
        return f"<Subject {self.subject_index}>"

    @property
    def picture(self) -> str:
        return f"<Picture {self.picture_index}>"


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
        registries = payload.get("registries")
        if not isinstance(registries, Mapping):
            registries = {}

        if isinstance(payload.get("unit"), Mapping):
            unit = payload["unit"]
        elif isinstance(payload.get("units"), Sequence) and not isinstance(payload.get("units"), (str, bytes)):
            units = [x for x in payload["units"] if isinstance(x, Mapping)]
            if unit_id is None:
                if len(units) != 1:
                    raise H3DirectorCompileError("canonical_director with multiple units requires unit_id")
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


def _format_ts(seconds: float) -> str:
    if seconds < 0:
        raise H3DirectorCompileError("shot timestamp must be >= 0")
    total_ms = int(round(seconds * 1000))
    minutes, rem = divmod(total_ms, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _contains_cjk(value: str) -> bool:
    return bool(_CJK_RE.search(value))


def _english_value(
    owner: Mapping[str, Any],
    key: str,
    *,
    path: str,
    required: bool = False,
) -> str:
    """Read ``key_en`` first, then an already-English ``key`` value.

    This intentionally does not machine-translate semantic prose.  The official H3
    skill requires English rewrite sections; passing Chinese director prose through
    would be non-compliant and makes prompt-preview hashes misleading.
    """
    preferred = owner.get(f"{key}_en")
    raw = preferred if preferred not in (None, "") else owner.get(key)
    if raw is None or raw == "":
        if required:
            raise H3DirectorCompileError(
                f"{path}.{key}_en is required for strict H3 native compilation"
            )
        return ""
    if isinstance(raw, Mapping) or (
        isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
    ):
        raise H3DirectorCompileError(
            f"{path}.{key} is structured semantic content; provide {key}_en as natural English H3 execution prose"
        )
    text = str(raw).strip()
    if _contains_cjk(text):
        raise H3DirectorCompileError(
            f"{path}.{key} contains non-English execution prose; provide {path}.{key}_en before H3 submission"
        )
    return text


def _english_optional_direct(owner: Mapping[str, Any], key: str, *, path: str) -> str:
    raw = owner.get(key)
    if raw is None or raw == "":
        return ""
    text = str(raw).strip()
    if _contains_cjk(text):
        raise H3DirectorCompileError(f"{path}.{key} must be English in the H3 execution layer")
    return text


def _character_entry(entity_id: str, registries: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(registries.get("characters")).get(entity_id))


def _character_name(entity_id: str, registries: Mapping[str, Any]) -> str:
    entry = _character_entry(entity_id, registries)
    return str(entry.get("name") or entity_id)


def _scene_entry(scene_id: str, registries: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _mapping(registries.get("scenes")).get(scene_id)
    return _mapping(value)


def _stable_speaker_description(entity_id: str, sid: str, registries: Mapping[str, Any]) -> str:
    entry = _character_entry(entity_id, registries)
    description = str(
        entry.get("h3_speaker_description_en")
        or entry.get("speaker_description_en")
        or ""
    ).strip()
    if description:
        if _contains_cjk(description):
            raise H3DirectorCompileError(
                f"character {entity_id!r} speaker_description_en must be English"
            )
        return f"{description} ({sid})"
    return f"The on-screen speaker ({sid})"


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
    refs: list[DirectorReference] = []
    subject_index_by_source: dict[str, int] = {}
    for index, (source, label) in enumerate(zip(source_names, labels, strict=True), start=1):
        source = str(source).strip()
        label = str(label).strip()
        if not source or not label:
            raise H3DirectorCompileError("reference source names and labels must not be blank")
        logical_key = source.casefold()
        subject_index = subject_index_by_source.setdefault(
            logical_key, len(subject_index_by_source) + 1
        )
        refs.append(
            DirectorReference(
                source,
                label,
                picture_index=index,
                subject_index=subject_index,
                kind=str(kind_map.get(source, "unknown")),
            )
        )
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


def _group_director_references(
    references: Sequence[DirectorReference],
) -> list[tuple[DirectorReference, tuple[DirectorReference, ...]]]:
    grouped: dict[int, list[DirectorReference]] = {}
    for ref in references:
        grouped.setdefault(ref.subject_index, []).append(ref)
    return [(items[0], tuple(items)) for _, items in sorted(grouped.items())]


def _picture_phrase(group: Sequence[DirectorReference]) -> str:
    pictures = [ref.picture for ref in group]
    if len(pictures) == 1:
        return pictures[0]
    if len(pictures) == 2:
        return f"{pictures[0]} and {pictures[1]}"
    return ", ".join(pictures[:-1]) + f", and {pictures[-1]}"


def _subject_definitions(references: Sequence[DirectorReference]) -> str:
    lines: list[str] = []
    for ref, group in _group_director_references(references):
        source = _picture_phrase(group)
        if ref.kind == "scene":
            lines.append(
                f"{ref.subject} is the environment defined by {source}; preserve its spatial layout, "
                "architecture, major props, lighting identity, and stable visual anchors."
            )
        elif ref.kind == "character":
            lines.append(
                f"{ref.subject} is the character defined by {source}; preserve facial identity, hairstyle, "
                "costume, body proportions, and stable visual traits."
            )
        elif ref.kind in {"object", "prop", "product"}:
            lines.append(
                f"{ref.subject} is the object defined by {source}; preserve its shape, material, proportions, "
                "and identifying visual details."
            )
        elif ref.kind == "style":
            lines.append(
                f"{ref.subject} is the visual style defined by {source}; preserve the referenced palette, "
                "texture, lighting treatment, and rendering characteristics."
            )
        else:
            lines.append(
                f"{ref.subject} is the reusable visible subject defined by {source}; preserve its stable "
                "identity and reference-defining visual attributes."
            )
    return "\n".join(lines)


def _speaker_map(unit: Mapping[str, Any]) -> dict[str, str]:
    """Assign Sx strictly by first *actual vocal event* in this target unit."""
    order: list[str] = []
    for shot in _list(unit.get("shots")):
        if not isinstance(shot, Mapping):
            continue
        for item in _list(shot.get("dialogue")):
            if not isinstance(item, Mapping):
                continue
            speaker = str(item.get("speaker_id") or "").strip()
            if speaker and speaker not in order:
                order.append(speaker)
    return {entity_id: f"S{index}" for index, entity_id in enumerate(order, start=1)}


def _dialogue_groups(
    unit: Mapping[str, Any],
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    """Return (continues_to_next, continues_from_previous) triples."""
    to_next: set[tuple[str, str, str]] = set()
    from_prev: set[tuple[str, str, str]] = set()
    for group in _list(unit.get("cross_shot_dialogue")):
        if not isinstance(group, Mapping) or not group.get("continuous"):
            continue
        speaker = str(group.get("speaker_id") or "").strip()
        shot_ids = [str(x) for x in _list(group.get("shot_ids")) if str(x)]
        for left, right in zip(shot_ids, shot_ids[1:]):
            to_next.add((left, right, speaker))
            from_prev.add((right, left, speaker))
    return to_next, from_prev


def _camera_sentence(shot: Mapping[str, Any]) -> str:
    lens = shot.get("lens_mm")
    lens_text = (
        f"with a focal length of {int(lens)}mm"
        if isinstance(lens, (int, float)) and not isinstance(lens, bool)
        else ""
    )
    pos = str(shot.get("camera_position_code") or "")
    position = {
        "CAM-EYE": "at eye level",
        "CAM-LOW": "from a low angle",
        "CAM-HIGH": "from a high angle",
        "CAM-GROUND": "from ground level",
    }.get(pos, "")

    motion = _mapping(shot.get("camera_motion"))
    motion_type = str(motion.get("type") or "static")
    direction = str(motion.get("direction") or "none")
    amplitude = str(motion.get("amplitude") or "none")
    speed = str(motion.get("speed") or "normal")

    amplitude_text = {
        "very_small": " with very small amplitude",
        "small": " with small amplitude",
        "medium": "",
        "large": " with large amplitude",
        "none": "",
    }.get(amplitude, "")
    speed_text = {
        "slow": " at slow speed",
        "normal": "",
        "fast": " at fast speed",
        "static": "",
    }.get(speed, "")

    if motion_type == "static":
        motion_text = "holds a static shot"
    elif motion_type == "push_in":
        motion_text = f"pushes in{amplitude_text}{speed_text}"
    elif motion_type == "pull_out":
        motion_text = f"pulls out{amplitude_text}{speed_text}"
    elif motion_type == "zoom_in":
        motion_text = f"zooms in{amplitude_text}{speed_text}"
    elif motion_type == "zoom_out":
        motion_text = f"zooms out{amplitude_text}{speed_text}"
    elif motion_type in {"pan", "pan_left", "pan_right"}:
        side = {
            "left": "left", "right": "right", "pan_left": "left", "pan_right": "right"
        }.get(direction, "right" if motion_type == "pan_right" else "left" if motion_type == "pan_left" else "")
        motion_text = f"pans {side}{amplitude_text}{speed_text}".strip()
    elif motion_type == "truck":
        side = {"left": "left", "right": "right", "parallel": "laterally"}.get(direction, direction)
        motion_text = f"trucks {side}{amplitude_text}{speed_text}".strip()
    elif motion_type == "tracking":
        target = " while following the moving subject" if direction == "follow_subject" else ""
        motion_text = f"uses a tracking shot{amplitude_text}{speed_text}{target}"
    elif motion_type == "tilt_up":
        motion_text = f"tilts up{amplitude_text}{speed_text}"
    elif motion_type == "tilt_down":
        motion_text = f"tilts down{amplitude_text}{speed_text}"
    else:
        cleaned = motion_type.replace("_", " ").strip()
        if not cleaned or _contains_cjk(cleaned):
            raise H3DirectorCompileError(
                f"unsupported/non-English camera_motion.type {motion_type!r}; provide a supported H3 motion code"
            )
        motion_text = f"uses {cleaned}"

    tail = " ".join(x for x in (lens_text, position) if x)
    return f"The camera {motion_text}{(' ' + tail) if tail else ''}."


def _visual_language_sentences(shot: Mapping[str, Any], *, path: str) -> list[str]:
    sentences: list[str] = []
    framing = _english_value(shot, "shot_size", path=path) or _english_value(shot, "framing", path=path)
    composition = _english_value(shot, "composition", path=path)
    if framing and composition:
        sentences.append(f"The framing is {framing}, using {composition}.")
    elif framing:
        sentences.append(f"The framing is {framing}.")
    elif composition:
        sentences.append(f"The composition uses {composition}.")

    lighting = _english_value(shot, "lighting", path=path)
    if lighting:
        sentences.append(f"The lighting uses {lighting}.")
    color_grade = _english_value(shot, "color_grade", path=path)
    if color_grade:
        sentences.append(f"The color treatment uses {color_grade}.")
    anchors = _english_value(shot, "scene_anchors", path=path)
    if anchors:
        sentences.append(f"The shot preserves these stable scene anchors: {anchors}.")
    return sentences


def _transition_phrase(value: object, *, path: str) -> str:
    if value in (None, "", {}, []):
        return ""
    if isinstance(value, Mapping):
        candidate = value.get("type_en") or value.get("type") or value.get("name_en") or value.get("name")
    else:
        candidate = value
    text = str(candidate or "").strip()
    if not text:
        return ""
    key = text.lower().replace(" ", "_")
    if text in _TRANSITION_MAP:
        return _TRANSITION_MAP[text]
    if key in _TRANSITION_MAP:
        return _TRANSITION_MAP[key]
    if _contains_cjk(text):
        raise H3DirectorCompileError(
            f"{path} contains non-English transition prose; provide an English transition code/value"
        )
    return f"the shot transitions using {text}"


def _screen_text_sentences(shot: Mapping[str, Any], *, path: str) -> list[str]:
    result: list[str] = []
    for index, item in enumerate(_list(shot.get("screen_text")), start=1):
        if not isinstance(item, Mapping):
            continue
        item_path = f"{path}.screen_text[{index}]"
        legibility = str(item.get("legibility") or "")
        text = item.get("text")
        if legibility == "exact":
            if not isinstance(text, str) or not text:
                raise H3DirectorCompileError(f"{item_path} exact text requires a non-empty text value")
            # Original-language visible text is explicitly allowed by H3 and remains verbatim in quotes.
            result.append(f'A visible screen element reads "{text}" clearly.')
        elif legibility == "blurred_unreadable":
            semantic = _english_value(item, "semantic", path=item_path)
            suffix = f" representing {semantic}" if semantic else ""
            result.append(f"A screen element is visible but deliberately unreadable{suffix}.")
        elif legibility == "semantic_only":
            semantic = _english_value(item, "semantic", path=item_path, required=True)
            result.append(
                f"The interface visibly communicates {semantic} without requiring readable text."
            )
    return result


def _shot_sound_sentence(shot: Mapping[str, Any], *, path: str) -> str:
    value = _english_value(shot, "sound", path=path)
    if value:
        return f"Synchronized diegetic sound in this shot includes {value}."
    design = _mapping(shot.get("sound_design"))
    if design:
        value = _english_value(design, "shot_sound", path=f"{path}.sound_design") or _english_value(
            design, "ambience", path=f"{path}.sound_design"
        )
        if value:
            return f"Synchronized diegetic sound in this shot includes {value}."
    return ""


def _dialogue_delivery(
    shot: Mapping[str, Any],
    item: Mapping[str, Any],
    speaker_id: str,
    *,
    path: str,
) -> str:
    direct = _english_value(item, "delivery", path=path)
    if direct:
        return direct
    direction_en = shot.get("dialogue_direction_en")
    if isinstance(direction_en, Mapping):
        value = str(direction_en.get(speaker_id) or "").strip()
        if value:
            if _contains_cjk(value):
                raise H3DirectorCompileError(f"{path}.dialogue_direction_en must be English")
            return value
    elif direction_en:
        value = str(direction_en).strip()
        if _contains_cjk(value):
            raise H3DirectorCompileError(f"{path}.dialogue_direction_en must be English")
        return value

    # If a semantic direction exists only in non-English source form, fail instead of dropping it.
    original = shot.get("dialogue_direction")
    if original not in (None, "", {}, []):
        if isinstance(original, Mapping):
            value = str(original.get(speaker_id) or "").strip()
        else:
            value = str(original).strip()
        if value and _contains_cjk(value):
            raise H3DirectorCompileError(
                f"{path} has non-English dialogue_direction; provide dialogue_direction_en"
            )
        if value:
            return value
    return "a natural speaking voice consistent with the staged performance"


def _continuation_maps(unit: Mapping[str, Any]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    to_next_triples, from_prev_triples = _dialogue_groups(unit)
    to_next = {(shot, speaker) for shot, _next, speaker in to_next_triples}
    from_prev = {(shot, speaker) for shot, _prev, speaker in from_prev_triples}
    return to_next, from_prev


def _dialogue_sentence(
    *,
    unit: Mapping[str, Any],
    shot: Mapping[str, Any],
    item: Mapping[str, Any],
    shot_id: str,
    speaker_map: Mapping[str, str],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
    path: str,
) -> str:
    speaker_id = str(item.get("speaker_id") or "").strip()
    text = str(item.get("text") or "")
    if not speaker_id or not text:
        raise H3DirectorCompileError(f"{path} requires speaker_id and verbatim text")
    sid = speaker_map.get(speaker_id)
    if sid is None:
        raise H3DirectorCompileError(f"dialogue speaker {speaker_id!r} missing from unit-local speaker map")
    subject = _subject_for_entity(speaker_id, registries, references)
    who = f"{subject} ({sid})" if subject else _stable_speaker_description(speaker_id, sid, registries)
    delivery = _dialogue_delivery(shot, item, speaker_id, path=path)

    to_next, from_prev = _continuation_maps(unit)
    continues_to_next = (shot_id, speaker_id) in to_next
    continues_from_prev = (shot_id, speaker_id) in from_prev

    voiceover = bool(item.get("voiceover") or item.get("off_screen_voiceover"))
    if voiceover:
        verb = "says in an off-screen voiceover"
    elif continues_from_prev:
        verb = "continues the same utterance"
    else:
        verb = "says"

    spoken = text
    if continues_from_prev:
        spoken = "<scenetrans>" + spoken
    if continues_to_next:
        spoken = spoken + "<scenetrans>"
    if item.get("cutoff"):
        spoken = spoken + "<cutoff>"

    sentence = f"{who} {verb} in {delivery}: <d>[Chinese] {spoken}</d>"
    if continues_to_next:
        sentence += " The same voice continues seamlessly across the cut without interruption."
    elif voiceover:
        sentence += " The corresponding on-screen character's lips remain completely closed."
    else:
        subject_phrase = subject if subject else "the speaker"
        sentence += f" After the line, {subject_phrase} closes their lips and stops speaking."
    return sentence


def _style_opening(unit: Mapping[str, Any]) -> str:
    notes = _mapping(unit.get("director_notes"))
    value = (
        str(unit.get("h3_style_opening_en") or "").strip()
        or str(notes.get("style_opening_en") or "").strip()
        or "Live-action cinematic drama with naturalistic lighting and restrained camera behavior consistent with each authored shot."
    )
    if _contains_cjk(value):
        raise H3DirectorCompileError("H3 style opening must be English")
    return value


def _continuity_sentences(unit: Mapping[str, Any]) -> list[str]:
    sentences: list[str] = []
    for key, intro in (
        ("scene_anchors", "Stable spatial anchors across the unit:"),
        ("continuity_in", "At the opening, preserve the incoming continuity state:"),
        ("continuity_out", "By the end, establish the outgoing continuity state:"),
    ):
        raw = unit.get(key)
        english = unit.get(f"{key}_en")
        if english not in (None, ""):
            text = str(english).strip()
            if _contains_cjk(text):
                raise H3DirectorCompileError(f"unit.{key}_en must be English")
            sentences.append(f"{intro} {text}.")
        elif raw not in (None, "", {}, []):
            if isinstance(raw, str) and not _contains_cjk(raw):
                sentences.append(f"{intro} {raw.strip()}.")
            else:
                raise H3DirectorCompileError(
                    f"unit.{key} contains structured/non-English continuity semantics; provide unit.{key}_en"
                )
    return sentences


def _role_constraint_sentence(unit: Mapping[str, Any]) -> str:
    clauses: list[str] = []
    if _list(unit.get("depicted_subject_ids")):
        clauses.append(
            "Depicted-only subjects remain inside photographs, screens, posters, or other embedded media and do not become live physical subjects"
        )
    if _list(unit.get("referenced_entity_ids")):
        clauses.append(
            "Referenced-only entities remain mentions or interface/contact states and do not appear as live physical subjects"
        )
    return ". ".join(clauses) + ("." if clauses else "")


def _registry_entity_ids_for_ref(
    ref: DirectorReference,
    registries: Mapping[str, Any],
) -> set[str]:
    matched: set[str] = set()
    target = {ref.source_name.casefold(), ref.label.casefold()}
    for registry_name in ("characters", "props", "objects", "products"):
        registry = _mapping(registries.get(registry_name))
        for entity_id, raw_entry in registry.items():
            candidates = {str(entity_id).casefold()}
            if isinstance(raw_entry, str):
                candidates.add(raw_entry.casefold())
            elif isinstance(raw_entry, Mapping):
                for key in ("name", "name_en", "label", "label_en"):
                    value = raw_entry.get(key)
                    if value:
                        candidates.add(str(value).casefold())
            if target & candidates:
                matched.add(str(entity_id))
    return matched


def _unit_scene_names(unit: Mapping[str, Any], registries: Mapping[str, Any]) -> set[str]:
    scene_id = str(unit.get("scene_id") or "").strip()
    names = {scene_id.casefold()} if scene_id else set()
    raw = _mapping(registries.get("scenes")).get(scene_id)
    if isinstance(raw, str):
        names.add(raw.casefold())
    elif isinstance(raw, Mapping):
        for key in ("name", "name_en", "label", "label_en"):
            value = raw.get(key)
            if value:
                names.add(str(value).casefold())
    return names


def _shot_entity_ids(shot: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key, value in shot.items():
        if key.endswith("_ids"):
            ids.update(str(item) for item in _list(value))
    ids.update(
        str(item.get("speaker_id"))
        for item in _list(shot.get("dialogue"))
        if isinstance(item, Mapping) and item.get("speaker_id")
    )
    return ids


def _reference_appears_in_shot(
    ref: DirectorReference,
    *,
    shot: Mapping[str, Any],
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
) -> bool:
    if ref.kind == "style":
        return True
    if ref.kind == "scene":
        target = {ref.source_name.casefold(), ref.label.casefold()}
        return bool(target & _unit_scene_names(unit, registries))
    entity_ids = _registry_entity_ids_for_ref(ref, registries)
    if entity_ids:
        return bool(entity_ids & _shot_entity_ids(shot))
    return False


def _reference_presence_sentences(
    *,
    shot_index: int,
    shot: Mapping[str, Any],
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> list[str]:
    del shot_index  # reserved for future diagnostics while keeping call sites explicit
    result: list[str] = []
    depicted = {str(x) for x in _list(shot.get("depicted_subject_ids"))}
    active = {str(x) for x in _list(shot.get("active_subject_ids"))}
    for primary, group in _group_director_references(references):
        if not any(
            _reference_appears_in_shot(
                item, shot=shot, unit=unit, registries=registries
            )
            for item in group
        ):
            continue
        if primary.kind == "scene":
            result.append(
                f"The shot takes place within {primary.subject}, using the referenced environment as the visible setting."
            )
        elif primary.kind == "character":
            entity_ids = set().union(
                *(_registry_entity_ids_for_ref(item, registries) for item in group)
            )
            if entity_ids & depicted and not entity_ids & active:
                result.append(
                    f"{primary.subject} appears only within embedded media in this shot, retaining the referenced identity and appearance."
                )
            else:
                result.append(
                    f"{primary.subject} is visibly present in this shot, retaining the referenced identity and appearance."
                )
        elif primary.kind in {"object", "prop", "product"}:
            result.append(
                f"{primary.subject} is visibly present as the referenced object in this shot."
            )
        elif primary.kind == "style":
            result.append(f"The visual treatment in this shot follows {primary.subject}.")
        else:
            result.append(
                f"{primary.subject} is visibly applied in this shot according to its reference definition."
            )
    return result


def _shot_paragraphs(
    *,
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> list[str]:
    shots = [x for x in _list(unit.get("shots")) if isinstance(x, Mapping)]
    if not shots:
        raise H3DirectorCompileError("canonical director unit requires non-empty shots")
    speaker_map = _speaker_map(unit)
    paragraphs: list[str] = []

    for index, shot in enumerate(shots, start=1):
        shot_id = str(shot.get("shot_id") or f"Shot-{index}")
        path = f"unit.shots[{index - 1}]"
        start = float(shot.get("start_sec") or 0)
        if index == 1:
            if abs(start) > 1e-6:
                raise H3DirectorCompileError("first canonical shot must start at 0")
            header = "[Shot 1]"
        else:
            header = f"[Shot {index}] At {_format_ts(start)},"

        parts: list[str] = []
        if index > 1:
            transition_value = shot.get("transition_in")
            transition_path = f"{path}.transition_in"
            if transition_value in (None, "", {}, []):
                previous_shot = shots[index - 2]
                transition_value = previous_shot.get("transition_out")
                transition_path = f"unit.shots[{index - 2}].transition_out"
            transition = _transition_phrase(transition_value, path=transition_path)
            if transition:
                parts.append(transition.capitalize() + ".")
            else:
                parts.append("The shot cuts to the next authored view.")

        parts.extend(
            _reference_presence_sentences(
                shot_index=index,
                shot=shot,
                unit=unit,
                registries=registries,
                references=references,
            )
        )
        parts.extend(_visual_language_sentences(shot, path=path))

        action = _english_value(shot, "action", path=path)
        if action:
            parts.append(action if action.endswith((".", "!", "?")) else action + ".")

        parts.append(_camera_sentence(shot))

        emotion = _english_value(shot, "emotion_motion", path=path)
        if emotion:
            parts.append(
                f"The visible performance changes through {emotion}."
            )

        parts.extend(_screen_text_sentences(shot, path=path))

        sound = _shot_sound_sentence(shot, path=path)
        if sound:
            parts.append(sound)

        for dialogue_index, item in enumerate(_list(shot.get("dialogue")), start=1):
            if not isinstance(item, Mapping):
                continue
            parts.append(
                _dialogue_sentence(
                    unit=unit,
                    shot=shot,
                    item=item,
                    shot_id=shot_id,
                    speaker_map=speaker_map,
                    registries=registries,
                    references=references,
                    path=f"{path}.dialogue[{dialogue_index - 1}]",
                )
            )

        # Transition semantics are rendered once at the beginning of the next shot,
        # matching the official playback-order examples and avoiding duplicate boundary instructions.

        # Keep each H3 shot as one readable playback-order paragraph, matching the
        # official examples rather than a stack of pseudo-field labels.
        paragraphs.append(header + " " + " ".join(x.strip() for x in parts if x.strip()))
    return paragraphs


def _reference_appearance(
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    ref: DirectorReference,
) -> list[int]:
    shots = [x for x in _list(unit.get("shots")) if isinstance(x, Mapping)]
    return [
        index
        for index, shot in enumerate(shots, start=1)
        if _reference_appears_in_shot(
            ref, shot=shot, unit=unit, registries=registries
        )
    ]


def _retention_analysis(
    unit: Mapping[str, Any],
    registries: Mapping[str, Any],
    references: Sequence[DirectorReference],
) -> str:
    lines: list[str] = []
    for ref, group in _group_director_references(references):
        appearances = sorted({
            shot_index
            for item in group
            for shot_index in _reference_appearance(unit, registries, item)
        })
        if not appearances:
            raise H3DirectorCompileError(
                f"{ref.subject} is backed by provider reference image(s) but is not bound to any target shot; "
                "fix Canonical shot subject/prop/scene bindings before H3 submission"
            )
        where = "appears in " + ", ".join(f"[Shot {index}]" for index in appearances)
        if ref.kind == "scene":
            details = "the referenced environment, layout, architecture, and stable spatial anchors are retained."
        elif ref.kind == "character":
            details = "the referenced identity, face, hairstyle, costume, proportions, and stable appearance are retained."
        elif ref.kind in {"object", "prop", "product"}:
            details = "the referenced shape, material, proportions, and identifying visual details are retained."
        elif ref.kind == "style":
            details = "the referenced palette, texture, lighting treatment, and rendering characteristics are retained."
        else:
            details = "the referenced subject identity and defining visual attributes are retained."
        lines.append(f"{ref.subject} ({where}): fully_preserved - {details}")
    return "\n".join(lines)


def _overall_soundscape(unit: Mapping[str, Any]) -> str:
    design = _mapping(unit.get("sound_design"))
    notes = _mapping(unit.get("director_notes"))
    for owner, path in ((design, "unit.sound_design"), (notes, "unit.director_notes")):
        if owner.get("ambience_en") not in (None, ""):
            value = str(owner.get("ambience_en")).strip()
            if _contains_cjk(value):
                raise H3DirectorCompileError(f"{path}.ambience_en must be English")
            return value
        if owner.get("ambience") not in (None, ""):
            value = str(owner.get("ambience")).strip()
            if value.lower() in _SILENCE_SENTINELS:
                return "N/A"
            if _contains_cjk(value):
                raise H3DirectorCompileError(
                    f"{path}.ambience contains non-English prose; provide ambience_en"
                )
            return value

    shot_sounds: list[str] = []
    for index, shot in enumerate(_list(unit.get("shots")), start=1):
        if not isinstance(shot, Mapping):
            continue
        sound = _shot_sound_sentence(shot, path=f"unit.shots[{index - 1}]")
        if sound:
            shot_sounds.append(sound)
    if shot_sounds:
        return " ".join(shot_sounds)
    raise H3DirectorCompileError(
        "strict H3 native compilation requires English overall soundscape semantics; provide "
        "unit.sound_design.ambience_en (or explicit N/A only for complete silence)"
    )


def _non_diegetic_music(unit: Mapping[str, Any]) -> str:
    design = _mapping(unit.get("sound_design"))
    notes = _mapping(unit.get("director_notes"))
    for owner, path in ((design, "unit.sound_design"), (notes, "unit.director_notes")):
        raw = owner.get("music_en")
        if raw in (None, ""):
            raw = owner.get("music")
        if raw in (None, ""):
            continue
        value = str(raw).strip()
        if value.lower() in _NO_MUSIC_SENTINELS or value in _NO_MUSIC_SENTINELS:
            return "N/A"
        if _contains_cjk(value):
            raise H3DirectorCompileError(
                f"{path}.music contains non-English prose; provide music_en or explicit no-music sentinel"
            )
        return value
    return "N/A"


def _legacy_inline_body(text: str) -> str:
    speaker_ids: dict[str, str] = {}

    def dialogue_repl(match: re.Match[str]) -> str:
        speaker = match.group("speaker").strip()
        sid = speaker_ids.setdefault(speaker, f"S{len(speaker_ids) + 1}")
        # Names outside <d> must be English in native H3 output.  Keep them for the
        # validator to reject if authoring has not yet been rewritten.
        dialogue = match.group("text")
        return (
            f"The on-screen speaker {speaker} ({sid}) says in a natural speaking voice: "
            f"<d>[Chinese] {dialogue}</d> After the line, the speaker closes their lips and stops speaking."
        )

    rendered = _LEGACY_DIALOGUE_RE.sub(dialogue_repl, text)
    rendered = _LEGACY_MENTION_RE.sub(lambda m: m.group("name").strip(), rendered)
    return rendered.strip()


def _extract_english_sound_lines(text: str) -> tuple[str, str]:
    body: list[str] = []
    sounds: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:Sound|Audio):\s*(.+)$", stripped, re.IGNORECASE)
        if match:
            sounds.append(match.group(1).strip())
        else:
            body.append(line)
    return "\n".join(body), " ".join(sounds).strip()


def compile_h3_text_t2va_prompt(
    *,
    source_prompt: str,
    duration_seconds: int,
    overall_soundscape: str = "",
    non_diegetic_music: str = "N/A",
    max_prompt_chars: int = H3_DEFAULT_MAX_PROMPT_CHARS,
) -> str:
    """Compile/validate free-form text as native H3 T2VA.

    Strict native T2VA is the official three-field format; the previous ArcReel
    six-section pseudo-T2VA format is intentionally rejected.
    """
    if not source_prompt or not source_prompt.strip():
        raise H3DirectorCompileError("source_prompt must not be blank")
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        raise H3DirectorCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; got {duration}s"
        )

    names = [match.group(1) for match in _BASE_SECTION_RE.finditer(source_prompt)]
    if names == ["integrated_multimodal_description", "overall_soundscape", "non_diegetic_music"]:
        try:
            prompt = validate_h3_native_t2va_prompt(source_prompt, duration_seconds=duration)
        except ValueError as exc:
            raise H3DirectorCompileError(str(exc)) from exc
    elif _REF_SECTION_RE.search(source_prompt):
        raise H3DirectorCompileError(
            "T2VA must use the official three-field H3 base format, not Ref2VA's six-section format"
        )
    else:
        body = _legacy_inline_body(source_prompt)
        body, extracted_sound = _extract_english_sound_lines(body)
        if _CJK_RE.search(re.sub(r"<d>.*?</d>", "", body, flags=re.DOTALL)):
            raise H3DirectorCompileError(
                "free-form T2VA contains non-English execution prose; rewrite the visual/camera/action/sound "
                "description in English before provider submission"
            )
        if not re.search(r"(?m)^\[Shot\s+1\]", body):
            body = f"[Shot 1] Live-action, cinematic, {body}"
        soundscape = overall_soundscape.strip() or extracted_sound
        if not soundscape:
            raise H3DirectorCompileError(
                "strict H3 T2VA requires an English overall_soundscape; use N/A only for explicit complete silence"
            )
        if _contains_cjk(soundscape):
            raise H3DirectorCompileError("overall_soundscape must be English")
        music = non_diegetic_music.strip() or "N/A"
        if _contains_cjk(music):
            raise H3DirectorCompileError("non_diegetic_music must be English")
        prompt = "\n\n".join(
            [
                f"integrated_multimodal_description: {body}",
                f"overall_soundscape: {soundscape}",
                f"non_diegetic_music: {music}",
            ]
        )
        try:
            prompt = validate_h3_native_t2va_prompt(prompt, duration_seconds=duration)
        except ValueError as exc:
            raise H3DirectorCompileError(str(exc)) from exc

    if len(prompt) > int(max_prompt_chars):
        raise H3DirectorCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {max_prompt_chars}"
        )
    return prompt


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
    """Compile Canonical Director data into a strict native H3 execution prompt."""
    duration = int(duration_seconds)
    if not H3_MIN_DURATION_SECONDS <= duration <= H3_MAX_DURATION_SECONDS:
        raise H3DirectorCompileError(
            f"H3 prompt duration must be {H3_MIN_DURATION_SECONDS}-{H3_MAX_DURATION_SECONDS}s; got {duration}s"
        )
    bundle = CanonicalDirectorBundle.resolve(canonical_director, unit_id=unit_id)
    unit = bundle.unit
    registries = bundle.registries

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

    shot_paragraphs = _shot_paragraphs(unit=unit, registries=registries, references=refs)
    role_constraint = _role_constraint_sentence(unit)
    continuity = _continuity_sentences(unit)
    opening = _style_opening(unit)
    ambience = _overall_soundscape(unit)
    music = _non_diegetic_music(unit)

    if refs:
        detailed_parts = [opening]
        if role_constraint:
            detailed_parts.append(role_constraint)
        detailed_parts.extend(continuity)
        detailed_parts.extend(shot_paragraphs)
        subject_definitions = _subject_definitions(refs)
        summary = (
            f"[reference generation] The {duration}-second target video uses "
            + ", ".join(primary.subject for primary, _group in _group_director_references(refs))
            + " as visual references and follows the authored multi-shot timing, staging, camera movement, "
              "visible text, sound, and vocal events."
        )
        retention = _retention_analysis(unit, registries, refs)
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
                "\n".join(detailed_parts),
                "",
                "overall_soundscape:",
                ambience,
                "",
                "non_diegetic_music:",
                music,
            ]
        ).strip()
        try:
            prompt = validate_h3_native_ref2va_prompt(
                prompt,
                duration_seconds=duration,
                reference_count=len(refs),
            )
        except ValueError as exc:
            raise H3DirectorCompileError(str(exc)) from exc
    else:
        integrated_parts: list[str] = []
        for index, paragraph in enumerate(shot_paragraphs):
            if index == 0:
                # The official base guide places overall style at the beginning of Shot 1.
                prefix_parts = [opening]
                if role_constraint:
                    prefix_parts.append(role_constraint)
                prefix_parts.extend(continuity)
                paragraph = paragraph.replace(
                    "[Shot 1] ", f"[Shot 1] {' '.join(prefix_parts)} ", 1
                )
            integrated_parts.append(paragraph)
        prompt = "\n\n".join(
            [
                "integrated_multimodal_description: " + " ".join(integrated_parts),
                "overall_soundscape: " + ambience,
                "non_diegetic_music: " + music,
            ]
        ).strip()
        try:
            prompt = validate_h3_native_t2va_prompt(prompt, duration_seconds=duration)
        except ValueError as exc:
            raise H3DirectorCompileError(str(exc)) from exc

    if len(prompt) > int(max_prompt_chars):
        raise H3DirectorCompileError(
            f"compiled H3 prompt is {len(prompt)} characters; limit is {max_prompt_chars}"
        )
    return prompt, mode