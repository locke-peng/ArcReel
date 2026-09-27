from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.reference_video.h3_runtime_gate import H3RuntimeSelectionError
from lib.reference_video.media_qa_schema import MediaQAFinding
from lib.version_manager import PaidVersionCommit
from lib.video_artifact_facts import VIDEO_ARTIFACT_RESTORE_BLOCKER_FIELD
from server.services import reference_video_tasks, video_artifact_currency
from server.services.video_artifact_currency import VideoArtifactCommitter


@pytest.mark.asyncio
async def test_reference_video_builds_runtime_gate_only_for_h3_compiled_path(
    tmp_path: Path,
) -> None:
    async def evaluator(_path: Path) -> tuple[MediaQAFinding, ...]:
        return ()

    h3_gate = reference_video_tasks._build_h3_preselection_media_gate(
        payload={"prompt_compiler": "auto"},
        model_name="MiniMax-H3",
        has_references=False,
        evaluator=evaluator,
        repair_handlers={},
    )
    assert h3_gate is not None

    staged = tmp_path / "h3.mp4"
    staged.write_bytes(b"h3-provider-result")
    report = await h3_gate(staged, 8, {})
    assert report["status"] == "PASS"
    assert report["provider_recalled"] is False

    raw_gate = reference_video_tasks._build_h3_preselection_media_gate(
        payload={"prompt_compiler": "raw"},
        model_name="MiniMax-H3",
        has_references=False,
        evaluator=evaluator,
        repair_handlers={},
    )
    assert raw_gate is None

    non_h3_gate = reference_video_tasks._build_h3_preselection_media_gate(
        payload={"prompt_compiler": "auto"},
        model_name="another-video-model",
        has_references=False,
        evaluator=evaluator,
        repair_handlers={},
    )
    assert non_h3_gate is None


@pytest.mark.asyncio
async def test_video_artifact_committer_commits_repaired_staging_and_gate_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = tmp_path / "staged.mp4"
    current = tmp_path / "reference_videos" / "E1U1.mp4"
    staged.write_bytes(b"provider-result")

    async def gate(path: Path, duration: int, _metadata):
        assert duration == 8
        assert path.read_bytes() == b"provider-result"
        path.write_bytes(b"deterministically-repaired")
        return {
            "status": "PASS",
            "provider_recalled": False,
            "repair_passes": 1,
        }

    captured = {}

    def commit(**kwargs):
        captured["staged_bytes"] = kwargs["staged_file"].read_bytes()
        captured["metadata"] = dict(kwargs["version_metadata"])
        return PaidVersionCommit(version=2, selected=True)

    monkeypatch.setattr(video_artifact_currency, "commit_paid_video_artifact", commit)
    committer = VideoArtifactCommitter(
        project_manager=MagicMock(),
        project_name="demo",
        project_path=tmp_path,
        versions=MagicMock(),
        resource_type="reference_videos",
        resource_id="E1U1",
        prompt="p",
        preselection_media_gate=gate,
    )
    metadata = {"execution_narration": {"delivery": "post_production"}}

    await committer.prepare_selection(staged, 8, metadata)
    assert committer.selection_error is None

    outcome = committer(staged, current, 8, metadata)

    assert outcome.selected is True
    assert captured["staged_bytes"] == b"deterministically-repaired"
    assert captured["metadata"]["h3_auto_repair"] == {
        "status": "PASS",
        "provider_recalled": False,
        "repair_passes": 1,
    }


@pytest.mark.asyncio
async def test_video_artifact_committer_archives_gate_failure_as_history_only_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = tmp_path / "staged.mp4"
    current = tmp_path / "reference_videos" / "E1U1.mp4"
    staged.write_bytes(b"paid-provider-result")
    failure_report = {
        "status": "PROVIDER_REPAIR_REQUIRED",
        "provider_recalled": False,
        "source_media_sha256": "a" * 64,
        "final_media_sha256": "a" * 64,
        "passes": [],
    }

    async def gate(_path: Path, _duration: int, _metadata):
        raise H3RuntimeSelectionError(
            "h3_provider_repair_required",
            "provider repair required",
            report=failure_report,
        )

    captured = {}

    def commit(**kwargs):
        captured["metadata"] = dict(kwargs["version_metadata"])
        # Real commit_paid_video_artifact sees selection_error through resolve_current_basis
        # and leaves the paid bytes history-only. The existing currency integration suite
        # already locks that selection behavior; this test locks the new H3 metadata seam.
        return PaidVersionCommit(version=2, selected=False)

    monkeypatch.setattr(video_artifact_currency, "commit_paid_video_artifact", commit)
    committer = VideoArtifactCommitter(
        project_manager=MagicMock(),
        project_name="demo",
        project_path=tmp_path,
        versions=MagicMock(),
        resource_type="reference_videos",
        resource_id="E1U1",
        prompt="p",
        preselection_media_gate=gate,
    )
    metadata = {"execution_narration": {"delivery": "post_production"}}

    await committer.prepare_selection(staged, 8, metadata)

    assert isinstance(committer.selection_error, H3RuntimeSelectionError)
    outcome = committer(staged, current, 8, metadata)

    assert outcome.selected is False
    assert captured["metadata"]["h3_auto_repair"] == failure_report
    assert (
        captured["metadata"][VIDEO_ARTIFACT_RESTORE_BLOCKER_FIELD]
        == "h3_provider_repair_required"
    )


def _canonical_timeline() -> dict:
    return {
        "unit": {
            "unit_id": "E15U03",
            "duration_sec": 15,
            "shots": [
                {"shot_id": "S1", "start_sec": 0, "end_sec": 5},
                {"shot_id": "S2", "start_sec": 5, "end_sec": 10},
                {"shot_id": "S3", "start_sec": 10, "end_sec": 15},
            ],
        }
    }


def test_reference_video_auto_wires_timeline_only_after_verified_prompt_lock() -> None:
    evaluator, handlers = reference_video_tasks._resolve_trusted_h3_runtime_bundle(
        canonical_director=_canonical_timeline(),
        unit_id="E15U03",
        prompt_lock_verified=True,
        h3_compiler_applied=True,
        evaluator=None,
        repair_handlers=None,
    )

    assert evaluator is not None
    assert handlers is not None
    assert set(handlers) == {reference_video_tasks.H3RepairAction.DETERMINISTIC_AV_RETIME}


@pytest.mark.parametrize(
    ("prompt_lock_verified", "h3_compiler_applied"),
    [
        (False, True),
        (True, False),
        (False, False),
    ],
)
def test_reference_video_never_auto_wires_unlocked_or_uncompiled_canonical(
    prompt_lock_verified: bool,
    h3_compiler_applied: bool,
) -> None:
    evaluator, handlers = reference_video_tasks._resolve_trusted_h3_runtime_bundle(
        canonical_director=_canonical_timeline(),
        unit_id="E15U03",
        prompt_lock_verified=prompt_lock_verified,
        h3_compiler_applied=h3_compiler_applied,
        evaluator=None,
        repair_handlers=None,
    )

    assert evaluator is None
    assert handlers is None


def test_reference_video_injected_trusted_runtime_bundle_takes_precedence() -> None:
    async def injected(_path: Path) -> tuple[MediaQAFinding, ...]:
        return ()

    handlers = {}
    evaluator, resolved_handlers = reference_video_tasks._resolve_trusted_h3_runtime_bundle(
        canonical_director=_canonical_timeline(),
        unit_id="E15U03",
        prompt_lock_verified=True,
        h3_compiler_applied=True,
        evaluator=injected,
        repair_handlers=handlers,
    )

    assert evaluator is injected
    assert resolved_handlers is handlers
