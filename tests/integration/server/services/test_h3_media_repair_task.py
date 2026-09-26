from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.reference_video.h3_media_pipeline import (
    EvidenceChain,
    H3MediaPipelineError,
    RepairAction,
    sha256_file,
    write_provider_evidence_chain,
)
from lib.reference_video.h3_repair_task import H3RepairTaskPlan
from lib.version_manager import VersionManager


def _make_video(path: Path, *, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x180:rate=24:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=32000:duration={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "32000",
            "-ac",
            "2",
            "-shortest",
            str(path),
        ],
        check=True,
    )


def _pixel_payload(source_sha256: str) -> dict:
    return {
        "expected_source_sha256": source_sha256,
        "observations": [
            {
                "kind": "local_ui_text",
                "shot_id": "S1",
                "start_sec": 0,
                "end_sec": 1,
                "detail": "reviewed local UI contamination",
            }
        ],
        "action": "deterministic_pixel_sanitization",
        "regions": [
            {
                "shot_id": "S1",
                "start_sec": 0,
                "end_sec": 1,
                "x": 10,
                "y": 10,
                "width": 80,
                "height": 50,
                "blur_radius": 12,
                "opacity": 1,
            }
        ],
    }


def test_h3_repair_task_plan_uses_shared_qa_planner() -> None:
    plan = H3RepairTaskPlan.from_payload(_pixel_payload("a" * 64))
    assert plan.action == RepairAction.DETERMINISTIC_PIXEL_SANITIZATION


def test_h3_repair_task_rejects_semantic_regeneration() -> None:
    payload = {
        "expected_source_sha256": "a" * 64,
        "observations": [{"kind": "identity_mismatch", "shot_id": "S1"}],
    }
    with pytest.raises(H3MediaPipelineError, match="not executable"):
        H3RepairTaskPlan.from_payload(payload)


def test_h3_repair_task_rejects_declared_action_that_disagrees_with_planner() -> None:
    payload = _pixel_payload("a" * 64)
    payload["action"] = "deterministic_av_retime"
    with pytest.raises(H3MediaPipelineError, match="does not match QA planner"):
        H3RepairTaskPlan.from_payload(payload)


def test_evidence_chain_round_trip_revalidates_hash_graph(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"provider")
    chain = write_provider_evidence_chain(
        unit_id="E1U1",
        provider_output=source,
        provider_prompt="prompt",
        provider_id="autodl",
        model_id="minimax_h3",
        requested_resolution="480p",
        requested_duration_seconds=5,
        output_path=tmp_path / "evidence.json",
    )
    loaded = EvidenceChain.from_json(chain.to_json())
    assert loaded == chain

    raw = json.loads(chain.to_json())
    raw["nodes"][0]["stage"] = "deterministic_av_retime"
    with pytest.raises(H3MediaPipelineError, match="evidence roots"):
        EvidenceChain.from_json(json.dumps(raw))


@pytest.mark.asyncio
async def test_production_h3_repair_selects_local_derived_version_and_extends_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = tmp_path / "demo"
    current = project_path / "reference_videos" / "E1U1.mp4"
    _make_video(current)
    source_sha256 = sha256_file(current)

    evidence_path = project_path / "reference_videos" / "evidence" / "E1U1.json"
    write_provider_evidence_chain(
        unit_id="E1U1",
        provider_output=current,
        provider_prompt="provider prompt",
        provider_id="autodl",
        model_id="minimax_h3",
        requested_resolution="480p",
        requested_duration_seconds=1,
        output_path=evidence_path,
    )
    versions = VersionManager(project_path)
    assert versions.add_version(
        "reference_videos",
        "E1U1",
        "provider prompt",
        source_file=current,
        provider_id="autodl",
    ) == 1

    from server.services import h3_media_repair_tasks as service

    fake_pm = SimpleNamespace(get_project_path=lambda _project_name: project_path)
    monkeypatch.setattr(service, "get_project_manager", lambda: fake_pm)

    result = await service.execute_h3_media_repair_task(
        "demo",
        "E1U1",
        _pixel_payload(source_sha256),
        user_id="u1",
        task_id="repair-1",
    )

    assert result["version"] == 2
    assert result["provider_recalled"] is False
    assert result["repair_action"] == "deterministic_pixel_sanitization"
    assert result["source_sha256"] == source_sha256
    assert result["output_sha256"] == sha256_file(current)
    assert result["output_sha256"] != source_sha256

    chain = EvidenceChain.from_json(evidence_path.read_text(encoding="utf-8"))
    assert len(chain.nodes) == 2
    assert chain.nodes[-1].stage == "deterministic_pixel_sanitization"
    assert chain.nodes[-1].parent_sha256 == (source_sha256,)
    assert chain.nodes[-1].metadata["provider_recalled"] is False
    assert versions.get_versions("reference_videos", "E1U1")["current_version"] == 2


@pytest.mark.asyncio
async def test_production_h3_repair_fails_closed_when_reviewed_source_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = tmp_path / "demo"
    current = project_path / "reference_videos" / "E1U1.mp4"
    _make_video(current)

    from server.services import h3_media_repair_tasks as service

    fake_pm = SimpleNamespace(get_project_path=lambda _project_name: project_path)
    monkeypatch.setattr(service, "get_project_manager", lambda: fake_pm)

    with pytest.raises(H3MediaPipelineError, match="changed after QA"):
        await service.execute_h3_media_repair_task(
            "demo",
            "E1U1",
            _pixel_payload("0" * 64),
            user_id="u1",
            task_id="repair-stale",
        )
