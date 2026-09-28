from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import (
    H3ProviderRepairApproval,
    H3RepairScopeKind,
    H3RepairTicketContext,
    H3RepairTicketStatus,
    H3ShotRepairContext,
    build_h3_repair_ticket,
    validate_provider_repair_approval,
)
from lib.reference_video.h3_shot_repair_executor import (
    build_h3_shot_repair_request,
    execute_h3_shot_scoped_provider_repair,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)


def _provider_finding(
    *,
    unit_id: str = "E12U06",
    shot_id: str | None = "E12U06-S02",
    start: float | None = 5.0,
    end: float | None = 10.0,
    failure_class: H3FailureClass = H3FailureClass.LARGE_SEMANTIC_FAILURE,
) -> MediaQAFinding:
    time_range = (
        MediaQATimeRange(start_seconds=start, end_seconds=end)
        if start is not None and end is not None
        else None
    )
    return MediaQAFinding(
        unit_id=unit_id,
        shot_id=shot_id,
        time_range=time_range,
        canonical_violation="provider invented non-canonical semantic content",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=0.5,
        failure_class=failure_class,
        evidence_frames=(180,),
        tags=("semantic_failure",),
    )


def test_provider_ticket_is_approval_eligible_only_when_shot_scoped() -> None:
    source_sha = "1" * 64
    plan = plan_h3_auto_repair(_provider_finding())
    ticket = build_h3_repair_ticket(
        plan,
        source_media_sha256=source_sha,
        context=H3RepairTicketContext(
            provider_prompt_sha256="2" * 64,
            reference_sha256=("3" * 64,),
        ),
    )

    assert ticket.status is H3RepairTicketStatus.AWAITING_APPROVAL
    assert ticket.approval_eligible is True
    assert ticket.scope_kind is H3RepairScopeKind.SHOT
    assert ticket.shot_id == "E12U06-S02"
    assert ticket.repair_action == H3RepairAction.REGENERATE_SHOT.value

    unscoped = build_h3_repair_ticket(
        plan_h3_auto_repair(_provider_finding(shot_id=None, start=None, end=None)),
        source_media_sha256=source_sha,
    )
    assert unscoped.status is H3RepairTicketStatus.HUMAN_REVIEW_REQUIRED
    assert unscoped.approval_eligible is False
    assert unscoped.scope_kind is H3RepairScopeKind.UNRESOLVED


def test_shot_context_overrides_unit_prompt_and_reference_hashes() -> None:
    ticket = build_h3_repair_ticket(
        plan_h3_auto_repair(_provider_finding()),
        source_media_sha256="1" * 64,
        context=H3RepairTicketContext(
            provider_prompt_sha256="2" * 64,
            reference_sha256=("3" * 64,),
            shot_contexts=(
                H3ShotRepairContext(
                    shot_id="E12U06-S02",
                    provider_prompt_sha256="4" * 64,
                    reference_sha256=("5" * 64, "6" * 64),
                ),
            ),
        ),
    )

    assert ticket.provider_prompt_sha256 == "4" * 64
    assert ticket.reference_sha256 == ("5" * 64, "6" * 64)


def test_unknown_escalation_never_becomes_provider_approval_eligible() -> None:
    finding = MediaQAFinding(
        unit_id="E99U99",
        canonical_violation="unclassified media anomaly",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=False,
        repairability=MediaQARepairability.HUMAN_REVIEW,
        failure_class=H3FailureClass.UNKNOWN,
    )
    ticket = build_h3_repair_ticket(
        plan_h3_auto_repair(finding),
        source_media_sha256="1" * 64,
    )

    assert ticket.repair_action == H3RepairAction.ESCALATE.value
    assert ticket.provider_recall_required is False
    assert ticket.approval_eligible is False
    assert ticket.status is H3RepairTicketStatus.HUMAN_REVIEW_REQUIRED


def test_shot_executor_requires_exact_approval_and_source_sha(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    provider_shot = tmp_path / "shot.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"source-unit-media")
    provider_shot.write_bytes(b"replacement-shot")

    ticket = build_h3_repair_ticket(
        plan_h3_auto_repair(_provider_finding()),
        source_media_sha256=sha256_file(source),
        context=H3RepairTicketContext(provider_prompt_sha256="2" * 64),
    )
    approval = H3ProviderRepairApproval(
        ticket_id=ticket.ticket_id,
        ticket_sha256=ticket.ticket_sha256,
        source_media_sha256=ticket.source_media_sha256,
        shot_id="E12U06-S02",
        approved_by="ci-contract-test",
        approved_at="2026-09-28T00:00:00Z",
    )
    validate_provider_repair_approval(ticket, approval)
    request = build_h3_shot_repair_request(ticket, approval)
    assert request.duration_seconds == 5.0

    provider_calls: list[str] = []

    def provider_runner(_request):
        provider_calls.append(_request.shot_id)
        return provider_shot

    def assembly_runner(source_media, shot_media, output_media, _request):
        assert source_media == source
        assert shot_media == provider_shot
        shutil.copy2(source_media, output_media)
        with output_media.open("ab") as handle:
            handle.write(b"|assembled|" + shot_media.read_bytes())

    result = execute_h3_shot_scoped_provider_repair(
        ticket=ticket,
        approval=approval,
        source_unit_media=source,
        output_unit_media=output,
        provider_runner=provider_runner,
        assembly_runner=assembly_runner,
    )
    assert provider_calls == ["E12U06-S02"]
    assert result.provider_recalled is True
    assert result.provider_calls == 1
    assert result.shot_id == "E12U06-S02"

    source.write_bytes(b"changed-after-ticket")
    with pytest.raises(RuntimeError, match="changed after repair ticket creation"):
        execute_h3_shot_scoped_provider_repair(
            ticket=ticket,
            approval=approval,
            source_unit_media=source,
            output_unit_media=output,
            provider_runner=provider_runner,
            assembly_runner=assembly_runner,
        )
    assert provider_calls == ["E12U06-S02"]


def test_scope_mismatch_blocks_before_provider_execution(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    ticket = build_h3_repair_ticket(
        plan_h3_auto_repair(_provider_finding()),
        source_media_sha256=sha256_file(source),
    )
    wrong = H3ProviderRepairApproval(
        ticket_id=ticket.ticket_id,
        ticket_sha256=ticket.ticket_sha256,
        source_media_sha256=ticket.source_media_sha256,
        shot_id="E12U06-S01",
        approved_by="ci-contract-test",
        approved_at="2026-09-28T00:00:00Z",
    )

    with pytest.raises(RuntimeError, match="shot scope"):
        build_h3_shot_repair_request(ticket, wrong)
