from pathlib import Path

import pytest

from lib.reference_video.h3_media_pipeline import (
    EvidenceChain,
    EvidenceNode,
    H3MediaPipelineError,
    MediaObservation,
    ObservationKind,
    RepairRegion,
    RepairRequest,
    TimelineSegment,
    classify_media_observations,
    validate_repair_request,
    write_provider_evidence_chain,
)
from lib.reference_video.h3_production_policy import MediaIssueCode, RepairAction


def test_e13u01_qa_classifies_exact_text_to_text_plate() -> None:
    decision = classify_media_observations(
        [MediaObservation(ObservationKind.EXACT_TEXT_MISMATCH, shot_id="E13U01-S02")]
    )
    assert decision.issues == (MediaIssueCode.EXACT_TEXT_MISSING_OR_WRONG,)
    assert decision.action == RepairAction.DETERMINISTIC_TEXT_PLATE
    assert decision.provider_recall_allowed is False


def test_e11u02_qa_classifies_local_text_to_pixel_sanitization() -> None:
    decision = classify_media_observations(
        [
            MediaObservation(ObservationKind.UNEXPECTED_READABLE_TEXT, shot_id="E11U02-S01"),
            MediaObservation(ObservationKind.LOCAL_UI_TEXT, shot_id="E11U02-S02"),
        ]
    )
    assert decision.action == RepairAction.DETERMINISTIC_PIXEL_SANITIZATION
    assert decision.provider_recall_allowed is False


def test_e15u03_qa_classifies_av_drift_to_retime() -> None:
    decision = classify_media_observations(
        [
            MediaObservation(ObservationKind.SHOT_BOUNDARY_DRIFT, start_sec=4.9167),
            MediaObservation(ObservationKind.AUDIO_BOUNDARY_DRIFT, start_sec=9.25),
        ]
    )
    assert decision.action == RepairAction.DETERMINISTIC_AV_RETIME
    assert decision.provider_recall_allowed is False


def test_semantic_failure_is_only_class_allowed_to_request_regeneration() -> None:
    decision = classify_media_observations(
        [MediaObservation(ObservationKind.IDENTITY_MISMATCH, shot_id="S2")]
    )
    assert decision.action == RepairAction.REGENERATE_SHOT
    assert decision.provider_recall_allowed is True


def test_pixel_repair_requires_explicit_local_region() -> None:
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
        source_path=Path("source.mp4"),
        output_path=Path("repair.mp4"),
        regions=(
            RepairRegion(
                shot_id="S1",
                start_sec=0,
                end_sec=5,
                x=10,
                y=20,
                width=100,
                height=50,
            ),
        ),
    )
    validate_repair_request(request)


def test_av_retime_requires_explicit_source_segments() -> None:
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_AV_RETIME,
        source_path=Path("source.mp4"),
        output_path=Path("repair.mp4"),
        timeline=(
            TimelineSegment(0, 118 / 24, 5),
            TimelineSegment(118 / 24, 222 / 24, 5),
            TimelineSegment(222 / 24, 342 / 24, 5),
        ),
    )
    validate_repair_request(request)


def test_repair_never_overwrites_supplier_evidence() -> None:
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_TEXT_PLATE,
        source_path=Path("same.mp4"),
        output_path=Path("same.mp4"),
        exact_text=("联合创始人",),
    )
    with pytest.raises(H3MediaPipelineError, match="must not overwrite"):
        validate_repair_request(request)


def test_regeneration_cannot_run_inside_deterministic_repair_stage() -> None:
    request = RepairRequest(
        action=RepairAction.REGENERATE_SHOT,
        source_path=Path("source.mp4"),
        output_path=Path("repair.mp4"),
    )
    with pytest.raises(H3MediaPipelineError, match="cannot execute"):
        validate_repair_request(request)


def test_evidence_chain_is_hash_linked_and_rejects_unknown_parent(tmp_path: Path) -> None:
    source = tmp_path / "supplier.mp4"
    source.write_bytes(b"supplier")
    repaired = tmp_path / "repaired.mp4"
    repaired.write_bytes(b"repaired")

    supplier = EvidenceNode.create(
        stage="provider_output",
        artifact_path=source,
        metadata={"provider": "autodl"},
    )
    repair = EvidenceNode.create(
        stage="deterministic_repair",
        artifact_path=repaired,
        parent_sha256=(supplier.artifact_sha256,),
        metadata={"action": "deterministic_av_retime"},
    )
    chain = EvidenceChain(unit_id="E15U03", nodes=(supplier, repair))
    chain.validate()
    assert '"unit_id": "E15U03"' in chain.to_json()

    bad = EvidenceChain(
        unit_id="BAD",
        nodes=(
            supplier,
            EvidenceNode.create(
                stage="bad_repair",
                artifact_path=repaired,
                parent_sha256=("0" * 64,),
            ),
        ),
    )
    with pytest.raises(H3MediaPipelineError, match="parent hash"):
        bad.validate()


def test_provider_success_writes_phase2_root_evidence(tmp_path: Path) -> None:
    provider = tmp_path / "provider.mp4"
    provider.write_bytes(b"paid-provider-output")
    sidecar = tmp_path / "evidence" / "E13U03.json"
    chain = write_provider_evidence_chain(
        unit_id="E13U03",
        provider_output=provider,
        provider_prompt="zero-text visual prompt",
        provider_id="autodl",
        model_id="minimax_h3_zm_u24",
        requested_resolution="480p横",
        requested_duration_seconds=15,
        output_path=sidecar,
    )
    assert sidecar.is_file()
    assert chain.nodes[0].stage == "provider_output"
    assert chain.nodes[0].artifact_sha256
    payload = sidecar.read_text(encoding="utf-8")
    assert "provider_prompt_sha256" in payload
    assert "zero-text visual prompt" not in payload
