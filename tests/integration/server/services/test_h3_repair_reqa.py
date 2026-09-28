from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from lib.db.models.h3_repair_ticket import H3RepairTicketRecord
from lib.db.models.task import Task
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import (
    H3RepairTicketLifecycleState,
    H3RepairTicketStore,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)
from lib.resource_paths import resource_relative_path
from lib.version_manager import VersionManager
from server.services import h3_repair_reqa


class _ProjectManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path

    def get_project_path(self, _project_name: str) -> Path:
        return self.project_path


class _SelectingCommitter:
    def __init__(
        self,
        *,
        versions: VersionManager,
        resource_type: str,
        resource_id: str,
        prompt: str,
        **_kwargs,
    ):
        self.versions = versions
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.prompt = prompt

    async def prepare_selection(self, _staged: Path, _duration: int, _metadata) -> None:
        return None

    def __call__(self, staged: Path, current: Path, duration: int, metadata):
        return self.versions.commit_staged_paid_version(
            self.resource_type,
            self.resource_id,
            self.prompt,
            staged_file=staged,
            current_file=current,
            select_current=True,
            duration_seconds=duration,
            **dict(metadata),
        )

    async def release_admission_guard(self) -> None:
        return None


def _provider_finding() -> MediaQAFinding:
    return MediaQAFinding(
        unit_id="E12U06",
        shot_id="E12U06-S02",
        time_range=MediaQATimeRange(start_seconds=5.0, end_seconds=10.0),
        canonical_violation="provider invented non-canonical semantic content",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=0.5,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        evidence_frames=(180,),
        tags=("semantic_failure",),
    )


def _source_setup(project_path: Path):
    current = project_path / resource_relative_path("reference_videos", "E12U06")
    current.parent.mkdir(parents=True)
    current.write_bytes(b"accepted-source-unit")
    prompt = """subject_definitions:
Character A is stable.

summary:
[REF2VA] Create one 15-second 16:9 video.

retention_analysis:
Keep Character A identity stable.

detailed_description:
[Shot 1]
first beat
[Shot 2] At 00:05.000
repair this beat
[Shot 3] At 00:10.000
third beat

overall_soundscape:
Room tone.

non_diegetic_music:
N/A"""
    versions = VersionManager(project_path)
    source_version = versions.add_version(
        "reference_videos",
        "E12U06",
        prompt,
        source_file=current,
        execution_provider_media=[],
        execution_generate_audio=True,
        execution_seed=None,
        execution_provider_id="minimax",
        execution_provider_model_id="MiniMax-H3",
        execution_backend_model_id="MiniMax-H3",
        execution_endpoint_guard="minimax-h3",
        execution_capability="r2v",
        execution_aspect_ratio="16:9",
        execution_resolution="768p",
        execution_service_tier="default",
        execution_duration_seconds=15,
        execution_task_id="origin-task",
    )
    return current, prompt, versions, source_version


async def _persist_reqa_ticket(
    db_factory,
    *,
    source_sha: str,
    prompt_sha: str,
    candidate_sha: str,
):
    ticket = build_h3_repair_ticket(
        plan_h3_auto_repair(_provider_finding()),
        source_media_sha256=source_sha,
        context=H3RepairTicketContext(
            provider_prompt_sha256=prompt_sha,
            reference_sha256=(),
        ),
    )
    async with db_factory() as session:
        store = H3RepairTicketStore(session)
        await store.persist(project_name="ai-boss", ticket=ticket)
        for state in (
            H3RepairTicketLifecycleState.APPROVED,
            H3RepairTicketLifecycleState.QUEUED,
            H3RepairTicketLifecycleState.RUNNING,
            H3RepairTicketLifecycleState.PROVIDER_COMPLETED,
            H3RepairTicketLifecycleState.REASSEMBLING,
            H3RepairTicketLifecycleState.REQA_RUNNING,
        ):
            await store.transition(
                project_name="ai-boss",
                ticket_id=ticket.ticket_id,
                target=state,
                reason="test setup",
            )
        record = await session.get(H3RepairTicketRecord, ("ai-boss", ticket.ticket_id))
        assert record is not None
        record.execution_identity = "h3exec_slice5_test"
        record.repair_output_sha256 = candidate_sha
        await session.commit()
    return ticket


async def test_reqa_pass_selects_repaired_unit_and_accepts_ticket(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    current, prompt, versions, source_version = _source_setup(project_path)
    candidate = project_path / "repairs" / "reassembled_units" / "h3exec_slice5_test.mp4"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"reassembled-repair-pass")
    ticket = await _persist_reqa_ticket(
        db_factory,
        source_sha=sha256_file(current),
        prompt_sha=provider_prompt_sha256(prompt),
        candidate_sha=sha256_file(candidate),
    )

    async def evaluator(_path: Path):
        return ()

    monkeypatch.setattr(h3_repair_reqa, "safe_session_factory", db_factory)
    monkeypatch.setattr(h3_repair_reqa, "get_project_manager", lambda: _ProjectManager(project_path))
    monkeypatch.setattr(h3_repair_reqa, "VideoArtifactCommitter", _SelectingCommitter)

    result = await h3_repair_reqa.execute_h3_repair_reqa(
        project_name="ai-boss",
        ticket_id=ticket.ticket_id,
        candidate_media=candidate,
        evaluator=evaluator,
        repair_handlers={},
    )

    assert result["reqa_outcome"] == "PASS"
    assert result["lifecycle_state"] == H3RepairTicketLifecycleState.ACCEPTED.value
    assert result["selected_current"] is True
    assert current.read_bytes() == b"reassembled-repair-pass"
    assert versions.get_current_version("reference_videos", "E12U06") == source_version + 1

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
        )
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.ACCEPTED
        assert persisted.reqa_outcome == "PASS"
        assert persisted.selected_artifact_id == "reference_videos/E12U06.mp4"
        assert persisted.selected_version_id == f"reference_videos:E12U06:v{source_version + 1}"


async def test_reqa_provider_failure_archives_history_and_creates_fresh_unapproved_ticket(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    current, prompt, versions, source_version = _source_setup(project_path)
    original_bytes = current.read_bytes()
    candidate = project_path / "repairs" / "reassembled_units" / "h3exec_slice5_test.mp4"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"reassembled-still-bad")
    ticket = await _persist_reqa_ticket(
        db_factory,
        source_sha=sha256_file(current),
        prompt_sha=provider_prompt_sha256(prompt),
        candidate_sha=sha256_file(candidate),
    )

    async def evaluator(_path: Path):
        return (_provider_finding(),)

    monkeypatch.setattr(h3_repair_reqa, "safe_session_factory", db_factory)
    monkeypatch.setattr(h3_repair_reqa, "get_project_manager", lambda: _ProjectManager(project_path))

    result = await h3_repair_reqa.execute_h3_repair_reqa(
        project_name="ai-boss",
        ticket_id=ticket.ticket_id,
        candidate_media=candidate,
        evaluator=evaluator,
        repair_handlers={},
    )

    assert result["reqa_outcome"] == "PROVIDER_REPAIR_REQUIRED"
    assert result["lifecycle_state"] == H3RepairTicketLifecycleState.REJECTED.value
    assert result["selected_current"] is False
    assert len(result["followup_ticket_ids"]) == 1
    assert current.read_bytes() == original_bytes
    assert versions.get_current_version("reference_videos", "E12U06") == source_version

    info = versions.get_versions("reference_videos", "E12U06")
    repair_history = [
        item
        for item in info["versions"]
        if item.get("h3_repair_ticket_id") == ticket.ticket_id
    ]
    assert len(repair_history) == 1
    assert repair_history[0]["is_current"] is False
    assert repair_history[0]["h3_reqa"]["status"] == "PROVIDER_REPAIR_REQUIRED"

    followup_id = result["followup_ticket_ids"][0]
    assert followup_id != ticket.ticket_id
    async with db_factory() as session:
        old = await H3RepairTicketStore(session).load(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
        )
        followup = await H3RepairTicketStore(session).load(
            project_name="ai-boss",
            ticket_id=followup_id,
        )
        assert old is not None
        assert old.lifecycle_state is H3RepairTicketLifecycleState.REJECTED
        assert old.reqa_outcome == "PROVIDER_REPAIR_REQUIRED"
        assert followup is not None
        assert followup.lifecycle_state is H3RepairTicketLifecycleState.AWAITING_APPROVAL
        assert followup.approval_json is None
        assert followup.approval_identity is None
        assert followup.max_provider_calls is None


async def test_reqa_followup_creation_is_bounded_and_fails_closed(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    current, prompt, versions, source_version = _source_setup(project_path)
    candidate = project_path / "repairs" / "reassembled_units" / "h3exec_slice5_test.mp4"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"reassembled-multiple-bad-shots")
    ticket = await _persist_reqa_ticket(
        db_factory,
        source_sha=sha256_file(current),
        prompt_sha=provider_prompt_sha256(prompt),
        candidate_sha=sha256_file(candidate),
    )

    second = MediaQAFinding(
        unit_id="E12U06",
        shot_id="E12U06-S03",
        time_range=MediaQATimeRange(start_seconds=10.0, end_seconds=15.0),
        canonical_violation="second provider-only semantic failure",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=False,
        audio_is_accepted=True,
        repairability=MediaQARepairability.PROVIDER,
        affected_fraction=0.4,
        failure_class=H3FailureClass.LARGE_SEMANTIC_FAILURE,
        evidence_frames=(300,),
        tags=("semantic_failure",),
    )

    async def evaluator(_path: Path):
        return (_provider_finding(), second)

    monkeypatch.setattr(h3_repair_reqa, "safe_session_factory", db_factory)
    monkeypatch.setattr(h3_repair_reqa, "get_project_manager", lambda: _ProjectManager(project_path))

    result = await h3_repair_reqa.execute_h3_repair_reqa(
        project_name="ai-boss",
        ticket_id=ticket.ticket_id,
        candidate_media=candidate,
        evaluator=evaluator,
        repair_handlers={},
        max_followup_tickets=1,
    )

    assert result["reqa_outcome"] == "PROVIDER_REPAIR_FOLLOWUP_BLOCKED"
    assert result["lifecycle_state"] == H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED.value
    assert result["followup_ticket_ids"] == []
    assert versions.get_current_version("reference_videos", "E12U06") == source_version

    async with db_factory() as session:
        rows = await H3RepairTicketStore(session).list_for_project(project_name="ai-boss")
        assert [row.ticket.ticket_id for row in rows] == [ticket.ticket_id]
        assert rows[0].lifecycle_state is H3RepairTicketLifecycleState.HUMAN_REVIEW_REQUIRED


async def test_reqa_recovers_trusted_canonical_from_source_execution_task(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    current, prompt, _versions, _source_version = _source_setup(project_path)
    candidate = project_path / "repairs" / "reassembled_units" / "h3exec_slice5_test.mp4"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"trusted-reqa-candidate")
    ticket = await _persist_reqa_ticket(
        db_factory,
        source_sha=sha256_file(current),
        prompt_sha=provider_prompt_sha256(prompt),
        candidate_sha=sha256_file(candidate),
    )

    now = datetime.now(UTC)
    async with db_factory() as session:
        session.add(
            Task(
                task_id="origin-task",
                project_name="ai-boss",
                task_type="reference_video",
                media_type="video",
                resource_id="E12U06",
                payload_json=json.dumps(
                    {
                        "canonical_director": {"trusted": "canonical"},
                        "expected_provider_prompt_sha256": provider_prompt_sha256(prompt),
                    }
                ),
                status="succeeded",
                source="agent",
                queued_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    captured = {}

    async def evaluator(_path: Path):
        return ()

    def trusted_bundle(**kwargs):
        captured.update(kwargs)
        return evaluator, {}

    monkeypatch.setattr(h3_repair_reqa, "safe_session_factory", db_factory)
    monkeypatch.setattr(h3_repair_reqa, "get_project_manager", lambda: _ProjectManager(project_path))
    monkeypatch.setattr(h3_repair_reqa, "VideoArtifactCommitter", _SelectingCommitter)
    monkeypatch.setattr(h3_repair_reqa, "resolve_trusted_h3_runtime_bundle", trusted_bundle)

    result = await h3_repair_reqa.execute_h3_repair_reqa(
        project_name="ai-boss",
        ticket_id=ticket.ticket_id,
        candidate_media=candidate,
    )

    assert result["reqa_outcome"] == "PASS"
    assert captured["canonical_director"] == {"trusted": "canonical"}
    assert captured["prompt_lock_verified"] is True
    assert captured["h3_compiler_applied"] is True
