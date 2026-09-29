"""Auditable fail-closed repair tickets for non-deterministic H3 failures.

This module owns no repair policy. It serializes the existing Phase 3 planner decision
into an immutable escalation object that can be reviewed and explicitly approved later.
Provider execution remains disabled unless a matching approval is supplied to the separate
shot-scoped executor.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from lib.reference_video.h3_auto_repair_loop import H3AutoRepairPlan
from lib.reference_video.h3_production_policy import H3RepairAction

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class H3RepairTicketStatus(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class H3RepairScopeKind(StrEnum):
    SHOT = "shot"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class H3ShotRepairContext:
    shot_id: str
    provider_prompt_sha256: str | None = None
    reference_sha256: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.shot_id.strip():
            raise ValueError("shot_id is required")
        _validate_sha(self.provider_prompt_sha256, "provider_prompt_sha256")
        _validate_sha_tuple(self.reference_sha256, "reference_sha256")


@dataclass(frozen=True)
class H3RepairTicketContext:
    provider_prompt_sha256: str | None = None
    reference_sha256: tuple[str, ...] = ()
    shot_contexts: tuple[H3ShotRepairContext, ...] = ()
    provider_task_id: str | None = None
    provider_run_id: int | None = None
    provider_artifact_id: int | None = None

    def __post_init__(self) -> None:
        _validate_sha(self.provider_prompt_sha256, "provider_prompt_sha256")
        _validate_sha_tuple(self.reference_sha256, "reference_sha256")
        shot_ids = [item.shot_id for item in self.shot_contexts]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("shot_contexts must not contain duplicate shot_id values")

    def resolve_for_shot(self, shot_id: str | None) -> tuple[str | None, tuple[str, ...]]:
        if shot_id is not None:
            for item in self.shot_contexts:
                if item.shot_id == shot_id:
                    return (
                        item.provider_prompt_sha256 or self.provider_prompt_sha256,
                        item.reference_sha256 or self.reference_sha256,
                    )
        return self.provider_prompt_sha256, self.reference_sha256


@dataclass(frozen=True)
class H3RepairTicket:
    schema_version: int
    ticket_id: str
    ticket_sha256: str
    status: H3RepairTicketStatus
    approval_eligible: bool
    unit_id: str
    shot_id: str | None
    scope_kind: H3RepairScopeKind
    start_seconds: float | None
    end_seconds: float | None
    region: str | None
    failure_class: str
    repair_action: str
    provider_recall_required: bool
    canonical_violation: str
    planner_reason: str
    source_media_sha256: str
    provider_prompt_sha256: str | None
    reference_sha256: tuple[str, ...]
    evidence_frames: tuple[int, ...]
    tags: tuple[str, ...]
    provider_task_id: str | None = None
    provider_run_id: int | None = None
    provider_artifact_id: int | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("repair ticket schema_version must be 1")
        if not self.ticket_id.startswith("h3rt_"):
            raise ValueError("repair ticket_id must start with h3rt_")
        _validate_sha(self.ticket_sha256, "ticket_sha256")
        _validate_sha(self.source_media_sha256, "source_media_sha256")
        _validate_sha(self.provider_prompt_sha256, "provider_prompt_sha256")
        _validate_sha_tuple(self.reference_sha256, "reference_sha256")
        if self.scope_kind is H3RepairScopeKind.SHOT:
            if not self.shot_id:
                raise ValueError("shot-scoped repair ticket requires shot_id")
            if self.start_seconds is None or self.end_seconds is None:
                raise ValueError("shot-scoped repair ticket requires a time range")
            if self.end_seconds <= self.start_seconds:
                raise ValueError("shot-scoped repair ticket requires a positive time range")
        if self.approval_eligible:
            if self.status is not H3RepairTicketStatus.AWAITING_APPROVAL:
                raise ValueError("approval-eligible ticket must await approval")
            if not self.provider_recall_required:
                raise ValueError("approval-eligible ticket must require provider recall")
            if self.scope_kind is not H3RepairScopeKind.SHOT:
                raise ValueError("approval-eligible provider ticket must be shot-scoped")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "approval_eligible": self.approval_eligible,
            "unit_id": self.unit_id,
            "shot_id": self.shot_id,
            "scope_kind": self.scope_kind.value,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "region": self.region,
            "failure_class": self.failure_class,
            "repair_action": self.repair_action,
            "provider_recall_required": self.provider_recall_required,
            "canonical_violation": self.canonical_violation,
            "planner_reason": self.planner_reason,
            "source_media_sha256": self.source_media_sha256,
            "provider_prompt_sha256": self.provider_prompt_sha256,
            "reference_sha256": list(self.reference_sha256),
            "evidence_frames": list(self.evidence_frames),
            "tags": list(self.tags),
            "provider_task_id": self.provider_task_id,
            "provider_run_id": self.provider_run_id,
            "provider_artifact_id": self.provider_artifact_id,
        }

    def to_dict(self) -> dict[str, Any]:
        result = self.payload()
        result["ticket_id"] = self.ticket_id
        result["ticket_sha256"] = self.ticket_sha256
        return result


@dataclass(frozen=True)
class H3ProviderRepairApproval:
    ticket_id: str
    ticket_sha256: str
    source_media_sha256: str
    shot_id: str
    approved_by: str
    approved_at: str
    max_provider_calls: int = 1

    def __post_init__(self) -> None:
        if not self.ticket_id.startswith("h3rt_"):
            raise ValueError("approval ticket_id must start with h3rt_")
        _validate_sha(self.ticket_sha256, "ticket_sha256")
        _validate_sha(self.source_media_sha256, "source_media_sha256")
        if not self.shot_id.strip():
            raise ValueError("approval shot_id is required")
        if not self.approved_by.strip():
            raise ValueError("approved_by is required")
        if not self.approved_at.strip():
            raise ValueError("approved_at is required")
        if self.max_provider_calls != 1:
            raise ValueError("shot-scoped provider approval allows exactly one provider call")


def _validate_sha(value: str | None, field_name: str) -> None:
    if value is not None and not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _validate_sha_tuple(values: tuple[str, ...], field_name: str) -> None:
    for index, value in enumerate(values):
        _validate_sha(value, f"{field_name}[{index}]")


def _ticket_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_h3_repair_ticket(
    plan: H3AutoRepairPlan,
    *,
    source_media_sha256: str,
    context: H3RepairTicketContext | None = None,
) -> H3RepairTicket:
    """Freeze one planner result into an auditable escalation ticket.

    Provider-required tickets are approval eligible only when Media QA identified exactly
    one shot and its time range. Unscoped provider failures and UNKNOWN escalations remain
    human-review-only and cannot be approved for automatic provider execution.
    """

    _validate_sha(source_media_sha256, "source_media_sha256")
    decision = plan.decision
    if not decision.provider_recall_required and decision.action is not H3RepairAction.ESCALATE:
        raise ValueError("repair tickets are only for provider-required or escalated plans")

    finding = plan.finding
    time_range = finding.time_range
    scope_is_shot = bool(finding.shot_id and time_range is not None)
    scope_kind = H3RepairScopeKind.SHOT if scope_is_shot else H3RepairScopeKind.UNRESOLVED
    approval_eligible = bool(decision.provider_recall_required and scope_is_shot)
    status = (
        H3RepairTicketStatus.AWAITING_APPROVAL
        if approval_eligible
        else H3RepairTicketStatus.HUMAN_REVIEW_REQUIRED
    )

    ticket_context = context or H3RepairTicketContext()
    prompt_sha, reference_sha = ticket_context.resolve_for_shot(finding.shot_id)
    payload = {
        "schema_version": 1,
        "status": status.value,
        "approval_eligible": approval_eligible,
        "unit_id": finding.unit_id,
        "shot_id": finding.shot_id,
        "scope_kind": scope_kind.value,
        "start_seconds": time_range.start_seconds if time_range else None,
        "end_seconds": time_range.end_seconds if time_range else None,
        "region": finding.region,
        "failure_class": plan.failure.failure_class.value,
        "repair_action": decision.action.value,
        "provider_recall_required": decision.provider_recall_required,
        "canonical_violation": finding.canonical_violation,
        "planner_reason": decision.reason,
        "source_media_sha256": source_media_sha256,
        "provider_prompt_sha256": prompt_sha,
        "reference_sha256": list(reference_sha),
        "evidence_frames": list(finding.evidence_frames),
        "tags": list(finding.tags),
        "provider_task_id": ticket_context.provider_task_id,
        "provider_run_id": ticket_context.provider_run_id,
        "provider_artifact_id": ticket_context.provider_artifact_id,
    }
    digest = _ticket_digest(payload)
    return H3RepairTicket(
        schema_version=1,
        ticket_id=f"h3rt_{digest[:24]}",
        ticket_sha256=digest,
        status=status,
        approval_eligible=approval_eligible,
        unit_id=finding.unit_id,
        shot_id=finding.shot_id,
        scope_kind=scope_kind,
        start_seconds=time_range.start_seconds if time_range else None,
        end_seconds=time_range.end_seconds if time_range else None,
        region=finding.region,
        failure_class=plan.failure.failure_class.value,
        repair_action=decision.action.value,
        provider_recall_required=decision.provider_recall_required,
        canonical_violation=finding.canonical_violation,
        planner_reason=decision.reason,
        source_media_sha256=source_media_sha256,
        provider_prompt_sha256=prompt_sha,
        reference_sha256=reference_sha,
        evidence_frames=finding.evidence_frames,
        tags=finding.tags,
        provider_task_id=ticket_context.provider_task_id,
        provider_run_id=ticket_context.provider_run_id,
        provider_artifact_id=ticket_context.provider_artifact_id,
    )


def validate_provider_repair_approval(
    ticket: H3RepairTicket,
    approval: H3ProviderRepairApproval,
) -> None:
    """Fail closed unless approval binds exactly to one immutable shot ticket."""

    if not ticket.approval_eligible:
        raise RuntimeError("repair ticket is not eligible for provider approval")
    if ticket.status is not H3RepairTicketStatus.AWAITING_APPROVAL:
        raise RuntimeError("repair ticket is not awaiting approval")
    if ticket.scope_kind is not H3RepairScopeKind.SHOT or ticket.shot_id is None:
        raise RuntimeError("provider approval requires a shot-scoped ticket")
    if approval.ticket_id != ticket.ticket_id:
        raise RuntimeError("provider approval ticket_id does not match repair ticket")
    if approval.ticket_sha256 != ticket.ticket_sha256:
        raise RuntimeError("provider approval ticket SHA does not match repair ticket")
    if approval.source_media_sha256 != ticket.source_media_sha256:
        raise RuntimeError("provider approval source media SHA does not match repair ticket")
    if approval.shot_id != ticket.shot_id:
        raise RuntimeError("provider approval shot scope does not match repair ticket")
