"""Phase 4 orchestration for the H3 media auto-repair loop.

This module deliberately owns no repair policy. It connects structured Media QA findings
to the existing Phase 3 classifier/planner/executor chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lib.reference_video.h3_failure_classifier import classify_h3_media_finding
from lib.reference_video.h3_production_policy import (
    H3MediaFailure,
    H3RepairDecision,
    plan_h3_media_repair,
)
from lib.reference_video.h3_repair_executor import (
    H3RepairExecutionResult,
    RepairRunner,
    execute_h3_media_repair,
)
from lib.reference_video.media_qa_schema import MediaQAFinding


@dataclass(frozen=True)
class H3AutoRepairPlan:
    finding: MediaQAFinding
    failure: H3MediaFailure
    decision: H3RepairDecision

    @property
    def provider_recall_required(self) -> bool:
        return self.decision.provider_recall_required


def plan_h3_auto_repair(finding: MediaQAFinding) -> H3AutoRepairPlan:
    """Classify a structured finding and invoke the single Phase 3 repair planner."""

    failure = classify_h3_media_finding(finding)
    decision = plan_h3_media_repair(failure)
    return H3AutoRepairPlan(
        finding=finding,
        failure=failure,
        decision=decision,
    )


def execute_h3_auto_repair(
    plan: H3AutoRepairPlan,
    *,
    source_media: Iterable[Path],
    output_media: Path,
    deterministic_runner: RepairRunner | None = None,
    provider_runner: RepairRunner | None = None,
    allow_provider_recall: bool = False,
) -> H3RepairExecutionResult:
    """Execute the already-selected planner decision through the fail-closed executor."""

    return execute_h3_media_repair(
        plan.decision,
        source_media=source_media,
        output_media=output_media,
        deterministic_runner=deterministic_runner,
        provider_runner=provider_runner,
        allow_provider_recall=allow_provider_recall,
    )
