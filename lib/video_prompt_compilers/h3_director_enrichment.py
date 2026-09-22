from __future__ import annotations

"""Rich Canonical Director field rendering for MiniMax H3.

This file is an additive companion to ArcReel's V6 ``h3_director_compiler.py``.
It renders Canonical Shot IR facts that V6 accepted in the payload but did not consume:
framing, angle, composition, DoF, lighting, color grade, subject staging/costume,
environment/props, continuity, transition, visual style/quality, negative constraints,
SFX/diegetic sound, and dialogue offscreen/cutoff state.

The helper is stdlib-only and backwards compatible: absent fields emit no text.
"""

from collections.abc import Mapping, Sequence
from typing import Any


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _text(value: object) -> str:
    return str(value or "").strip()


def _label(value: object) -> str:
    data = _mapping(value)
    return _text(data.get("label") or data.get("name") or data.get("id"))


def _short_list(values: object, *, limit: int = 5) -> str:
    items: list[str] = []
    for value in _list(values):
        cleaned = _text(value)
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return ", ".join(items)


def shot_setup_lines(shot: Mapping[str, Any]) -> list[str]:
    """Render stable visual setup before action/camera/performance lines."""
    lines: list[str] = []

    framing = _label(shot.get("framing"))
    angle = _label(shot.get("angle"))
    composition = _label(shot.get("composition"))
    depth = _text(shot.get("depth_of_field"))
    lens_family = _text(shot.get("lens_family"))
    setup = [
        f"framing {framing}" if framing else "",
        f"angle {angle}" if angle else "",
        f"composition {composition}" if composition else "",
        lens_family + " lens family" if lens_family else "",
        depth,
    ]
    setup = [x for x in setup if x]
    if setup:
        lines.append("Visual setup: " + "; ".join(setup) + ".")

    lighting = _mapping(shot.get("lighting"))
    light_parts = [
        _label(lighting.get("direction")),
        _label(lighting.get("ratio")),
        _label(lighting.get("color_temperature")),
        _text(lighting.get("notes")),
    ]
    light_parts = [x for x in light_parts if x]
    if light_parts:
        lines.append("Lighting: " + "; ".join(light_parts) + ".")

    grade = _label(shot.get("color_grade"))
    if grade:
        lines.append(f"Color grade: {grade}.")

    environment = _mapping(shot.get("environment"))
    env_parts: list[str] = []
    scene_name = _text(environment.get("scene_name"))
    zone = _text(environment.get("zone_id"))
    if scene_name:
        env_parts.append(scene_name + (f" / {zone}" if zone else ""))
    time_of_day = _text(environment.get("time_of_day"))
    weather = _text(environment.get("weather"))
    if time_of_day:
        env_parts.append(time_of_day)
    if weather:
        env_parts.append(weather)
    anchors = _short_list(environment.get("environment_anchors"), limit=5)
    if anchors:
        env_parts.append("anchors: " + anchors)
    props = _short_list(shot.get("props"), limit=6)
    if props:
        env_parts.append("visible props: " + props)
    if env_parts:
        lines.append("Environment: " + "; ".join(env_parts) + ".")

    subject_lines: list[str] = []
    for state in _list(shot.get("subject_states")):
        if not isinstance(state, Mapping):
            continue
        name = _text(state.get("name") or state.get("subject_id"))
        bits: list[str] = []
        position = _text(state.get("position"))
        costume = _text(state.get("costume_variant"))
        facial = _text(state.get("facial_expression"))
        body = _text(state.get("body_language"))
        anchors = _short_list(state.get("appearance_anchors"), limit=4)
        if position:
            bits.append(position)
        if costume:
            bits.append("costume " + costume)
        if anchors:
            bits.append("identity anchors: " + anchors)
        if facial:
            bits.append("face: " + facial)
        if body:
            bits.append("body: " + body)
        if name and bits:
            subject_lines.append(name + " — " + "; ".join(bits))
    if subject_lines:
        lines.append("Subject staging: " + " | ".join(subject_lines) + ".")

    style = _text(shot.get("visual_style"))
    quality = _short_list(shot.get("quality_terms"), limit=6)
    if style or quality:
        pieces = []
        if style:
            pieces.append(style)
        if quality:
            pieces.append("quality: " + quality)
        lines.append("Visual style: " + "; ".join(pieces) + ".")

    return lines


def _continuity_line(shot: Mapping[str, Any]) -> str:
    continuity = _mapping(shot.get("continuity_in"))
    previous_id = _text(continuity.get("previous_shot_id"))
    state = _mapping(continuity.get("state"))
    if not previous_id or not state:
        return ""

    previous_scene = _mapping(state.get("scene"))
    current_scene = _mapping(shot.get("environment"))
    previous_scene_id = _text(previous_scene.get("scene_id"))
    current_scene_id = _text(current_scene.get("scene_id"))
    parts = [f"enter from {previous_id}"]
    if previous_scene_id and current_scene_id:
        if previous_scene_id == current_scene_id:
            parts.append(f"keep scene {current_scene_id} spatially continuous")
        else:
            parts.append(f"scene boundary {previous_scene_id} -> {current_scene_id}; do not carry the old layout")

    previous_subjects = {
        _text(item.get("subject_id")): item
        for item in _list(state.get("subjects"))
        if isinstance(item, Mapping) and _text(item.get("subject_id"))
    }
    current_subjects = {
        _text(item.get("subject_id")): item
        for item in _list(shot.get("subject_states"))
        if isinstance(item, Mapping) and _text(item.get("subject_id"))
    }
    locks: list[str] = []
    for sid in sorted(set(previous_subjects) & set(current_subjects)):
        prev = previous_subjects[sid]
        cur = current_subjects[sid]
        name = _text(cur.get("name") or sid)
        prev_costume = _text(prev.get("costume_variant"))
        cur_costume = _text(cur.get("costume_variant"))
        if prev_costume and cur_costume and prev_costume == cur_costume:
            locks.append(f"{name} stays in {cur_costume}")
        else:
            locks.append(f"preserve {name} identity")
    if locks:
        parts.append(", ".join(locks[:4]))

    return "Continuity: " + "; ".join(parts) + "."


def _transition_line(shot: Mapping[str, Any], unit: Mapping[str, Any]) -> str:
    transition = _mapping(shot.get("transition_to_next")) or _mapping(unit.get("transition_to_next"))
    if not transition:
        return ""
    name = _text(transition.get("name") or transition.get("type") or transition.get("type_id"))
    medium = _text(transition.get("medium") or transition.get("note"))
    target = _text(transition.get("target_scene") or transition.get("target"))
    parts = [x for x in (name, medium, f"target {target}" if target else "") if x]
    return "Transition to next unit: " + "; ".join(parts) + "." if parts else ""


def _negative_constraint_line(shot: Mapping[str, Any]) -> str:
    policy = _mapping(shot.get("negative_constraints"))
    if not policy:
        return ""
    parts: list[str] = []
    has_explicit_text = bool(_list(shot.get("screen_text")))
    if policy.get("allow_visible_text") is False:
        if has_explicit_text:
            parts.append("no incidental readable text beyond the explicitly declared screen text")
        else:
            parts.append("no readable text, subtitles, logos, or watermarks")
    if policy.get("allow_expressionless") is False:
        parts.append("avoid expressionless faces when a performance beat is specified")
    if policy.get("allow_flat_lighting") is False:
        parts.append("avoid flat lighting; preserve the declared lighting design")
    forbid = _short_list(policy.get("extra_forbid"), limit=8)
    if forbid:
        parts.append("forbid: " + forbid)
    allow = _short_list(policy.get("extra_allow"), limit=5)
    if allow:
        parts.append("explicitly allowed: " + allow)
    return "Constraints: " + "; ".join(parts) + "." if parts else ""


def shot_post_lines(shot: Mapping[str, Any], unit: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    continuity = _continuity_line(shot)
    if continuity:
        lines.append(continuity)
    transition = _transition_line(shot, unit)
    if transition:
        lines.append(transition)
    negative = _negative_constraint_line(shot)
    if negative:
        lines.append(negative)
    return lines


def enrich_dialogue_delivery(item: Mapping[str, Any], delivery: str) -> str:
    """Append source-authored speech state without changing dialogue text."""
    notes: list[str] = []
    if bool(item.get("offscreen")):
        notes.append("offscreen voice; do not lip-sync an on-screen character")
    if bool(item.get("cross_cut")):
        notes.append("continues across the cut")
    if bool(item.get("cutoff")):
        notes.append("cut off naturally at the authored endpoint")
    base = delivery.strip()
    if not notes:
        return base
    suffix = "; ".join(notes)
    return f"{base}; {suffix}" if base else suffix


def enrich_overall_soundscape(sound_design: Mapping[str, Any], ambience: str) -> str:
    parts: list[str] = []
    if ambience.strip() and ambience.strip() != "N/A":
        parts.append(ambience.strip())
    sfx = _short_list(sound_design.get("sfx"), limit=10)
    if sfx:
        parts.append("SFX: " + sfx)
    diegetic = _short_list(sound_design.get("diegetic_music"), limit=6)
    if diegetic:
        parts.append("Diegetic sound/music: " + diegetic)
    return "; ".join(parts) if parts else "N/A"
