"""Shared MiniMax H3 production policy learned from the six golden supplier units.

This module deliberately contains no unit-specific branches. The six accepted units
exercise generic invariants that every future H3 unit can use through Canonical
Director IR and Media-QA issue codes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class H3ProductionPolicyError(ValueError):
    """A free, deterministic pre-provider production-policy failure."""


class MediaIssueCode(StrEnum):
    EXACT_TEXT_MISSING_OR_WRONG = "exact_text_missing_or_wrong"
    NONCANONICAL_VISIBLE_TEXT = "noncanonical_visible_text"
    LOCAL_UI_TEXT_CONTAMINATION = "local_ui_text_contamination"
    SHOT_TIMELINE_DRIFT = "shot_timeline_drift"
    AUDIO_TIMELINE_DRIFT = "audio_timeline_drift"
    IDENTITY_DRIFT = "identity_drift"
    ACTION_OR_STAGING_DRIFT = "action_or_staging_drift"
    SCENE_OR_COMPOSITION_DRIFT = "scene_or_composition_drift"


class RepairAction(StrEnum):
    DETERMINISTIC_TEXT_PLATE = "deterministic_text_plate"
    DETERMINISTIC_PIXEL_SANITIZATION = "deterministic_pixel_sanitization"
    DETERMINISTIC_AV_RETIME = "deterministic_av_retime"
    REGENERATE_SHOT = "regenerate_shot"
    REJECT_OR_ESCALATE = "reject_or_escalate"


@dataclass(frozen=True)
class H3CanonicalPolicyFacts:
    unit_id: str
    duration_seconds: float
    shot_count: int
    exact_visible_text: tuple[str, ...]
    dialogue_text: tuple[str, ...]
    active_subject_ids: tuple[str, ...]
    depicted_subject_ids: tuple[str, ...]
    referenced_entity_ids: tuple[str, ...]


def _sequence(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _string_ids(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if str(item))


def validate_h3_canonical_unit(
    unit: Mapping[str, Any],
    *,
    provider_duration_seconds: int | float,
) -> H3CanonicalPolicyFacts:
    """Validate generic Canonical facts before any paid H3 provider call."""

    unit_id = str(unit.get("unit_id") or "").strip()
    duration = float(provider_duration_seconds)
    if duration <= 0:
        raise H3ProductionPolicyError("provider duration must be positive")

    shots = [item for item in _sequence(unit.get("shots")) if isinstance(item, Mapping)]
    if not shots:
        raise H3ProductionPolicyError("canonical H3 unit requires at least one shot")

    exact_visible_text: list[str] = []
    dialogue_text: list[str] = []
    cursor = 0.0

    for index, shot in enumerate(shots, start=1):
        shot_id = str(shot.get("shot_id") or f"shot-{index}")
        try:
            start = float(shot.get("start_sec"))
            end = float(shot.get("end_sec"))
        except (TypeError, ValueError) as exc:
            raise H3ProductionPolicyError(
                f"{shot_id}: start_sec/end_sec must be numeric"
            ) from exc

        if abs(start - cursor) > 1e-6:
            raise H3ProductionPolicyError(
                f"{shot_id}: shot timeline must be contiguous; expected start {cursor:g}, got {start:g}"
            )
        if end <= start:
            raise H3ProductionPolicyError(f"{shot_id}: shot end must be greater than start")

        declared = shot.get("duration_sec")
        if isinstance(declared, (int, float)) and not isinstance(declared, bool):
            if abs(float(declared) - (end - start)) > 1e-6:
                raise H3ProductionPolicyError(
                    f"{shot_id}: duration_sec does not match start_sec/end_sec"
                )
        cursor = end

        for screen in _sequence(shot.get("screen_text")):
            if not isinstance(screen, Mapping):
                continue
            legibility = str(screen.get("legibility") or "").strip()
            literal = screen.get("text")
            if legibility == "exact":
                if not isinstance(literal, str) or not literal:
                    raise H3ProductionPolicyError(
                        f"{shot_id}: exact screen text requires a non-empty literal"
                    )
                exact_visible_text.append(literal)
            elif literal not in (None, ""):
                raise H3ProductionPolicyError(
                    f"{shot_id}: only exact screen text may carry literal text; "
                    f"{legibility or 'unspecified'} must be semantic-only"
                )

        for dialogue in _sequence(shot.get("dialogue")):
            if not isinstance(dialogue, Mapping):
                continue
            literal = dialogue.get("text")
            if isinstance(literal, str) and literal:
                dialogue_text.append(literal)

    if abs(cursor - duration) > 1e-6:
        raise H3ProductionPolicyError(
            f"canonical shot timeline ends at {cursor:g}s but provider duration is {duration:g}s"
        )

    active = _string_ids(unit.get("active_subject_ids"))
    depicted = _string_ids(unit.get("depicted_subject_ids"))
    referenced = _string_ids(unit.get("referenced_entity_ids"))
    roles = {
        "active": set(active),
        "depicted": set(depicted),
        "referenced": set(referenced),
    }
    for left, right in (("active", "depicted"), ("active", "referenced"), ("depicted", "referenced")):
        overlap = roles[left] & roles[right]
        if overlap:
            raise H3ProductionPolicyError(
                f"entity roles must be disjoint; {left}/{right} overlap: {sorted(overlap)!r}"
            )

    return H3CanonicalPolicyFacts(
        unit_id=unit_id,
        duration_seconds=duration,
        shot_count=len(shots),
        exact_visible_text=tuple(exact_visible_text),
        dialogue_text=tuple(dialogue_text),
        active_subject_ids=active,
        depicted_subject_ids=depicted,
        referenced_entity_ids=referenced,
    )


def plan_h3_media_repair(
    issues: Sequence[MediaIssueCode | str],
) -> RepairAction:
    """Choose the least-destructive repair covering the observed media failure."""

    normalized = {MediaIssueCode(str(issue)) for issue in issues}
    if not normalized:
        raise H3ProductionPolicyError("repair planning requires at least one media issue")

    semantic = {
        MediaIssueCode.IDENTITY_DRIFT,
        MediaIssueCode.ACTION_OR_STAGING_DRIFT,
        MediaIssueCode.SCENE_OR_COMPOSITION_DRIFT,
    }
    if normalized & semantic:
        return RepairAction.REGENERATE_SHOT

    timeline = {
        MediaIssueCode.SHOT_TIMELINE_DRIFT,
        MediaIssueCode.AUDIO_TIMELINE_DRIFT,
    }
    if normalized <= timeline:
        return RepairAction.DETERMINISTIC_AV_RETIME

    text_contamination = {
        MediaIssueCode.NONCANONICAL_VISIBLE_TEXT,
        MediaIssueCode.LOCAL_UI_TEXT_CONTAMINATION,
    }
    if normalized <= text_contamination:
        return RepairAction.DETERMINISTIC_PIXEL_SANITIZATION

    if normalized == {MediaIssueCode.EXACT_TEXT_MISSING_OR_WRONG}:
        return RepairAction.DETERMINISTIC_TEXT_PLATE

    return RepairAction.REJECT_OR_ESCALATE
