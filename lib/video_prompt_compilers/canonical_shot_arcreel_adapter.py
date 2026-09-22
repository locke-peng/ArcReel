"""Canonical Shot IR -> ArcReel request-scoped canonical_director adapter.

The adapter is deterministic and provider-neutral at the input boundary. Canonical
Shot IR remains the fact source. The output shape is consumed by
lib.video_prompt_compilers.h3_director_compiler.

It does not persist project/script files and never fabricates physical reference
images. ArcReel still resolves provider references from persisted @[name] mentions.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

ADAPTER_VERSION = "1.0.0"

_SHOT_ID_RE = re.compile(r"^E(?P<episode>\d{2})S(?P<shot>\d{2})$")
_LOCATION_RE = re.compile(r"^(?P<scene_id>S\d+)\s+(?P<name>.+?)(?:\s*/\s*(?P<zone>Z\d+))?$")
_NOTE_COSTUME_RE = re.compile(r"^costume_stage_(?P<character>C\d+)=(?P<variant>.+)$")
_COSTUME_RE = re.compile(
    r"\b(W\d+|M\d+|K\d+|SW\d+|J\d+|FZ\d+|CY\d+|CZL\d+|LT\d+|SS\d+|GHS\d+|TC\d+|HOST\d+|TEACH\d+)\b"
)

_CAMERA_MOVEMENT_MAP: dict[str, tuple[str, str]] = {
    "static": ("static", "none"),
    "push_in": ("push_in", "forward"),
    "pull_out": ("pull_out", "backward"),
    "tracking": ("tracking", "follow_subject"),
    "follow": ("tracking", "follow_subject"),
}


@dataclass(frozen=True)
class AdapterIssue:
    code: str
    severity: str
    shot_id: str
    field: str
    message: str


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _text(value: object) -> str:
    return str(value or "").strip()


def _unique(values: Sequence[object]) -> list[str]:
    return list(dict.fromkeys(text for value in values if (text := _text(value))))


def _parse_shot_id(shot_id: str) -> tuple[int, int]:
    match = _SHOT_ID_RE.fullmatch(shot_id)
    if match is None:
        raise ValueError(f"unsupported canonical shot id: {shot_id!r}")
    return int(match["episode"]), int(match["shot"])


def arcreel_unit_id(shot_id: str) -> str:
    episode, shot = _parse_shot_id(shot_id)
    return f"E{episode}U{shot:02d}"


def _parse_location(value: object) -> tuple[str, str, str | None]:
    raw = _text(value)
    match = _LOCATION_RE.fullmatch(raw)
    if match is None:
        fallback = raw or "UNKNOWN_SCENE"
        return fallback, fallback, None
    return match["scene_id"], match["name"].strip(), match["zone"]


def _costume_variants(shot: Mapping[str, Any]) -> dict[str, str]:
    variants: dict[str, str] = {}
    for note in _items(shot.get("notes")):
        match = _NOTE_COSTUME_RE.match(_text(note))
        if match is not None:
            variants[match["character"]] = match["variant"].strip()

    for subject in _items(shot.get("subjects")):
        if not isinstance(subject, Mapping):
            continue
        subject_id = _text(subject.get("subject_id"))
        if not subject_id or subject_id in variants:
            continue
        for anchor in _items(subject.get("appearance_anchors")):
            match = _COSTUME_RE.search(_text(anchor))
            if match is not None:
                variants[subject_id] = match[1]
                break
    return variants


def _scene_state(shot: Mapping[str, Any]) -> dict[str, Any]:
    scene = _mapping(shot.get("scene"))
    scene_id, scene_name, zone = _parse_location(scene.get("location"))
    return {
        "scene_id": scene_id,
        "scene_name": scene_name,
        "zone_id": zone,
        "time_of_day": _text(scene.get("time_of_day")) or None,
        "weather": _text(scene.get("weather")) or None,
        "environment_anchors": _unique(_items(scene.get("environment"))),
        "props": _unique(_items(scene.get("props"))),
    }


def _subject_states(shot: Mapping[str, Any]) -> list[dict[str, Any]]:
    variants = _costume_variants(shot)
    states: list[dict[str, Any]] = []
    for subject in _items(shot.get("subjects")):
        if not isinstance(subject, Mapping):
            continue
        subject_id = _text(subject.get("subject_id"))
        name = _text(subject.get("name"))
        variant = variants.get(subject_id)
        states.append(
            {
                "subject_id": subject_id,
                "name": name,
                "position": _text(subject.get("position")) or None,
                "costume_variant": variant,
                "reference_name_hint": f"{name}/{variant}" if name and variant else name or None,
                "appearance_anchors": _unique(_items(subject.get("appearance_anchors"))),
                "facial_expression": _text(subject.get("facial_expression")) or None,
                "body_language": _text(subject.get("body_language")) or None,
            }
        )
    return states


def _continuity_snapshot(shot: Mapping[str, Any]) -> dict[str, Any]:
    scene = _scene_state(shot)
    return {
        "source_shot_id": _text(shot.get("shot_id")),
        "scene": scene,
        "subjects": _subject_states(shot),
        "visible_props": scene["props"],
    }


def _camera_motion(shot: Mapping[str, Any]) -> dict[str, str]:
    camera = _mapping(shot.get("camera"))
    raw = _text(camera.get("movement")) or "static"
    motion_type, direction = _CAMERA_MOVEMENT_MAP.get(raw, (raw, "none"))
    return {
        "type": motion_type,
        "direction": direction,
        "amplitude": _text(camera.get("amplitude")) or "none",
        "speed": _text(camera.get("speed")) or "normal",
        "source_movement": raw,
    }


def _dialogue(shot: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    dialogue: list[dict[str, Any]] = []
    directions: dict[str, str] = {}
    speaker_order: list[str] = []

    for subject in _items(shot.get("subjects")):
        if not isinstance(subject, Mapping):
            continue
        stable_id = _text(subject.get("subject_id"))
        if not stable_id:
            continue
        for item in _items(subject.get("dialogue")):
            if not isinstance(item, Mapping):
                continue
            text = _text(item.get("text"))
            if not text:
                continue
            local_id = _text(item.get("speaker_id"))
            delivery = _text(item.get("delivery"))
            payload = {
                "speaker_id": stable_id,
                "source_local_speaker_id": local_id or None,
                "language": _text(item.get("language")) or "Chinese",
                "text": text,
                "delivery": delivery,
                "offscreen": bool(item.get("offscreen")),
                "cross_cut": bool(item.get("cross_cut")),
                "cutoff": bool(item.get("cutoff")),
            }
            dialogue.append(payload)
            if delivery:
                directions[stable_id] = delivery
            if stable_id not in speaker_order:
                speaker_order.append(stable_id)
    return dialogue, directions, speaker_order


def _action_text(shot: Mapping[str, Any]) -> str:
    actions = [
        f"{name}: {action}" if name else action
        for subject in _items(shot.get("subjects"))
        if isinstance(subject, Mapping)
        and (action := _text(subject.get("action")))
        and (name := _text(subject.get("name"))) is not None
    ]
    return " ; ".join(actions)


def _emotion_text(shot: Mapping[str, Any]) -> str:
    emotion = _mapping(shot.get("emotion"))
    parts: list[str] = []
    primary = _text(emotion.get("primary_id"))
    if primary:
        parts.append(primary)
    secondary = _unique(_items(emotion.get("secondary_ids")))
    if secondary:
        parts.append("secondary: " + ", ".join(secondary))
    visible = _unique(_items(emotion.get("visible_cues")))
    if visible:
        parts.append("visible cues: " + ", ".join(visible))
    for subject in _items(shot.get("subjects")):
        if not isinstance(subject, Mapping):
            continue
        name = _text(subject.get("name"))
        details = ", ".join(
            value
            for value in (
                _text(subject.get("facial_expression")),
                _text(subject.get("body_language")),
            )
            if value
        )
        if details:
            parts.append(f"{name}: {details}" if name else details)
    return " ; ".join(parts)


def _screen_text(shot: Mapping[str, Any], issues: list[AdapterIssue]) -> list[dict[str, str]]:
    scene = _mapping(shot.get("scene"))
    values = _unique(_items(scene.get("visible_text")))
    if not values:
        return []
    negative = _mapping(shot.get("negative_policy"))
    if negative.get("allow_visible_text") is False:
        issues.append(
            AdapterIssue(
                code="IR_VISIBLE_TEXT_NEGATIVE_CONFLICT",
                severity="warning",
                shot_id=_text(shot.get("shot_id")),
                field="scene.visible_text / negative_policy.allow_visible_text",
                message=(
                    "Explicit visible_text exists while allow_visible_text=false; "
                    "adapter preserves explicit text and constrains incidental text only."
                ),
            )
        )
    return [
        {
            "kind": "screen text",
            "legibility": "exact",
            "text": value,
            "semantic": value,
        }
        for value in values
    ]


def _sound_design(shot: Mapping[str, Any]) -> dict[str, Any]:
    audio = _mapping(shot.get("audio"))
    ambience = _unique(_items(audio.get("ambience")))
    return {
        "ambience": "; ".join(ambience) if ambience else "N/A",
        "sfx": _unique(_items(audio.get("sfx"))),
        "diegetic_music": _unique(_items(audio.get("diegetic_music"))),
        "music": _text(audio.get("non_diegetic_music")) or "N/A",
    }


def _lighting(shot: Mapping[str, Any]) -> dict[str, Any]:
    lighting = _mapping(shot.get("lighting"))
    return {
        "direction": dict(_mapping(lighting.get("direction"))),
        "ratio": dict(_mapping(lighting.get("ratio"))),
        "color_temperature": dict(_mapping(lighting.get("color_temperature"))),
        "notes": _text(lighting.get("notes")) or None,
    }


def _negative_constraints(shot: Mapping[str, Any]) -> dict[str, Any]:
    policy = _mapping(shot.get("negative_policy"))
    return {
        "allow_visible_text": bool(policy.get("allow_visible_text", False)),
        "allow_expressionless": bool(policy.get("allow_expressionless", False)),
        "allow_flat_lighting": bool(policy.get("allow_flat_lighting", False)),
        "extra_forbid": _unique(_items(policy.get("extra_forbid"))),
        "extra_allow": _unique(_items(policy.get("extra_allow"))),
    }


def adapt_shot(
    shot: Mapping[str, Any],
    *,
    previous_shot: Mapping[str, Any] | None = None,
    issues: list[AdapterIssue] | None = None,
) -> dict[str, Any]:
    issue_list = issues if issues is not None else []
    shot_id = _text(shot.get("shot_id"))
    _parse_shot_id(shot_id)

    duration = int(shot.get("duration_sec") or 0)
    scene_state = _scene_state(shot)
    dialogue, dialogue_direction, speaker_order = _dialogue(shot)
    subjects = [item for item in _items(shot.get("subjects")) if isinstance(item, Mapping)]
    active_ids = _unique([item.get("subject_id") for item in subjects])

    if len(active_ids) >= 2:
        issue_list.append(
            AdapterIssue(
                code="IR_AXIS_STATE_UNAVAILABLE",
                severity="info",
                shot_id=shot_id,
                field="subjects.position / camera.axis",
                message=(
                    "Multi-subject shot has no explicit left/right screen-side or axis-side fact "
                    "in source IR; adapter does not infer one."
                ),
            )
        )

    lens = _mapping(shot.get("lens"))
    camera = _mapping(shot.get("camera"))
    visual = _mapping(shot.get("visual"))
    transition = shot.get("transition") if isinstance(shot.get("transition"), Mapping) else None

    canonical_shot = {
        "shot_id": shot_id,
        "start_sec": 0,
        "duration_sec": duration,
        "framing": dict(_mapping(shot.get("framing"))),
        "angle": dict(_mapping(shot.get("angle"))),
        "composition": dict(_mapping(shot.get("composition"))),
        "lens_mm": lens.get("focal_length_mm"),
        "lens_family": _text(lens.get("lens_family")) or None,
        "depth_of_field": _text(lens.get("depth_of_field")) or None,
        "camera_position_code": _text(camera.get("position")) or None,
        "camera_motion": _camera_motion(shot),
        "motion_descriptor": dict(_mapping(shot.get("motion"))),
        "lighting": _lighting(shot),
        "color_grade": dict(_mapping(shot.get("color_grade"))),
        "action": _action_text(shot),
        "emotion_motion": _emotion_text(shot),
        "emotion_descriptor": dict(_mapping(shot.get("emotion"))),
        "subject_states": _subject_states(shot),
        "environment": scene_state,
        "props": scene_state["props"],
        "raw_visible_text": _unique(_items(_mapping(shot.get("scene")).get("visible_text"))),
        "screen_text": _screen_text(shot, issue_list),
        "dialogue_direction": dialogue_direction,
        "dialogue": dialogue,
        "continuity_in": {
            "boundary": "episode_start" if previous_shot is None else "adjacent_shot",
            "previous_shot_id": _text(previous_shot.get("shot_id")) if previous_shot else None,
            "state": _continuity_snapshot(previous_shot) if previous_shot is not None else None,
        },
        "continuity_out": _continuity_snapshot(shot),
        "transition_to_next": dict(transition) if transition is not None else None,
        "negative_constraints": _negative_constraints(shot),
        "visual_style": _text(visual.get("style")) or None,
        "quality_terms": _unique(_items(visual.get("quality_terms"))),
        "source_render_notes": _unique(_items(visual.get("render_notes"))),
        "source_schema_version": shot.get("schema_version"),
        "source_order": shot.get("order"),
        "source_global_start_sec": shot.get("start_time_sec"),
        "source_reference_uses": list(_items(shot.get("reference_uses"))),
        "source_notes": list(_items(shot.get("notes"))),
    }

    return {
        "unit_id": arcreel_unit_id(shot_id),
        "source_shot_ids": [shot_id],
        "duration_sec": duration,
        "scene_id": scene_state["scene_id"],
        "scene_variant": scene_state["zone_id"],
        "active_subject_ids": active_ids,
        "depicted_subject_ids": [],
        "referenced_entity_ids": [],
        "continuity_level": "hard",
        "continuity_in": canonical_shot["continuity_in"],
        "continuity_out": canonical_shot["continuity_out"],
        "speaker_semantic_order": speaker_order,
        "cross_shot_dialogue": [],
        "transition_to_next": dict(transition) if transition is not None else None,
        "sound_design": _sound_design(shot),
        "director_notes": {
            "aspect_ratio": _text(visual.get("aspect_ratio")) or None,
            "style": _text(visual.get("style")) or None,
            "quality_terms": _unique(_items(visual.get("quality_terms"))),
            "negative_constraints": _negative_constraints(shot),
        },
        "shots": [canonical_shot],
    }


def _character_registry(
    shots: Sequence[Mapping[str, Any]],
    cast_registry: Mapping[str, Any] | None,
) -> dict[str, Any]:
    cast_by_id = {
        _text(entry.get("character_id")): entry
        for entry in _items(cast_registry.get("entries") if isinstance(cast_registry, Mapping) else None)
        if isinstance(entry, Mapping) and _text(entry.get("character_id"))
    }
    names: dict[str, str] = {}
    for shot in shots:
        for subject in _items(shot.get("subjects")):
            if isinstance(subject, Mapping):
                subject_id = _text(subject.get("subject_id"))
                name = _text(subject.get("name"))
                if subject_id and name:
                    names.setdefault(subject_id, name)

    result: dict[str, Any] = {}
    for subject_id, name in sorted(names.items()):
        base_id = "EX" if subject_id.startswith("EX-") else subject_id
        cast_entry = cast_by_id.get(base_id, {})
        variants = _unique(_items(cast_entry.get("costume_variants"))) if isinstance(cast_entry, Mapping) else []
        result[subject_id] = {
            "name": name,
            "base_character_id": base_id,
            "costume_variants": variants,
        }
    return result


def _scene_registry(shots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for shot in shots:
        state = _scene_state(shot)
        result.setdefault(state["scene_id"], {"name": state["scene_name"]})
    return result


def adapt_document(
    document: Mapping[str, Any],
    *,
    cast_registry: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[AdapterIssue]]:
    shots = sorted(
        [item for item in _items(document.get("shots")) if isinstance(item, Mapping)],
        key=lambda item: int(item.get("order") or 0),
    )
    issues: list[AdapterIssue] = []
    previous_by_episode: dict[int, Mapping[str, Any]] = {}
    units: list[dict[str, Any]] = []

    for shot in shots:
        shot_id = _text(shot.get("shot_id"))
        episode, _ = _parse_shot_id(shot_id)
        units.append(adapt_shot(shot, previous_shot=previous_by_episode.get(episode), issues=issues))
        previous_by_episode[episode] = shot

    return (
        {
            "adapter_version": ADAPTER_VERSION,
            "source_schema_version": document.get("schema_version"),
            "source_project_id": document.get("project_id"),
            "mapping_policy": "one_canonical_shot_per_reference_video_unit",
            "units": units,
            "registries": {
                "characters": _character_registry(shots, cast_registry),
                "scenes": _scene_registry(shots),
            },
        },
        issues,
    )


def select_unit_bundle(bundle: Mapping[str, Any], unit_id: str) -> dict[str, Any]:
    units = [
        unit
        for unit in _items(bundle.get("units"))
        if isinstance(unit, Mapping) and _text(unit.get("unit_id")) == unit_id
    ]
    if len(units) != 1:
        raise ValueError(f"canonical director bundle must contain exactly one {unit_id!r}; found {len(units)}")
    return {
        "unit": dict(units[0]),
        "registries": dict(_mapping(bundle.get("registries"))),
    }


def build_coverage_report(
    document: Mapping[str, Any],
    bundle: Mapping[str, Any],
    issues: Sequence[AdapterIssue],
) -> dict[str, Any]:
    shots = [item for item in _items(document.get("shots")) if isinstance(item, Mapping)]
    units = [item for item in _items(bundle.get("units")) if isinstance(item, Mapping)]
    output_dialogue = [
        item
        for unit in units
        for shot in _items(unit.get("shots"))
        if isinstance(shot, Mapping)
        for item in _items(shot.get("dialogue"))
        if isinstance(item, Mapping)
    ]
    unresolved = [item for item in output_dialogue if _text(item.get("speaker_id")).startswith("S")]
    transitions = sum(1 for shot in shots if isinstance(shot.get("transition"), Mapping))
    visible_text = sum(1 for shot in shots if _items(_mapping(shot.get("scene")).get("visible_text")))
    multi_subject = sum(1 for shot in shots if len(_items(shot.get("subjects"))) >= 2)

    return {
        "adapter_version": ADAPTER_VERSION,
        "source_shot_count": len(shots),
        "output_unit_count": len(units),
        "output_shot_count": sum(len(_items(unit.get("shots"))) for unit in units),
        "facts": {
            "dialogue_lines": len(output_dialogue),
            "unresolved_local_dialogue_speaker_ids": len(unresolved),
            "explicit_transition_shots": transitions,
            "visible_text_shots": visible_text,
            "multi_subject_shots": multi_subject,
            "reference_uses_nonempty_shots": sum(1 for shot in shots if _items(shot.get("reference_uses"))),
        },
        "issue_counts": dict(Counter(issue.code for issue in issues)),
        "severity_counts": dict(Counter(issue.severity for issue in issues)),
        "issues": [asdict(issue) for issue in issues],
    }
