from __future__ import annotations

from pathlib import Path

import pytest

from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_runtime_gate import (
    H3RuntimeSelectionError,
    run_h3_runtime_selection_gate,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
)


def _finding(
    *,
    tags: tuple[str, ...],
    provider_result_usable: bool = True,
    audio_is_accepted: bool = True,
    affected_fraction: float = 0.05,
) -> MediaQAFinding:
    return MediaQAFinding(
        unit_id="E11U02",
        canonical_violation="runtime test finding",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=provider_result_usable,
        audio_is_accepted=audio_is_accepted,
        repairability=MediaQARepairability.DETERMINISTIC,
        affected_fraction=affected_fraction,
        tags=tags,
    )


@pytest.mark.asyncio
async def test_runtime_gate_passes_clean_media_without_repair(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"clean-provider-media")

    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return ()

    result = await run_h3_runtime_selection_gate(
        staged,
        evaluator=evaluator,
        repair_handlers={},
    )

    assert result.status == "PASS"
    assert result.provider_recalled is False
    assert result.repair_passes == 0
    assert result.source_media_sha256 == result.final_media_sha256


@pytest.mark.asyncio
async def test_runtime_gate_repairs_then_reqa_passes(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"provider-media-with-local-text")

    async def evaluator(path: Path) -> tuple[MediaQAFinding, ...]:
        if b"repaired" in path.read_bytes():
            return ()
        return (_finding(tags=("noncanonical_text",)),)

    repair_calls = 0

    def repair(path: Path, _plan) -> None:
        nonlocal repair_calls
        repair_calls += 1
        path.write_bytes(path.read_bytes() + b"-repaired")

    result = await run_h3_runtime_selection_gate(
        staged,
        evaluator=evaluator,
        repair_handlers={
            H3RepairAction.DETERMINISTIC_SURFACE_REPAIR: repair,
        },
    )

    assert repair_calls == 1
    assert result.status == "PASS"
    assert result.provider_recalled is False
    assert result.repair_passes == 1
    assert result.source_media_sha256 != result.final_media_sha256
    assert result.passes[0]["executed_repairs"][0]["provider_recalled"] is False
    assert result.passes[1]["findings"] == []


@pytest.mark.asyncio
async def test_runtime_gate_provider_route_fails_closed_without_recall(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"semantic-failure")

    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return (
            _finding(
                tags=("invented_content",),
                provider_result_usable=False,
                audio_is_accepted=False,
                affected_fraction=1.0,
            ),
        )

    with pytest.raises(H3RuntimeSelectionError) as exc:
        await run_h3_runtime_selection_gate(
            staged,
            evaluator=evaluator,
            repair_handlers={},
        )

    assert exc.value.code == "h3_provider_repair_required"
    assert exc.value.report["provider_recalled"] is False
    assert exc.value.report["status"] == "PROVIDER_REPAIR_REQUIRED"


@pytest.mark.asyncio
async def test_runtime_gate_unknown_failure_escalates_without_provider(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"unknown-failure")

    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return (_finding(tags=("unrecognized_fact",)),)

    with pytest.raises(H3RuntimeSelectionError) as exc:
        await run_h3_runtime_selection_gate(
            staged,
            evaluator=evaluator,
            repair_handlers={},
        )

    assert exc.value.code == "h3_media_qa_escalation_required"
    assert exc.value.report["provider_recalled"] is False


@pytest.mark.asyncio
async def test_runtime_gate_missing_deterministic_handler_fails_closed(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"repairable")

    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return (_finding(tags=("noncanonical_text",)),)

    with pytest.raises(H3RuntimeSelectionError) as exc:
        await run_h3_runtime_selection_gate(
            staged,
            evaluator=evaluator,
            repair_handlers={},
        )

    assert exc.value.code == "h3_deterministic_repair_handler_missing"


@pytest.mark.asyncio
async def test_runtime_gate_detects_no_progress(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"unchanged")

    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return (_finding(tags=("noncanonical_text",)),)

    def no_op(_path: Path, _plan) -> None:
        return None

    with pytest.raises(H3RuntimeSelectionError) as exc:
        await run_h3_runtime_selection_gate(
            staged,
            evaluator=evaluator,
            repair_handlers={
                H3RepairAction.DETERMINISTIC_SURFACE_REPAIR: no_op,
            },
        )

    assert exc.value.code == "h3_deterministic_repair_no_progress"
    assert exc.value.report["status"] == "NO_REPAIR_PROGRESS"


@pytest.mark.asyncio
async def test_runtime_gate_bounds_repair_iterations(tmp_path: Path) -> None:
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"round0")

    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return (_finding(tags=("noncanonical_text",)),)

    def mutate(path: Path, _plan) -> None:
        path.write_bytes(path.read_bytes() + b"-next")

    with pytest.raises(H3RuntimeSelectionError) as exc:
        await run_h3_runtime_selection_gate(
            staged,
            evaluator=evaluator,
            repair_handlers={
                H3RepairAction.DETERMINISTIC_SURFACE_REPAIR: mutate,
            },
            max_repair_passes=1,
        )

    assert exc.value.code == "h3_media_qa_unresolved"
    assert exc.value.report["provider_recalled"] is False
    assert len(exc.value.report["passes"]) == 2
