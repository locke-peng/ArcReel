from __future__ import annotations

from pathlib import Path

import pytest

from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import (
    H3RepairTicketContext,
    H3ShotRepairContext,
)
from lib.reference_video.h3_runtime_gate import (
    H3RuntimeSelectionError,
    run_h3_runtime_selection_gate,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)


def _finding(
    *,
    unit_id: str,
    shot_id: str,
    start: float,
    end: float,
    failure_class: H3FailureClass,
) -> MediaQAFinding:
    return MediaQAFinding(
        unit_id=unit_id,
        shot_id=shot_id,
        time_range=MediaQATimeRange(start_seconds=start, end_seconds=end),
        canonical_violation=f"{shot_id} violates Canonical semantics",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=(end - start) / 15.0,
        failure_class=failure_class,
        evidence_frames=(int(start * 24 + 6),),
        tags=("provider_repair_fixture",),
    )


@pytest.mark.asyncio
async def test_runtime_gate_emits_auditable_ticket_instead_of_recalling_provider(
    tmp_path: Path,
) -> None:
    media = tmp_path / "E12U06.mp4"
    media.write_bytes(b"paid-provider-result")

    async def evaluator(_media: Path):
        return (
            _finding(
                unit_id="E12U06",
                shot_id="E12U06-S02",
                start=5,
                end=10,
                failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
            ),
        )

    with pytest.raises(H3RuntimeSelectionError) as caught:
        await run_h3_runtime_selection_gate(
            media,
            evaluator=evaluator,
            repair_handlers={},
            repair_ticket_context=H3RepairTicketContext(
                provider_prompt_sha256="2" * 64,
                reference_sha256=("3" * 64,),
            ),
        )

    error = caught.value
    assert error.code == "h3_provider_repair_required"
    assert error.report["provider_recalled"] is False
    tickets = error.report["repair_tickets"]
    assert len(tickets) == 1
    assert tickets[0]["status"] == "awaiting_approval"
    assert tickets[0]["approval_eligible"] is True
    assert tickets[0]["shot_id"] == "E12U06-S02"
    assert tickets[0]["source_media_sha256"] == sha256_file(media)


@pytest.mark.asyncio
async def test_multishot_semantic_failure_produces_independent_shot_tickets(
    tmp_path: Path,
) -> None:
    media = tmp_path / "E13U03.mp4"
    media.write_bytes(b"accepted-unit-used-as-routing-fixture")

    async def evaluator(_media: Path):
        return (
            _finding(
                unit_id="E13U03",
                shot_id="E13U03-S07",
                start=5,
                end=10,
                failure_class=H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
            ),
            _finding(
                unit_id="E13U03",
                shot_id="E13U03-S08",
                start=10,
                end=15,
                failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
            ),
        )

    context = H3RepairTicketContext(
        shot_contexts=(
            H3ShotRepairContext(
                shot_id="E13U03-S07",
                provider_prompt_sha256="4" * 64,
                reference_sha256=("5" * 64,),
            ),
            H3ShotRepairContext(
                shot_id="E13U03-S08",
                provider_prompt_sha256="6" * 64,
                reference_sha256=("7" * 64,),
            ),
        ),
    )

    with pytest.raises(H3RuntimeSelectionError) as caught:
        await run_h3_runtime_selection_gate(
            media,
            evaluator=evaluator,
            repair_handlers={},
            repair_ticket_context=context,
        )

    tickets = caught.value.report["repair_tickets"]
    assert len(tickets) == 2
    assert {ticket["shot_id"] for ticket in tickets} == {
        "E13U03-S07",
        "E13U03-S08",
    }
    assert {ticket["provider_prompt_sha256"] for ticket in tickets} == {
        "4" * 64,
        "6" * 64,
    }
    assert len({ticket["ticket_id"] for ticket in tickets}) == 2
    assert all(ticket["scope_kind"] == "shot" for ticket in tickets)
    assert all(ticket["approval_eligible"] is True for ticket in tickets)
