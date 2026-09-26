"""Post-provider H3 media QA, deterministic repair planning, and evidence provenance.

The module is unit-agnostic. Detectors/reviewers emit normalized observations; this
layer classifies them, chooses the least-destructive repair, validates repair inputs,
and writes a hash-linked evidence chain. Paid regeneration is never executed here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from lib.reference_video.h3_production_policy import (
    MediaIssueCode,
    RepairAction,
    plan_h3_media_repair,
)


class H3MediaPipelineError(ValueError):
    pass


class ObservationKind(StrEnum):
    EXACT_TEXT_MISMATCH = "exact_text_mismatch"
    UNEXPECTED_READABLE_TEXT = "unexpected_readable_text"
    LOCAL_UI_TEXT = "local_ui_text"
    SHOT_BOUNDARY_DRIFT = "shot_boundary_drift"
    AUDIO_BOUNDARY_DRIFT = "audio_boundary_drift"
    IDENTITY_MISMATCH = "identity_mismatch"
    ACTION_MISMATCH = "action_mismatch"
    SCENE_COMPOSITION_MISMATCH = "scene_composition_mismatch"


_OBSERVATION_TO_ISSUE = {
    ObservationKind.EXACT_TEXT_MISMATCH: MediaIssueCode.EXACT_TEXT_MISSING_OR_WRONG,
    ObservationKind.UNEXPECTED_READABLE_TEXT: MediaIssueCode.NONCANONICAL_VISIBLE_TEXT,
    ObservationKind.LOCAL_UI_TEXT: MediaIssueCode.LOCAL_UI_TEXT_CONTAMINATION,
    ObservationKind.SHOT_BOUNDARY_DRIFT: MediaIssueCode.SHOT_TIMELINE_DRIFT,
    ObservationKind.AUDIO_BOUNDARY_DRIFT: MediaIssueCode.AUDIO_TIMELINE_DRIFT,
    ObservationKind.IDENTITY_MISMATCH: MediaIssueCode.IDENTITY_DRIFT,
    ObservationKind.ACTION_MISMATCH: MediaIssueCode.ACTION_OR_STAGING_DRIFT,
    ObservationKind.SCENE_COMPOSITION_MISMATCH: MediaIssueCode.SCENE_OR_COMPOSITION_DRIFT,
}


@dataclass(frozen=True)
class MediaObservation:
    kind: ObservationKind
    shot_id: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    detail: str = ""


@dataclass(frozen=True)
class RepairRegion:
    shot_id: str
    start_sec: float
    end_sec: float
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TimelineSegment:
    source_start_sec: float
    source_end_sec: float
    target_duration_sec: float


@dataclass(frozen=True)
class RepairRequest:
    action: RepairAction
    source_path: Path
    output_path: Path
    regions: tuple[RepairRegion, ...] = ()
    timeline: tuple[TimelineSegment, ...] = ()
    exact_text: tuple[str, ...] = ()


@dataclass(frozen=True)
class MediaQADecision:
    issues: tuple[MediaIssueCode, ...]
    action: RepairAction | None
    provider_recall_allowed: bool


def classify_media_observations(
    observations: Sequence[MediaObservation],
) -> MediaQADecision:
    issues = tuple(dict.fromkeys(_OBSERVATION_TO_ISSUE[item.kind] for item in observations))
    if not issues:
        return MediaQADecision(issues=(), action=None, provider_recall_allowed=False)
    action = plan_h3_media_repair(issues)
    return MediaQADecision(
        issues=issues,
        action=action,
        provider_recall_allowed=action == RepairAction.REGENERATE_SHOT,
    )


def validate_repair_request(request: RepairRequest) -> None:
    if request.source_path == request.output_path:
        raise H3MediaPipelineError("repair output must not overwrite immutable source evidence")

    if request.action == RepairAction.DETERMINISTIC_PIXEL_SANITIZATION:
        if not request.regions:
            raise H3MediaPipelineError("pixel sanitization requires explicit bounded regions")
        for region in request.regions:
            if region.start_sec < 0 or region.end_sec <= region.start_sec:
                raise H3MediaPipelineError("repair region requires a positive time interval")
            if min(region.x, region.y, region.width, region.height) < 0:
                raise H3MediaPipelineError("repair region geometry must be non-negative")
            if region.width == 0 or region.height == 0:
                raise H3MediaPipelineError("repair region must have non-zero area")

    elif request.action == RepairAction.DETERMINISTIC_AV_RETIME:
        if not request.timeline:
            raise H3MediaPipelineError("A/V retime requires explicit source/target timeline segments")
        cursor = 0.0
        for segment in request.timeline:
            if segment.source_start_sec < cursor - 1e-6:
                raise H3MediaPipelineError("timeline source segments must be ordered and non-overlapping")
            if segment.source_end_sec <= segment.source_start_sec:
                raise H3MediaPipelineError("timeline source segment must have positive duration")
            if segment.target_duration_sec <= 0:
                raise H3MediaPipelineError("timeline target duration must be positive")
            cursor = segment.source_end_sec

    elif request.action == RepairAction.DETERMINISTIC_TEXT_PLATE:
        if not request.exact_text:
            raise H3MediaPipelineError("text plate requires canonical exact text")

    elif request.action in {RepairAction.REGENERATE_SHOT, RepairAction.REJECT_OR_ESCALATE}:
        raise H3MediaPipelineError(
            f"{request.action.value} is not a deterministic local repair and cannot execute in this stage"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class EvidenceNode:
    stage: str
    artifact_sha256: str
    parent_sha256: tuple[str, ...]
    metadata_sha256: str

    @classmethod
    def create(
        cls,
        *,
        stage: str,
        artifact_path: Path,
        parent_sha256: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> "EvidenceNode":
        canonical_metadata = json.dumps(
            dict(metadata or {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            stage=stage,
            artifact_sha256=sha256_file(artifact_path),
            parent_sha256=tuple(parent_sha256),
            metadata_sha256=hashlib.sha256(canonical_metadata).hexdigest(),
        )


@dataclass(frozen=True)
class EvidenceChain:
    unit_id: str
    nodes: tuple[EvidenceNode, ...]

    def validate(self) -> None:
        seen: set[str] = set()
        for index, node in enumerate(self.nodes):
            if index and not node.parent_sha256:
                raise H3MediaPipelineError(f"{node.stage}: derived evidence node requires parent hash")
            missing = set(node.parent_sha256) - seen
            if missing:
                raise H3MediaPipelineError(
                    f"{node.stage}: evidence parent hash not present earlier in chain: {sorted(missing)!r}"
                )
            seen.add(node.artifact_sha256)

    def to_json(self) -> str:
        self.validate()
        return json.dumps(
            {"unit_id": self.unit_id, "nodes": [asdict(node) for node in self.nodes]},
            ensure_ascii=False,
            indent=2,
        )
