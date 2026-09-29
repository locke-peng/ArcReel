"""Shot-scoped provider repair execution boundary for approved H3 repair tickets.

This module never chooses a repair action and never authorizes spend. It consumes an
immutable repair ticket plus a matching explicit approval, invokes exactly one injected
provider runner for that shot, then invokes an injected deterministic assembler. The
resulting unit media must still pass the normal H3 runtime gate before formal selection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import (
    H3ProviderRepairApproval,
    H3RepairScopeKind,
    H3RepairTicket,
    validate_provider_repair_approval,
)


@dataclass(frozen=True)
class H3ShotRepairRequest:
    ticket_id: str
    ticket_sha256: str
    unit_id: str
    shot_id: str
    start_seconds: float
    end_seconds: float
    repair_action: H3RepairAction
    source_media_sha256: str
    provider_prompt_sha256: str | None
    reference_sha256: tuple[str, ...]

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds

    def to_dict(self) -> dict[str, object]:
        return {
            "ticket_id": self.ticket_id,
            "ticket_sha256": self.ticket_sha256,
            "unit_id": self.unit_id,
            "shot_id": self.shot_id,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
            "repair_action": self.repair_action.value,
            "source_media_sha256": self.source_media_sha256,
            "provider_prompt_sha256": self.provider_prompt_sha256,
            "reference_sha256": list(self.reference_sha256),
        }


@dataclass(frozen=True)
class H3ShotRepairExecutionResult:
    ticket_id: str
    shot_id: str
    repair_action: str
    provider_recalled: bool
    provider_calls: int
    source_media_sha256: str
    provider_shot_sha256: str
    output_media_sha256: str
    output_media_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "ticket_id": self.ticket_id,
            "shot_id": self.shot_id,
            "repair_action": self.repair_action,
            "provider_recalled": self.provider_recalled,
            "provider_calls": self.provider_calls,
            "source_media_sha256": self.source_media_sha256,
            "provider_shot_sha256": self.provider_shot_sha256,
            "output_media_sha256": self.output_media_sha256,
            "output_media_path": self.output_media_path,
        }


H3ShotProviderRunner = Callable[[H3ShotRepairRequest], Path]
H3ShotAssemblyRunner = Callable[[Path, Path, Path, H3ShotRepairRequest], None]


_PROVIDER_SHOT_ACTIONS = {
    H3RepairAction.REGENERATE_SHOT,
    H3RepairAction.RECOMPILE_DIALOGUE_DETACHED,
    H3RepairAction.REGENERATE_WITH_IDENTITY_BRIDGE,
}


def build_h3_shot_repair_request(
    ticket: H3RepairTicket,
    approval: H3ProviderRepairApproval,
) -> H3ShotRepairRequest:
    validate_provider_repair_approval(ticket, approval)
    if ticket.scope_kind is not H3RepairScopeKind.SHOT:
        raise RuntimeError("provider repair request must be shot-scoped")
    if ticket.shot_id is None or ticket.start_seconds is None or ticket.end_seconds is None:
        raise RuntimeError("provider repair ticket is missing shot scope")
    try:
        action = H3RepairAction(ticket.repair_action)
    except ValueError as exc:
        raise RuntimeError(f"unknown provider repair action: {ticket.repair_action}") from exc
    if action not in _PROVIDER_SHOT_ACTIONS:
        raise RuntimeError(f"repair action is not a shot provider action: {action.value}")
    return H3ShotRepairRequest(
        ticket_id=ticket.ticket_id,
        ticket_sha256=ticket.ticket_sha256,
        unit_id=ticket.unit_id,
        shot_id=ticket.shot_id,
        start_seconds=ticket.start_seconds,
        end_seconds=ticket.end_seconds,
        repair_action=action,
        source_media_sha256=ticket.source_media_sha256,
        provider_prompt_sha256=ticket.provider_prompt_sha256,
        reference_sha256=ticket.reference_sha256,
    )


def execute_h3_shot_scoped_provider_repair(
    *,
    ticket: H3RepairTicket,
    approval: H3ProviderRepairApproval,
    source_unit_media: Path,
    output_unit_media: Path,
    provider_runner: H3ShotProviderRunner,
    assembly_runner: H3ShotAssemblyRunner,
) -> H3ShotRepairExecutionResult:
    """Execute one explicitly approved shot repair and deterministic reassembly.

    The source media SHA is rechecked before the injected provider runner executes. This
    prevents an approval for one artifact version from being replayed against a newer unit.
    The provider runner is invoked exactly once; multi-shot failures therefore require
    independent tickets and independent approvals.
    """

    request = build_h3_shot_repair_request(ticket, approval)
    if not source_unit_media.is_file() or source_unit_media.stat().st_size == 0:
        raise FileNotFoundError(source_unit_media)
    actual_source_sha = sha256_file(source_unit_media)
    if actual_source_sha != request.source_media_sha256:
        raise RuntimeError(
            "source unit media changed after repair ticket creation; provider execution blocked"
        )

    provider_shot = provider_runner(request)
    if not provider_shot.is_file() or provider_shot.stat().st_size == 0:
        raise RuntimeError("approved provider repair produced no shot media")

    assembly_runner(
        source_unit_media,
        provider_shot,
        output_unit_media,
        request,
    )
    if not output_unit_media.is_file() or output_unit_media.stat().st_size == 0:
        raise RuntimeError("shot-scoped repair assembly produced no unit media")

    return H3ShotRepairExecutionResult(
        ticket_id=request.ticket_id,
        shot_id=request.shot_id,
        repair_action=request.repair_action.value,
        provider_recalled=True,
        provider_calls=1,
        source_media_sha256=actual_source_sha,
        provider_shot_sha256=sha256_file(provider_shot),
        output_media_sha256=sha256_file(output_unit_media),
        output_media_path=str(output_unit_media),
    )
