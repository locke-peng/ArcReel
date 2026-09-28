"""Fail-closed H3 Media QA gate for formal video selection.

The gate sits after provider bytes exist but before they can become the current formal
artifact. It consumes structured Media QA findings, routes them through the single Phase 3
repair policy, executes only registered deterministic repairs, and re-runs QA.

It never performs provider generation. Any provider-required, unknown, unsupported, or
non-converging repair remains history-only through the caller's artifact-selection seam.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.reference_video.h3_auto_repair_loop import (
    H3AutoRepairPlan,
    execute_h3_auto_repair,
    plan_h3_auto_repair,
)
from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import (
    H3RepairTicketContext,
    build_h3_repair_ticket,
)
from lib.reference_video.media_qa_schema import MediaQAFinding

H3MediaQAEvaluator = Callable[[Path], Awaitable[tuple[MediaQAFinding, ...]]]
H3DeterministicRepairHandler = Callable[[Path, H3AutoRepairPlan], None]


class H3RuntimeSelectionError(RuntimeError):
    """A paid H3 result must not become current without a safe local repair."""

    def __init__(self, code: str, message: str, *, report: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.report = dict(report)


@dataclass(frozen=True)
class H3RuntimeGateResult:
    status: str
    provider_recalled: bool
    repair_passes: int
    source_media_sha256: str
    final_media_sha256: str
    passes: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_recalled": self.provider_recalled,
            "repair_passes": self.repair_passes,
            "source_media_sha256": self.source_media_sha256,
            "final_media_sha256": self.final_media_sha256,
            "passes": [dict(item) for item in self.passes],
        }


def _finding_dict(finding: MediaQAFinding) -> dict[str, Any]:
    return finding.to_dict()


def _plan_dict(plan: H3AutoRepairPlan) -> dict[str, Any]:
    return {
        "unit_id": plan.finding.unit_id,
        "failure_class": plan.failure.failure_class.value,
        "repair_action": plan.decision.action.value,
        "provider_recall_required": plan.decision.provider_recall_required,
        "reason": plan.decision.reason,
    }


def _error_report(
    *,
    source_media_sha256: str,
    current_media_sha256: str,
    passes: list[Mapping[str, Any]],
    status: str,
    repair_tickets: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    report = {
        "status": status,
        "provider_recalled": False,
        "source_media_sha256": source_media_sha256,
        "final_media_sha256": current_media_sha256,
        "passes": [dict(item) for item in passes],
    }
    if repair_tickets:
        report["repair_tickets"] = [dict(item) for item in repair_tickets]
    return report


async def run_h3_runtime_selection_gate(
    staged_file: Path,
    *,
    evaluator: H3MediaQAEvaluator,
    repair_handlers: Mapping[H3RepairAction, H3DeterministicRepairHandler],
    max_repair_passes: int = 2,
    repair_ticket_context: H3RepairTicketContext | None = None,
) -> H3RuntimeGateResult:
    """Run Media QA -> policy -> deterministic repair -> Re-QA before formal selection.

    max_repair_passes counts repair rounds, not the initial QA inspection.
    """

    if not staged_file.is_file() or staged_file.stat().st_size == 0:
        raise FileNotFoundError(staged_file)
    if max_repair_passes < 0:
        raise ValueError("max_repair_passes must be >= 0")

    source_hash = sha256_file(staged_file)
    current_hash = source_hash
    pass_records: list[Mapping[str, Any]] = []

    for pass_index in range(max_repair_passes + 1):
        findings = tuple(await evaluator(staged_file))
        plans = tuple(plan_h3_auto_repair(finding) for finding in findings)
        record: dict[str, Any] = {
            "pass_index": pass_index,
            "media_sha256": current_hash,
            "findings": [_finding_dict(finding) for finding in findings],
            "plans": [_plan_dict(plan) for plan in plans],
        }
        pass_records.append(record)

        if not findings:
            return H3RuntimeGateResult(
                status="PASS",
                provider_recalled=False,
                repair_passes=pass_index,
                source_media_sha256=source_hash,
                final_media_sha256=current_hash,
                passes=tuple(pass_records),
            )

        provider_required = tuple(plan for plan in plans if plan.provider_recall_required)
        if provider_required:
            tickets = tuple(
                build_h3_repair_ticket(
                    plan,
                    source_media_sha256=current_hash,
                    context=repair_ticket_context,
                ).to_dict()
                for plan in provider_required
            )
            record["repair_tickets"] = [dict(ticket) for ticket in tickets]
            report = _error_report(
                source_media_sha256=source_hash,
                current_media_sha256=current_hash,
                passes=pass_records,
                status="PROVIDER_REPAIR_REQUIRED",
                repair_tickets=tickets,
            )
            raise H3RuntimeSelectionError(
                "h3_provider_repair_required",
                "H3 Media QA requires provider regeneration; automatic provider recall is disabled",
                report=report,
            )

        escalations = tuple(
            plan for plan in plans if plan.decision.action is H3RepairAction.ESCALATE
        )
        if escalations:
            tickets = tuple(
                build_h3_repair_ticket(
                    plan,
                    source_media_sha256=current_hash,
                    context=repair_ticket_context,
                ).to_dict()
                for plan in escalations
            )
            record["repair_tickets"] = [dict(ticket) for ticket in tickets]
            report = _error_report(
                source_media_sha256=source_hash,
                current_media_sha256=current_hash,
                passes=pass_records,
                status="HUMAN_REVIEW_REQUIRED",
                repair_tickets=tickets,
            )
            raise H3RuntimeSelectionError(
                "h3_media_qa_escalation_required",
                "H3 Media QA produced an unknown failure class and must fail closed",
                report=report,
            )

        missing_handlers = tuple(
            plan for plan in plans if plan.decision.action not in repair_handlers
        )
        if missing_handlers:
            report = _error_report(
                source_media_sha256=source_hash,
                current_media_sha256=current_hash,
                passes=pass_records,
                status="DETERMINISTIC_HANDLER_MISSING",
            )
            raise H3RuntimeSelectionError(
                "h3_deterministic_repair_handler_missing",
                "H3 deterministic repair was planned but no runtime handler is registered",
                report=report,
            )

        if pass_index >= max_repair_passes:
            report = _error_report(
                source_media_sha256=source_hash,
                current_media_sha256=current_hash,
                passes=pass_records,
                status="REPAIR_PASSES_EXHAUSTED",
            )
            raise H3RuntimeSelectionError(
                "h3_media_qa_unresolved",
                "H3 Media QA findings remain after the maximum deterministic repair passes",
                report=report,
            )

        before_hash = current_hash
        executed: list[dict[str, Any]] = []
        for plan in plans:
            handler = repair_handlers[plan.decision.action]

            def _runner(
                *,
                _handler: H3DeterministicRepairHandler = handler,
                _plan: H3AutoRepairPlan = plan,
            ) -> None:
                _handler(staged_file, _plan)

            result = execute_h3_auto_repair(
                plan,
                source_media=(staged_file,),
                output_media=staged_file,
                deterministic_runner=_runner,
            )
            if result.provider_recalled:
                raise RuntimeError("deterministic runtime repair unexpectedly recalled provider")
            executed.append(
                {
                    "action": result.action,
                    "provider_recalled": result.provider_recalled,
                    "input_media_sha256": result.source_media_sha256[0],
                    "output_media_sha256": result.output_media_sha256,
                }
            )
        record["executed_repairs"] = executed

        current_hash = sha256_file(staged_file)
        record["post_repair_media_sha256"] = current_hash
        if current_hash == before_hash:
            report = _error_report(
                source_media_sha256=source_hash,
                current_media_sha256=current_hash,
                passes=pass_records,
                status="NO_REPAIR_PROGRESS",
            )
            raise H3RuntimeSelectionError(
                "h3_deterministic_repair_no_progress",
                "H3 deterministic repair did not change staged media bytes",
                report=report,
            )

    raise AssertionError("unreachable H3 runtime gate loop")
