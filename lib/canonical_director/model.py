"""Provider-neutral Canonical Director v1 contract.

This module deliberately knows nothing about Canonical Shot IR source schemas,
ArcReel reference-video projection, provider syntax, files, credentials, or
runtime task state.  It defines only the normalized single-unit director
request fact described by the frozen integration architecture.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

CANONICAL_DIRECTOR_SCHEMA_VERSION = "1.0"
CANONICAL_DIRECTOR_MAX_JSON_BYTES = 65_536
CANONICAL_DIRECTOR_MAX_SHOTS = 16
CANONICAL_DIRECTOR_MAX_SUBJECTS_PER_SHOT = 16
CANONICAL_DIRECTOR_MAX_SPEECH_CUES_PER_SHOT = 16

_UNIT_ID_RE = re.compile(r"^E[1-9]\\d*U\\d+$")
_SHOT_ID_RE = re.compile(r"^E\\d+S\\d+$")

DirectorId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1_024)]
ShotId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64, pattern=r"^E\\d+S\\d+$")]
UnitId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64, pattern=r"^E[1-9]\\d*U\\d+$")]


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class DirectorSourceV1(_ContractModel):
    """Trace-only provenance.  None of these fields can drive ArcReel execution."""

    kind: Literal["canonical_shot_ir"] = "canonical_shot_ir"
    schema_version: ShortText | None = None
    project_id: ShortText | None = None
    shot_ids: tuple[ShotId, ...] = Field(min_length=1, max_length=CANONICAL_DIRECTOR_MAX_SHOTS)

    @model_validator(mode="after")
    def _unique_shot_ids(self) -> "DirectorSourceV1":
        if len(set(self.shot_ids)) != len(self.shot_ids):
            raise ValueError("source.shot_ids must be unique")
        return self


class DirectorTermV1(_ContractModel):
    id: DirectorId | None = None
    label: ShortText


class LensV1(_ContractModel):
    focal_length_mm: float | None = Field(default=None, gt=0, le=2_000)
    family: ShortText | None = None
    depth_of_field: ShortText | None = None


class CameraMotionV1(_ContractModel):
    type: ShortText
    direction: ShortText | None = None
    amplitude: ShortText | None = None
    speed: ShortText | None = None


class CameraV1(_ContractModel):
    position: ShortText | None = None
    motion: CameraMotionV1 | None = None


class LightingV1(_ContractModel):
    direction: DirectorTermV1 | None = None
    ratio: DirectorTermV1 | None = None
    color_temperature: DirectorTermV1 | None = None
    notes: LongText | None = None


class EnvironmentV1(_ContractModel):
    """Canonical semantic environment identity, never an ArcReel file reference."""

    scene_id: DirectorId | None = None
    zone_id: DirectorId | None = None
    time_of_day: ShortText | None = None
    weather: ShortText | None = None
    anchors: tuple[ShortText, ...] = Field(default=(), max_length=16)
    props: tuple[ShortText, ...] = Field(default=(), max_length=32)


class DirectorSubjectV1(_ContractModel):
    """How an already-authored subject is staged/performed, not whether it exists in content."""

    subject_id: DirectorId
    variant_id: DirectorId | None = None
    position: ShortText | None = None
    appearance_anchors: tuple[ShortText, ...] = Field(default=(), max_length=16)
    facial_expression: LongText | None = None
    body_language: LongText | None = None
    gesture: LongText | None = None
    gaze: LongText | None = None
    movement: LongText | None = None


class SpeechPerformanceV1(_ContractModel):
    """Performance-only speech direction.  Spoken wording is intentionally absent."""

    subject_id: DirectorId
    delivery: LongText | None = None
    offscreen: bool = False
    cross_cut: bool = False
    cutoff: bool = False


class ContinuitySubjectStateV1(_ContractModel):
    subject_id: DirectorId
    variant_id: DirectorId | None = None
    position: ShortText | None = None
    state: LongText | None = None


class ContinuityV1(_ContractModel):
    previous_shot_id: ShotId | None = None
    previous_scene_id: DirectorId | None = None
    boundary: ShortText | None = None
    level: Literal["soft", "hard", "locked"] = "hard"
    same_scene: bool | None = None
    subjects: tuple[ContinuitySubjectStateV1, ...] = Field(
        default=(), max_length=CANONICAL_DIRECTOR_MAX_SUBJECTS_PER_SHOT
    )
    visible_props: tuple[ShortText, ...] = Field(default=(), max_length=32)
    notes: tuple[LongText, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def _unique_subjects(self) -> "ContinuityV1":
        ids = [item.subject_id for item in self.subjects]
        if len(set(ids)) != len(ids):
            raise ValueError("continuity.subjects must not contain duplicate subject_id values")
        return self


class VisualTransitionV1(_ContractModel):
    """Visual bridge intent only; ArcReel transition_to_next remains edit-metadata truth."""

    intent: ShortText | None = None
    medium: ShortText | None = None
    target_scene_id: DirectorId | None = None
    notes: tuple[LongText, ...] = Field(default=(), max_length=8)


class SoundDesignV1(_ContractModel):
    ambience: tuple[ShortText, ...] = Field(default=(), max_length=16)
    sfx: tuple[ShortText, ...] = Field(default=(), max_length=32)
    diegetic_music: tuple[ShortText, ...] = Field(default=(), max_length=16)
    music_direction: LongText | None = None


class NegativeConstraintsV1(_ContractModel):
    allow_visible_text: bool | None = None
    allow_expressionless: bool | None = None
    allow_flat_lighting: bool | None = None
    forbid: tuple[ShortText, ...] = Field(default=(), max_length=32)
    allow: tuple[ShortText, ...] = Field(default=(), max_length=16)


class DirectorShotV1(_ContractModel):
    shot_id: ShotId
    start_seconds: float = Field(ge=0, le=3_600)
    duration_seconds: float = Field(gt=0, le=60)

    framing: DirectorTermV1 | None = None
    angle: DirectorTermV1 | None = None
    composition: DirectorTermV1 | None = None
    lens: LensV1 | None = None
    camera: CameraV1 | None = None
    motion: DirectorTermV1 | None = None
    lighting: LightingV1 | None = None
    color_grade: DirectorTermV1 | None = None
    environment: EnvironmentV1 | None = None

    subjects: tuple[DirectorSubjectV1, ...] = Field(default=(), max_length=CANONICAL_DIRECTOR_MAX_SUBJECTS_PER_SHOT)
    speech_performance: tuple[SpeechPerformanceV1, ...] = Field(
        default=(), max_length=CANONICAL_DIRECTOR_MAX_SPEECH_CUES_PER_SHOT
    )
    continuity: ContinuityV1 | None = None
    visual_transition: VisualTransitionV1 | None = None
    sound_design: SoundDesignV1 | None = None
    negative_constraints: NegativeConstraintsV1 | None = None
    visual_style: LongText | None = None
    quality_terms: tuple[ShortText, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def _unique_subject_cues(self) -> "DirectorShotV1":
        subject_ids = [item.subject_id for item in self.subjects]
        if len(set(subject_ids)) != len(subject_ids):
            raise ValueError("shot.subjects must not contain duplicate subject_id values")
        speech_ids = [item.subject_id for item in self.speech_performance]
        if len(set(speech_ids)) != len(speech_ids):
            raise ValueError("shot.speech_performance must not contain duplicate subject_id values")
        return self


class CanonicalDirectorV1(_ContractModel):
    """Normalized, single-ArcReel-unit, provider-neutral director overlay."""

    schema_version: Literal["1.0"] = CANONICAL_DIRECTOR_SCHEMA_VERSION
    unit_id: UnitId
    source: DirectorSourceV1
    timeline_duration_seconds: float = Field(gt=0, le=60)
    shots: tuple[DirectorShotV1, ...] = Field(min_length=1, max_length=CANONICAL_DIRECTOR_MAX_SHOTS)
    sound_design: SoundDesignV1 | None = None
    negative_constraints: NegativeConstraintsV1 | None = None

    @model_validator(mode="after")
    def _validate_contract(self) -> "CanonicalDirectorV1":
        if not _UNIT_ID_RE.fullmatch(self.unit_id):
            raise ValueError("unit_id must match ArcReel reference-video unit syntax")

        shot_ids = [shot.shot_id for shot in self.shots]
        if len(set(shot_ids)) != len(shot_ids):
            raise ValueError("shots must have unique shot_id values")
        if tuple(shot_ids) != self.source.shot_ids:
            raise ValueError("source.shot_ids must exactly match shots in order")

        previous_end = 0.0
        for index, shot in enumerate(self.shots):
            if not _SHOT_ID_RE.fullmatch(shot.shot_id):
                raise ValueError(f"invalid shot_id: {shot.shot_id}")
            if index == 0 and abs(shot.start_seconds) > 1e-6:
                raise ValueError("first director shot must start at 0")
            if shot.start_seconds + 1e-6 < previous_end:
                raise ValueError("director shots must not overlap")
            end = shot.start_seconds + shot.duration_seconds
            if end > self.timeline_duration_seconds + 1e-6:
                raise ValueError("director shot exceeds timeline_duration_seconds")
            previous_end = end

        encoded = _compact_json_bytes(self.model_dump(mode="json", exclude_none=True))
        if len(encoded) > CANONICAL_DIRECTOR_MAX_JSON_BYTES:
            raise ValueError(
                "canonical director payload exceeds "
                f"{CANONICAL_DIRECTOR_MAX_JSON_BYTES} UTF-8 JSON bytes"
            )
        return self


def _compact_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


__all__ = [
    "CANONICAL_DIRECTOR_MAX_JSON_BYTES",
    "CANONICAL_DIRECTOR_MAX_SHOTS",
    "CANONICAL_DIRECTOR_SCHEMA_VERSION",
    "CameraMotionV1",
    "CameraV1",
    "CanonicalDirectorV1",
    "ContinuitySubjectStateV1",
    "ContinuityV1",
    "DirectorShotV1",
    "DirectorSourceV1",
    "DirectorSubjectV1",
    "DirectorTermV1",
    "EnvironmentV1",
    "LensV1",
    "LightingV1",
    "NegativeConstraintsV1",
    "SoundDesignV1",
    "SpeechPerformanceV1",
    "VisualTransitionV1",
]