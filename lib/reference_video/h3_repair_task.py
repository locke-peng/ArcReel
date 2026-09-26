"""Validated production task contract for post-provider H3 deterministic repair.

The task contract is deliberately downstream of provider generation. Review/QA supplies
normalized observations plus deterministic coordinates/timeline facts. This module
never infers story facts and never permits semantic regeneration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from lib.reference_video.h3_media_pipeline import (
    H3MediaPipelineError,
    MediaObservation,
    ObservationKind,
    RepairAction,
    RepairRegion,
    RepairRegionKeyframe,
    RepairRegionTrack,
    RepairRequest,
    TimelineSegment,
    classify_media_observations,
    validate_repair_request,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TASK_ACTIONS = {
    RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
    RepairAction.DETERMINISTIC_AV_RETIME,
}


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise H3MediaPipelineError(f"{field} must be an array of objects")
    return list(value)


def _float(item: Mapping[str, Any], key: str) -> float:
    try:
        return float(item[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise H3MediaPipelineError(f"{key} must be numeric") from exc


def _int(item: Mapping[str, Any], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise H3MediaPipelineError(f"{key} must be an integer")
    return value


@dataclass(frozen=True)
class H3RepairTaskPlan:
    expected_source_sha256: str
    observations: tuple[MediaObservation, ...]
    action: RepairAction
    regions: tuple[RepairRegion, ...] = ()
    region_tracks: tuple[RepairRegionTrack, ...] = ()
    timeline: tuple[TimelineSegment, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "H3RepairTaskPlan":
        expected = str(payload.get("expected_source_sha256") or "").lower()
        if not _SHA256_RE.fullmatch(expected):
            raise H3MediaPipelineError("expected_source_sha256 must be a lowercase SHA-256 digest")

        observations: list[MediaObservation] = []
        for item in _mapping_list(payload.get("observations"), field="observations"):
            try:
                kind = ObservationKind(str(item.get("kind") or ""))
            except ValueError as exc:
                raise H3MediaPipelineError(f"unsupported media observation: {item.get('kind')!r}") from exc
            observations.append(
                MediaObservation(
                    kind=kind,
                    shot_id=str(item["shot_id"]) if item.get("shot_id") is not None else None,
                    start_sec=float(item["start_sec"]) if item.get("start_sec") is not None else None,
                    end_sec=float(item["end_sec"]) if item.get("end_sec") is not None else None,
                    detail=str(item.get("detail") or ""),
                )
            )
        if not observations:
            raise H3MediaPipelineError("production repair requires at least one QA observation")

        decision = classify_media_observations(observations)
        if decision.action not in _TASK_ACTIONS:
            raise H3MediaPipelineError(
                f"QA decision {decision.action.value if decision.action else 'none'} is not executable "
                "by the local production repair task"
            )

        declared = payload.get("action")
        if declared is not None:
            try:
                declared_action = RepairAction(str(declared))
            except ValueError as exc:
                raise H3MediaPipelineError(f"unsupported repair action: {declared!r}") from exc
            if declared_action != decision.action:
                raise H3MediaPipelineError(
                    f"declared repair action {declared_action.value} does not match QA planner "
                    f"decision {decision.action.value}"
                )

        regions: list[RepairRegion] = []
        for item in _mapping_list(payload.get("regions"), field="regions"):
            regions.append(
                RepairRegion(
                    shot_id=str(item.get("shot_id") or ""),
                    start_sec=_float(item, "start_sec"),
                    end_sec=_float(item, "end_sec"),
                    x=_int(item, "x"),
                    y=_int(item, "y"),
                    width=_int(item, "width"),
                    height=_int(item, "height"),
                    blur_radius=float(item.get("blur_radius", 18.0)),
                    opacity=float(item.get("opacity", 1.0)),
                )
            )

        tracks: list[RepairRegionTrack] = []
        for item in _mapping_list(payload.get("region_tracks"), field="region_tracks"):
            keyframes: list[RepairRegionKeyframe] = []
            for keyframe in _mapping_list(item.get("keyframes"), field="region_tracks[].keyframes"):
                keyframes.append(
                    RepairRegionKeyframe(
                        time_sec=_float(keyframe, "time_sec"),
                        x=_int(keyframe, "x"),
                        y=_int(keyframe, "y"),
                        width=_int(keyframe, "width"),
                        height=_int(keyframe, "height"),
                        enabled=bool(keyframe.get("enabled", True)),
                    )
                )
            tracks.append(
                RepairRegionTrack(
                    shot_id=str(item.get("shot_id") or ""),
                    start_sec=_float(item, "start_sec"),
                    end_sec=_float(item, "end_sec"),
                    keyframes=tuple(keyframes),
                    blur_radius=float(item.get("blur_radius", 18.0)),
                    opacity=float(item.get("opacity", 1.0)),
                )
            )

        timeline = tuple(
            TimelineSegment(
                source_start_sec=_float(item, "source_start_sec"),
                source_end_sec=_float(item, "source_end_sec"),
                target_duration_sec=_float(item, "target_duration_sec"),
            )
            for item in _mapping_list(payload.get("timeline"), field="timeline")
        )

        plan = cls(
            expected_source_sha256=expected,
            observations=tuple(observations),
            action=decision.action,
            regions=tuple(regions),
            region_tracks=tuple(tracks),
            timeline=timeline,
        )
        # Validate geometry/timeline before any queued executor spends CPU.
        validate_repair_request(plan.to_request(Path("__source__.mp4"), Path("__output__.mp4")))
        return plan

    def to_request(self, source_path: Path, output_path: Path) -> RepairRequest:
        return RepairRequest(
            action=self.action,
            source_path=source_path,
            output_path=output_path,
            regions=self.regions,
            region_tracks=self.region_tracks,
            timeline=self.timeline,
        )

    def evidence_metadata(self) -> dict[str, object]:
        return {
            "qa_observations": [
                {
                    "kind": item.kind.value,
                    "shot_id": item.shot_id,
                    "start_sec": item.start_sec,
                    "end_sec": item.end_sec,
                    "detail": item.detail,
                }
                for item in self.observations
            ],
            "planner_action": self.action.value,
            "provider_recalled": False,
        }
