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
    blur_radius: float = 18.0
    opacity: float = 1.0


@dataclass(frozen=True)
class RepairRegionKeyframe:
    time_sec: float
    x: int
    y: int
    width: int
    height: int
    enabled: bool = True


@dataclass(frozen=True)
class RepairRegionTrack:
    shot_id: str
    start_sec: float
    end_sec: float
    keyframes: tuple[RepairRegionKeyframe, ...]
    blur_radius: float = 18.0
    opacity: float = 1.0


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
    region_tracks: tuple[RepairRegionTrack, ...] = ()
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
        if not request.regions and not request.region_tracks:
            raise H3MediaPipelineError("pixel sanitization requires explicit bounded regions")
        for region in request.regions:
            if region.start_sec < 0 or region.end_sec <= region.start_sec:
                raise H3MediaPipelineError("repair region requires a positive time interval")
            if min(region.x, region.y, region.width, region.height) < 0:
                raise H3MediaPipelineError("repair region geometry must be non-negative")
            if region.width == 0 or region.height == 0:
                raise H3MediaPipelineError("repair region must have non-zero area")
            if region.blur_radius <= 0:
                raise H3MediaPipelineError("repair region blur radius must be positive")
            if not 0 < region.opacity <= 1:
                raise H3MediaPipelineError("repair region opacity must be in (0, 1]")
        for track in request.region_tracks:
            if track.start_sec < 0 or track.end_sec <= track.start_sec:
                raise H3MediaPipelineError("repair track requires a positive time interval")
            if track.blur_radius <= 0:
                raise H3MediaPipelineError("repair track blur radius must be positive")
            if not 0 < track.opacity <= 1:
                raise H3MediaPipelineError("repair track opacity must be in (0, 1]")
            if not track.keyframes:
                raise H3MediaPipelineError("repair track requires keyframes")
            cursor = -1.0
            for keyframe in track.keyframes:
                if keyframe.time_sec < cursor:
                    raise H3MediaPipelineError("repair track keyframes must be time ordered")
                if min(keyframe.x, keyframe.y, keyframe.width, keyframe.height) < 0:
                    raise H3MediaPipelineError("repair track geometry must be non-negative")
                if keyframe.enabled and (keyframe.width == 0 or keyframe.height == 0):
                    raise H3MediaPipelineError("enabled repair track keyframe must have non-zero area")
                cursor = keyframe.time_sec

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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    metadata: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        stage: str,
        artifact_path: Path,
        parent_sha256: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceNode:
        normalized_metadata = dict(metadata or {})
        canonical_metadata = json.dumps(
            normalized_metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            stage=stage,
            artifact_sha256=sha256_file(artifact_path),
            parent_sha256=tuple(parent_sha256),
            metadata_sha256=hashlib.sha256(canonical_metadata).hexdigest(),
            metadata=normalized_metadata,
        )


@dataclass(frozen=True)
class EvidenceChain:
    unit_id: str
    nodes: tuple[EvidenceNode, ...]

    def validate(self) -> None:
        seen: set[str] = set()
        root_stages = {"provider_output", "canonical_asset"}
        for index, node in enumerate(self.nodes):
            if not node.parent_sha256:
                if node.stage not in root_stages:
                    raise H3MediaPipelineError(
                        f"{node.stage}: only immutable provider/canonical assets may be evidence roots"
                    )
                if index == 0:
                    seen.add(node.artifact_sha256)
                    continue
            missing = set(node.parent_sha256) - seen
            if missing:
                raise H3MediaPipelineError(
                    f"{node.stage}: evidence parent hash not present earlier in chain: {sorted(missing)!r}"
                )
            seen.add(node.artifact_sha256)

    @classmethod
    def from_json(cls, value: str) -> "EvidenceChain":
        try:
            raw = json.loads(value)
            unit_id = str(raw["unit_id"])
            nodes = tuple(
                EvidenceNode(
                    stage=str(item["stage"]),
                    artifact_sha256=str(item["artifact_sha256"]),
                    parent_sha256=tuple(str(parent) for parent in item.get("parent_sha256") or ()),
                    metadata_sha256=str(item["metadata_sha256"]),
                    metadata=dict(item.get("metadata") or {}),
                )
                for item in raw["nodes"]
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise H3MediaPipelineError("malformed H3 evidence chain") from exc
        chain = cls(unit_id=unit_id, nodes=nodes)
        chain.validate()
        return chain

    def to_json(self) -> str:
        self.validate()
        return json.dumps(
            {"unit_id": self.unit_id, "nodes": [asdict(node) for node in self.nodes]},
            ensure_ascii=False,
            indent=2,
        )


def write_provider_evidence_chain(
    *,
    unit_id: str,
    provider_output: Path,
    provider_prompt: str,
    provider_id: str,
    model_id: str | None,
    requested_resolution: str | None,
    requested_duration_seconds: int,
    output_path: Path,
) -> EvidenceChain:
    """Persist the immutable Phase-2 root node immediately after provider success."""

    node = EvidenceNode.create(
        stage="provider_output",
        artifact_path=provider_output,
        metadata={
            "provider_id": provider_id,
            "model_id": model_id,
            "provider_prompt_sha256": sha256_text(provider_prompt),
            "requested_resolution": requested_resolution,
            "requested_duration_seconds": requested_duration_seconds,
        },
    )
    chain = EvidenceChain(unit_id=unit_id, nodes=(node,))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(chain.to_json(), encoding="utf-8")
    return chain
