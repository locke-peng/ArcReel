from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lib.reference_video import cut_detector
from lib.reference_video.evidence_schema import H3EvidenceRecord
from lib.reference_video.h3_failure_classifier import classify_h3_media_finding
from lib.reference_video.h3_production_policy import (
    H3FailureClass,
    H3MediaFailure,
    H3RepairAction,
    plan_h3_media_repair,
)
from lib.reference_video.h3_repair_executor import execute_h3_media_repair, sha256_file
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)


def _finding(
    *,
    unit_id: str,
    failure_class: H3FailureClass | None = None,
    tags: tuple[str, ...] = (),
    affected_fraction: float = 0.05,
    provider_result_usable: bool = True,
    audio_is_accepted: bool = True,
) -> MediaQAFinding:
    return MediaQAFinding(
        unit_id=unit_id,
        shot_id=f"{unit_id}-S1",
        time_range=MediaQATimeRange(0.0, 5.0),
        region="screen",
        failure_class=failure_class,
        canonical_violation="structured test finding",
        severity=MediaQASeverity.ERROR,
        evidence_frames=(12, 24),
        provider_result_usable=provider_result_usable,
        audio_is_accepted=audio_is_accepted,
        repairability=MediaQARepairability.DETERMINISTIC,
        affected_fraction=affected_fraction,
        tags=tags,
    )


def test_media_qa_schema_reuses_phase3_failure_enum() -> None:
    finding = _finding(
        unit_id="E11U02",
        failure_class=H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
    )
    assert finding.failure_class is H3FailureClass.LOCAL_NONCANONICAL_SURFACE
    assert finding.to_dict()["failure_class"] == "local_noncanonical_surface"


def test_classifier_maps_e11u02_to_existing_phase3_policy() -> None:
    failure = classify_h3_media_finding(
        _finding(unit_id="E11U02", tags=("noncanonical_text",))
    )
    assert failure.failure_class is H3FailureClass.LOCAL_NONCANONICAL_SURFACE

    decision = plan_h3_media_repair(failure)
    assert decision.action is H3RepairAction.DETERMINISTIC_SURFACE_REPAIR
    assert decision.provider_recall_required is False
    assert decision.preserve_audio_bitstream is True


def test_classifier_maps_e15u03_timeline_to_existing_phase3_policy() -> None:
    failure = classify_h3_media_finding(
        _finding(
            unit_id="E15U03",
            tags=("cut_timing",),
            affected_fraction=1.0,
        )
    )
    assert failure.failure_class is H3FailureClass.TIMELINE_ONLY_FAILURE

    decision = plan_h3_media_repair(failure)
    assert decision.action is H3RepairAction.DETERMINISTIC_AV_RETIME
    assert decision.provider_recall_required is False


def test_classifier_fails_closed_on_conflicting_tags() -> None:
    failure = classify_h3_media_finding(
        _finding(
            unit_id="X",
            tags=("cut_timing", "identity_drift"),
        )
    )
    assert failure.failure_class is H3FailureClass.UNKNOWN
    assert plan_h3_media_repair(failure).action is H3RepairAction.ESCALATE


def test_executor_runs_deterministic_action_without_provider_recall(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"source-media")

    decision = plan_h3_media_repair(
        H3MediaFailure(
            H3FailureClass.LOCAL_NONCANONICAL_SURFACE,
            affected_fraction=0.05,
            provider_result_usable=True,
            audio_is_accepted=True,
        )
    )

    provider_calls = 0

    def deterministic_runner() -> None:
        output.write_bytes(b"repaired-media")

    def provider_runner() -> None:
        nonlocal provider_calls
        provider_calls += 1

    result = execute_h3_media_repair(
        decision,
        source_media=(source,),
        output_media=output,
        deterministic_runner=deterministic_runner,
        provider_runner=provider_runner,
    )

    assert result.provider_recalled is False
    assert provider_calls == 0
    assert result.source_media_sha256 == (sha256_file(source),)
    assert result.output_media_sha256 == sha256_file(output)


def test_executor_fails_closed_when_policy_requires_provider(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-media")
    output = tmp_path / "output.mp4"

    decision = plan_h3_media_repair(
        H3MediaFailure(H3FailureClass.IDENTITY_CONTINUITY_FAILURE)
    )
    with pytest.raises(RuntimeError, match="provider execution is disabled"):
        execute_h3_media_repair(
            decision,
            source_media=(source,),
            output_media=output,
            deterministic_runner=lambda: None,
        )


def test_cut_detector_uses_actual_scene_score_peak_near_canonical_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"fake")

    monkeypatch.setattr(cut_detector, "_probe_fps", lambda _: 24.0)
    monkeypatch.setattr(
        cut_detector,
        "_scene_scores",
        lambda _path, _fps: [
            (117, 117 / 24, 0.10),
            (118, 118 / 24, 0.91),
            (119, 119 / 24, 0.08),
            (221, 221 / 24, 0.14),
            (222, 222 / 24, 0.88),
            (223, 223 / 24, 0.11),
        ],
    )

    cuts = cut_detector.detect_expected_cuts(
        media,
        target_cut_frames=(120, 240),
        search_radius_frames=24,
        min_scene_score=0.20,
    )

    assert [cut.actual_cut_frame for cut in cuts] == [118, 222]
    assert [cut.delta_frames for cut in cuts] == [-2, -18]
    assert cuts[0].target_cut_time == 5.0
    assert cuts[1].target_cut_time == 10.0


def test_evidence_records_form_verifiable_hash_chain() -> None:
    first = H3EvidenceRecord(
        unit_id="E11U02",
        stage="pre_repair",
        tested_sha="a" * 40,
        repair_action="deterministic_surface_repair",
        provider_recalled=False,
        qa_verdict="FAIL_REPAIRABLE",
        source_media_sha256=("1" * 64,),
        pre_media_sha256="1" * 64,
    ).sealed()
    first.verify()

    second = H3EvidenceRecord(
        unit_id="E11U02",
        stage="post_repair",
        tested_sha="a" * 40,
        repair_action="deterministic_surface_repair",
        provider_recalled=False,
        qa_verdict="PASS",
        source_media_sha256=("1" * 64,),
        pre_media_sha256="1" * 64,
        post_media_sha256="2" * 64,
        previous_record_sha256=first.record_sha256,
    ).sealed()
    second.verify()
    assert second.previous_record_sha256 == first.record_sha256

    tampered = replace(second, qa_verdict="FAIL")
    with pytest.raises(ValueError, match="hash mismatch"):
        tampered.verify()
