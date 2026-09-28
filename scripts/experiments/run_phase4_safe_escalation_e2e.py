"""Phase 4 safe-escalation replay using existing E12U06 and E13U03 evidence.

This acceptance never calls MiniMax. It verifies SHA-pinned historical media and prompts,
injects trusted structured QA findings that represent non-deterministic failures, and
asserts that the production runtime emits shot-scoped repair tickets while provider recall
remains disabled.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

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

E12_RUN_ID = 36013839904
E12_ARTIFACT_ID = 10813677092
E12_VIDEO_SHA256 = "3b1f445009afe1858fd65743d3c55ef2952140e5298246384c287fd9f164cdea"
E12_PROMPT_SHA256 = "4c3e7fdcb8aedf106779e2a926242a241a9bd1048b214123c9fb0ffe32586aed"
E12_CANONICAL_REFERENCE_SHA256 = "7b296bcbd21fdc1ef4792649c6062355c568bf64c2756a9319d86048d38a3762"
E12_RUNTIME_REFERENCE_SHA256 = "a897be2ad9a8da1673861eedb7fb54115d4d9b4859168fd6cccebb4a9b85a4ed"

E13_RUN_ID = 36128343054
E13_ARTIFACT_ID = 10860882490
E13_FINAL_SHA256 = "63a1238ae14161e7549fc9927adc611a3ba3aa7b6879c9050bac9a7a2fdf7b58"
E13_SHOT2_PROMPT_SHA256 = "0d446c1979e00916a3fa113ea2755d551f35469d5c986927f9929ded3b63d91c"
E13_SHOT3_PROMPT_SHA256 = "7584d77c759307cbc2da21376d1cddddb5677353673398553bb200cbf6179a2f"
E13_C01_BRIDGE_SHA256 = "fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135"
E13_CONSOLE_REFERENCE_SHA256 = "885c2d20cc8337932c5206b1fe973b9f9c573a45158e97c8527e29019dbb29ba"
E13_LOG_REFERENCE_SHA256 = "98b57d04ccf909451bdc172c9324f109c1f0b2cc519a2ef05220f6d3b0e6c3e6"


def _require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA mismatch: {actual} != {expected}")


def _finding(
    *,
    unit_id: str,
    shot_id: str,
    start_seconds: float,
    end_seconds: float,
    failure_class: H3FailureClass,
    violation: str,
    affected_fraction: float,
    evidence_frames: tuple[int, ...],
) -> MediaQAFinding:
    return MediaQAFinding(
        unit_id=unit_id,
        shot_id=shot_id,
        time_range=MediaQATimeRange(
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        ),
        canonical_violation=violation,
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=affected_fraction,
        failure_class=failure_class,
        evidence_frames=evidence_frames,
        tags=("existing_evidence_replay", "provider_repair_required"),
    )


async def _capture_provider_ticket_report(
    media: Path,
    *,
    findings: tuple[MediaQAFinding, ...],
    context: H3RepairTicketContext,
) -> dict[str, Any]:
    async def evaluator(_media: Path) -> tuple[MediaQAFinding, ...]:
        return findings

    try:
        await run_h3_runtime_selection_gate(
            media,
            evaluator=evaluator,
            repair_handlers={},
            repair_ticket_context=context,
        )
    except H3RuntimeSelectionError as exc:
        if exc.code != "h3_provider_repair_required":
            raise
        return dict(exc.report)
    raise RuntimeError("provider-required fixture unexpectedly passed runtime selection")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e12-upstream-dir", type=Path, required=True)
    parser.add_argument("--e13-upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    tested_sha = os.environ.get("GITHUB_SHA", "").strip()
    if not tested_sha:
        raise RuntimeError("GITHUB_SHA is required for escalation acceptance evidence")

    e12_video = args.e12_upstream_dir / "project" / "reference_videos" / "E12U06.mp4"
    e12_prompt = args.e12_upstream_dir / "E12U06_final_provider_prompt.txt"
    _require_sha(e12_video, E12_VIDEO_SHA256, "E12U06 supplier video")
    _require_sha(e12_prompt, E12_PROMPT_SHA256, "E12U06 provider prompt")

    e12_report = await _capture_provider_ticket_report(
        e12_video,
        findings=(
            _finding(
                unit_id="E12U06",
                shot_id="E12U06-S02",
                start_seconds=5.0,
                end_seconds=10.0,
                failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
                violation=(
                    "historical supplier evidence introduced a non-canonical suited figure "
                    "in the stage-wing doorway beat"
                ),
                affected_fraction=0.5,
                evidence_frames=(180, 228),
            ),
        ),
        context=H3RepairTicketContext(
            provider_prompt_sha256=E12_PROMPT_SHA256,
            reference_sha256=(
                E12_CANONICAL_REFERENCE_SHA256,
                E12_RUNTIME_REFERENCE_SHA256,
            ),
            provider_run_id=E12_RUN_ID,
            provider_artifact_id=E12_ARTIFACT_ID,
        ),
    )
    e12_tickets = e12_report.get("repair_tickets") or []
    if len(e12_tickets) != 1:
        raise RuntimeError(f"E12U06 expected one repair ticket: {e12_report}")
    e12_ticket = e12_tickets[0]
    if e12_ticket.get("shot_id") != "E12U06-S02":
        raise RuntimeError(f"E12U06 ticket is not shot-scoped: {e12_ticket}")
    if e12_ticket.get("repair_action") != "regenerate_shot":
        raise RuntimeError(f"E12U06 unexpected repair action: {e12_ticket}")
    if e12_ticket.get("status") != "awaiting_approval":
        raise RuntimeError(f"E12U06 ticket is not approval-gated: {e12_ticket}")

    e13_video = args.e13_upstream_dir / "project" / "reference_videos" / "E13U03.mp4"
    e13_shot2_prompt = args.e13_upstream_dir / "E13U03_shot2_provider_prompt.txt"
    e13_shot3_prompt = args.e13_upstream_dir / "E13U03_shot3_provider_prompt.txt"
    _require_sha(e13_video, E13_FINAL_SHA256, "E13U03 accepted final")
    _require_sha(e13_shot2_prompt, E13_SHOT2_PROMPT_SHA256, "E13U03 shot2 prompt")
    _require_sha(e13_shot3_prompt, E13_SHOT3_PROMPT_SHA256, "E13U03 shot3 prompt")

    e13_report = await _capture_provider_ticket_report(
        e13_video,
        findings=(
            _finding(
                unit_id="E13U03",
                shot_id="E13U03-S07",
                start_seconds=5.0,
                end_seconds=10.0,
                failure_class=H3FailureClass.IDENTITY_CONTINUITY_FAILURE,
                violation="shot 07 identity regression fixture requires the existing identity bridge",
                affected_fraction=1.0 / 3.0,
                evidence_frames=(150,),
            ),
            _finding(
                unit_id="E13U03",
                shot_id="E13U03-S08",
                start_seconds=10.0,
                end_seconds=15.0,
                failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
                violation=(
                    "shot 08 semantic-log regression fixture represents invented literal "
                    "content where Canonical specifies semantic-only scrolling logs"
                ),
                affected_fraction=1.0 / 3.0,
                evidence_frames=(270,),
            ),
        ),
        context=H3RepairTicketContext(
            shot_contexts=(
                H3ShotRepairContext(
                    shot_id="E13U03-S07",
                    provider_prompt_sha256=E13_SHOT2_PROMPT_SHA256,
                    reference_sha256=(
                        E13_CONSOLE_REFERENCE_SHA256,
                        E13_C01_BRIDGE_SHA256,
                    ),
                ),
                H3ShotRepairContext(
                    shot_id="E13U03-S08",
                    provider_prompt_sha256=E13_SHOT3_PROMPT_SHA256,
                    reference_sha256=(
                        E13_LOG_REFERENCE_SHA256,
                        E13_C01_BRIDGE_SHA256,
                    ),
                ),
            ),
            provider_run_id=E13_RUN_ID,
            provider_artifact_id=E13_ARTIFACT_ID,
        ),
    )
    e13_tickets = e13_report.get("repair_tickets") or []
    if len(e13_tickets) != 2:
        raise RuntimeError(f"E13U03 expected two independent repair tickets: {e13_report}")
    if {item.get("shot_id") for item in e13_tickets} != {
        "E13U03-S07",
        "E13U03-S08",
    }:
        raise RuntimeError(f"E13U03 ticket scopes are wrong: {e13_tickets}")
    if len({item.get("ticket_id") for item in e13_tickets}) != 2:
        raise RuntimeError("E13U03 multi-shot failure collapsed into one repair ticket")
    if not all(item.get("approval_eligible") for item in e13_tickets):
        raise RuntimeError("E13U03 provider tickets must require explicit approval")

    report = {
        "status": "FINAL_PASS",
        "tested_sha": tested_sha,
        "provider_recalled": False,
        "paid_provider_calls": 0,
        "e12u06": {
            "source_media_sha256": sha256_file(e12_video),
            "runtime_gate_status": e12_report.get("status"),
            "repair_tickets": e12_tickets,
        },
        "e13u03": {
            "source_media_sha256": sha256_file(e13_video),
            "runtime_gate_status": e13_report.get("status"),
            "repair_tickets": e13_tickets,
            "ticket_count": len(e13_tickets),
            "shot_scopes": [item["shot_id"] for item in e13_tickets],
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "phase4_safe_escalation_e2e.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
