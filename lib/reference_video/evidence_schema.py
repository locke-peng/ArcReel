"""Hash-chained evidence records for H3 auto-repair acceptance."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_sha(value: str | None, field_name: str) -> None:
    if value is not None and not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class H3EvidenceRecord:
    unit_id: str
    stage: str
    tested_sha: str
    repair_action: str
    provider_recalled: bool
    qa_verdict: str
    source_media_sha256: tuple[str, ...] = ()
    prompt_sha256: str | None = None
    reference_sha256: tuple[str, ...] = ()
    provider_task_id: str | None = None
    provider_run_id: int | None = None
    provider_artifact_id: int | None = None
    pre_media_sha256: str | None = None
    post_media_sha256: str | None = None
    actual_cuts: tuple[tuple[str, Any], ...] = ()
    media_probe: tuple[tuple[str, Any], ...] = ()
    evidence_frames: tuple[int, ...] = ()
    previous_record_sha256: str | None = None
    record_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id is required")
        if not self.stage:
            raise ValueError("stage is required")
        for index, value in enumerate(self.source_media_sha256):
            _validate_sha(value, f"source_media_sha256[{index}]")
        for index, value in enumerate(self.reference_sha256):
            _validate_sha(value, f"reference_sha256[{index}]")
        _validate_sha(self.prompt_sha256, "prompt_sha256")
        _validate_sha(self.pre_media_sha256, "pre_media_sha256")
        _validate_sha(self.post_media_sha256, "post_media_sha256")
        _validate_sha(self.previous_record_sha256, "previous_record_sha256")
        _validate_sha(self.record_sha256, "record_sha256")

    def payload(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "stage": self.stage,
            "tested_sha": self.tested_sha,
            "repair_action": self.repair_action,
            "provider_recalled": self.provider_recalled,
            "qa_verdict": self.qa_verdict,
            "source_media_sha256": list(self.source_media_sha256),
            "prompt_sha256": self.prompt_sha256,
            "reference_sha256": list(self.reference_sha256),
            "provider_task_id": self.provider_task_id,
            "provider_run_id": self.provider_run_id,
            "provider_artifact_id": self.provider_artifact_id,
            "pre_media_sha256": self.pre_media_sha256,
            "post_media_sha256": self.post_media_sha256,
            "actual_cuts": dict(self.actual_cuts),
            "media_probe": dict(self.media_probe),
            "evidence_frames": list(self.evidence_frames),
            "previous_record_sha256": self.previous_record_sha256,
        }

    def compute_sha256(self) -> str:
        encoded = json.dumps(
            self.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def sealed(self) -> H3EvidenceRecord:
        return replace(self, record_sha256=self.compute_sha256())

    def verify(self) -> None:
        if self.record_sha256 is None:
            raise ValueError("record_sha256 is missing")
        expected = self.compute_sha256()
        if self.record_sha256 != expected:
            raise ValueError(
                f"evidence record hash mismatch: {self.record_sha256} != {expected}"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["record_sha256"] = self.record_sha256
        return payload
