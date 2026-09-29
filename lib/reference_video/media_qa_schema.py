"""Structured media-QA findings for the H3 auto-repair loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from lib.reference_video.h3_production_policy import H3FailureClass


class MediaQASeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class MediaQARepairability(StrEnum):
    DETERMINISTIC = "deterministic"
    PROVIDER = "provider"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True)
class MediaQATimeRange:
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        if self.start_seconds < 0:
            raise ValueError("start_seconds must be >= 0")
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be >= start_seconds")

    def to_dict(self) -> dict[str, float]:
        return {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
        }


@dataclass(frozen=True)
class MediaQAFinding:
    unit_id: str
    canonical_violation: str
    severity: MediaQASeverity
    provider_result_usable: bool
    audio_is_accepted: bool
    repairability: MediaQARepairability
    affected_fraction: float = 1.0
    shot_id: str | None = None
    time_range: MediaQATimeRange | None = None
    region: str | None = None
    failure_class: H3FailureClass | None = None
    evidence_frames: tuple[int, ...] = ()
    exact_visible_text: str | None = None
    tags: tuple[str, ...] = ()
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.unit_id.strip():
            raise ValueError("unit_id is required")
        if not self.canonical_violation.strip():
            raise ValueError("canonical_violation is required")
        if not 0.0 <= self.affected_fraction <= 1.0:
            raise ValueError("affected_fraction must be between 0 and 1")
        if any(frame < 0 for frame in self.evidence_frames):
            raise ValueError("evidence_frames must be >= 0")
        if self.failure_class == H3FailureClass.EXACT_TEXT_REQUIRED and not self.exact_visible_text:
            raise ValueError("exact_visible_text is required for exact-text findings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "shot_id": self.shot_id,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "region": self.region,
            "failure_class": self.failure_class.value if self.failure_class else None,
            "canonical_violation": self.canonical_violation,
            "severity": self.severity.value,
            "evidence_frames": list(self.evidence_frames),
            "provider_result_usable": self.provider_result_usable,
            "audio_is_accepted": self.audio_is_accepted,
            "repairability": self.repairability.value,
            "affected_fraction": self.affected_fraction,
            "exact_visible_text": self.exact_visible_text,
            "tags": list(self.tags),
            "details": dict(self.details),
        }
