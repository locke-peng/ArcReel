from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import event

from lib.artifact_manifest import ArtifactBasis, compose_video_artifact_basis
from lib.db.models.h3_repair_ticket import H3RepairTicketRecord
from lib.db.models.task import Task
from lib.db.repositories.task_repo import TaskRepository
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_repair_approval_service import H3RepairApprovalFacts, H3RepairApprovalService
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_queue import H3RepairQueueService
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState, H3RepairTicketStore
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)
from lib.resource_paths import resource_relative_path
from lib.speech_artifact_provenance import build_video_duration_basis
from lib.version_manager import VersionManager
from lib.video_artifact_facts import VideoArtifactCurrencyFacts
from server.services import h3_repair_reqa, h3_repair_tasks


_PROJECT = "ai-boss"
_UNIT = "E12U06"
_SHOT = "E12U06-S02"


class _SimulatedProcessDeath(BaseException):
    """Test-only hard process death after durable provider submission state exists."""


def _accepted_prompt() -> str:
    return """subject_definitions:
Character A is stable.

summary:
[REF2VA] Create one 15-second 16:9 video.

retention_analysis:
Keep Character A identity stable.

detailed_description:
Continuity level locked.
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


def _provider_finding() -> MediaQAFinding:
    return MediaQAFinding(
        unit_id=_UNIT,
        shot_id=_SHOT,
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


def _currency(*, parent_version: int) -> VideoArtifactCurrencyFacts:
    visual = ArtifactBasis.build(
        "artifact-visual/video-reference",
        kind_version=1,
        inputs={
            "unit_id": _UNIT,
            "visual_lines": ["repair source"],
            "style": "",
            "canvas": {"aspect_ratio": "16:9"},
            "request_references": [],
        },
    )
    speech = ArtifactBasis.build("artifact-speech/video", kind_version=1, inputs={"mode": "silent"})
    duration = build_video_duration_basis(15)
    return VideoArtifactCurrencyFacts(
        episode=12,
        request_duration_seconds=15,
        visual_basis=visual,
        speech_basis=speech,
        duration_basis=duration,
        video_basis=compose_video_artifact_basis(visual=visual, speech=speech, duration=duration),
        voice_style_speakers=(),
        duration_tiers=(15,),
        reference_image_limit=None,
        parent_version=parent_version,
    )


class _ProjectManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path

    def load_project(self, _project_name: str) -> dict[str, object]:
        return {"generation_mode": "reference_video"}

    def get_project_path(self, _project_name: str) -> Path:
        return self.project_path


class _InterruptingResumeGenerator:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.generate_calls = 0
        self.resume_calls = 0
        self.provider_job_id: str | None = None

    def _write(self, resource_type: str, resource_id: str, payload: bytes) -> Path:
        output = self.project_path / resource_relative_path(resource_type, resource_id)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        return output

    async def generate_video_async(self, **kwargs):
        self.generate_calls += 1
        if self.generate_calls != 1:
            raise AssertionError("E2E-02 recovery must not submit provider generation twice")
        before_submit = kwargs["before_submit"]
        on_provider_job_id = kwargs["on_provider_job_id"]
        assert before_submit is not None
        assert on_provider_job_id is not None

        await before_submit()
        self.provider_job_id = "provider-job-e2e02"
        await on_provider_job_id(
            self.provider_job_id,
            "minimax-h3",
            "https://api.minimax.test",
        )
        raise _SimulatedProcessDeath("simulated hard worker death after provider job persistence")

    async def resume_video_async(self, **kwargs):
        self.resume_calls += 1
        assert self.resume_calls == 1
        assert self.provider_job_id is not None
        assert kwargs["job_id"] == self.provider_job_id
        output = self._write(
            kwargs["resource_type"],
            kwargs["resource_id"],
            b"provider-shot-resumed",
        )
        return output, 1, None, None


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

    async def prepare_selection(self, _staged: Path, _duration: int, _metadata: Any) -> None:
        return None

    def __call__(self, staged: Path, current: Path, duration: int, metadata: Any):
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


@dataclass
class _Evidence:
    lifecycle: list[str]
    payload: dict[str, Any]

    def state(self, value: H3RepairTicketLifecycleState) -> None:
        if not self.lifecycle or self.lifecycle[-1] != value.value:
            self.lifecycle.append(value.value)


async def _persisted(session_factory, ticket_id: str):
    async with session_factory() as session:
        result = await H3RepairTicketStore(session).load(project_name=_PROJECT, ticket_id=ticket_id)
    assert result is not None
    return result


async def _task_snapshot(session_factory, task_id: str) -> dict[str, object]:
    async with session_factory() as session:
        task = await TaskRepository(session).get(task_id)
    assert task is not None
    return task


def _write_evidence(evidence: dict[str, Any]) -> None:
    raw_dir = os.environ.get("H3_PHASE5_EVIDENCE_DIR")
    if not raw_dir:
        return
    directory = Path(raw_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "e2e02-interruption-resume.json").write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


async def test_phase5_interruption_resume_e2e(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = tmp_path / _PROJECT
    current = project_path / resource_relative_path("reference_videos", _UNIT)
    current.parent.mkdir(parents=True)
    current.write_bytes(b"accepted-source-unit")
    prompt = _accepted_prompt()

    versions = VersionManager(project_path)
    source_version = versions.add_version(
        "reference_videos",
        _UNIT,
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
        artifact_video_currency=_currency(parent_version=0).to_dict(),
    )

    ticket = build_h3_repair_ticket(
        plan_h3_auto_repair(_provider_finding()),
        source_media_sha256=sha256_file(current),
        context=H3RepairTicketContext(
            provider_prompt_sha256=provider_prompt_sha256(prompt),
            reference_sha256=(),
        ),
    )
    evidence = _Evidence(lifecycle=[], payload={})

    async with session_factory() as session:
        persisted = await H3RepairTicketStore(session).persist(project_name=_PROJECT, ticket=ticket)
        await session.commit()
        evidence.state(persisted.lifecycle_state)

        facts = H3RepairApprovalFacts(
            source_media_sha256=ticket.source_media_sha256,
            shot_id=_SHOT,
            repair_action=ticket.repair_action,
            provider_prompt_sha256=ticket.provider_prompt_sha256,
            reference_sha256=ticket.reference_sha256,
        )
        approved = await H3RepairApprovalService(session).approve(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
            approved_by="e2e",
            current_facts=facts,
        )
        evidence.state(approved.ticket.lifecycle_state)

        queued = await H3RepairQueueService(session).enqueue_approved_ticket(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
            user_id="e2e",
        )
        queued_ticket = await H3RepairTicketStore(session).load(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
        )
        assert queued_ticket is not None
        evidence.state(queued_ticket.lifecycle_state)

        claim = await H3RepairQueueService(session).claim_next()
        assert claim is not None
        assert claim.task_id == queued.task_id
        running_ticket = await H3RepairTicketStore(session).load(
            project_name=_PROJECT,
            ticket_id=ticket.ticket_id,
        )
        assert running_ticket is not None
        evidence.state(running_ticket.lifecycle_state)

    generator = _InterruptingResumeGenerator(project_path)
    manager = _ProjectManager(project_path)
    monkeypatch.setattr(h3_repair_tasks, "safe_session_factory", session_factory)
    monkeypatch.setattr(h3_repair_tasks, "get_project_manager", lambda: manager)

    async def resolve_context(*_args, **_kwargs):
        return SimpleNamespace(
            generator=generator,
            video=SimpleNamespace(
                provider_model=SimpleNamespace(provider_id="minimax", model_id="MiniMax-H3"),
                backend_model="MiniMax-H3",
                endpoint="minimax-h3",
                max_prompt_chars=7000,
            ),
        )

    monkeypatch.setattr(h3_repair_tasks, "resolve_generation_context", resolve_context)

    def deterministic_assemble(_source: Path, provider: Path, output: Path, _request) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"assembled:" + provider.read_bytes())

    monkeypatch.setattr(h3_repair_tasks, "assemble_h3_shot_window", deterministic_assemble)
    monkeypatch.setattr(h3_repair_reqa, "safe_session_factory", session_factory)
    monkeypatch.setattr(h3_repair_reqa, "get_project_manager", lambda: manager)
    monkeypatch.setattr(h3_repair_reqa, "VideoArtifactCommitter", _SelectingCommitter)

    async def pass_evaluator(_path: Path):
        return ()

    async def run_reqa(**kwargs):
        return await h3_repair_reqa.execute_h3_repair_reqa(
            **kwargs,
            evaluator=pass_evaluator,
            repair_handlers={},
        )

    monkeypatch.setattr(h3_repair_tasks, "execute_h3_repair_reqa", run_reqa)

    first_task = await _task_snapshot(session_factory, queued.task_id)
    with pytest.raises(_SimulatedProcessDeath):
        await h3_repair_tasks.execute_h3_repair_task(first_task)

    interrupted_ticket = await _persisted(session_factory, ticket.ticket_id)
    async with session_factory() as session:
        interrupted_task = await session.get(Task, queued.task_id)
        assert interrupted_task is not None
        checkpoint_before = interrupted_task.execution_checkpoint_json
        provider_job_id_before = interrupted_task.provider_job_id

    assert interrupted_ticket.lifecycle_state is H3RepairTicketLifecycleState.RUNNING
    assert interrupted_ticket.provider_call_count == 1
    assert interrupted_ticket.execution_identity == queued.execution_identity == claim.execution_identity
    assert checkpoint_before is not None
    assert provider_job_id_before == "provider-job-e2e02"
    assert generator.generate_calls == 1
    assert generator.resume_calls == 0

    execution_identity_before = interrupted_ticket.execution_identity
    ticket_id_before = interrupted_ticket.ticket.ticket_id
    task_id_before = queued.task_id

    def record_lifecycle_state(_target, value, _oldvalue, _initiator) -> None:
        if isinstance(value, str):
            evidence.state(H3RepairTicketLifecycleState(value))

    event.listen(H3RepairTicketRecord.lifecycle_state, "set", record_lifecycle_state)
    try:
        result = await h3_repair_tasks.execute_h3_repair_task(
            await _task_snapshot(session_factory, queued.task_id)
        )
    finally:
        event.remove(H3RepairTicketRecord.lifecycle_state, "set", record_lifecycle_state)

    final_ticket = await _persisted(session_factory, ticket.ticket_id)
    async with session_factory() as session:
        final_task = await session.get(Task, queued.task_id)
        assert final_task is not None
        checkpoint_after = final_task.execution_checkpoint_json
        provider_job_id_after = final_task.provider_job_id
        task_count = await session.scalar(
            __import__("sqlalchemy").select(__import__("sqlalchemy").func.count())
            .select_from(Task)
            .where(Task.task_type == "h3_provider_repair")
        )
        ticket_count = await session.scalar(
            __import__("sqlalchemy").select(__import__("sqlalchemy").func.count())
            .select_from(H3RepairTicketRecord)
            .where(H3RepairTicketRecord.project_name == _PROJECT)
        )

    final_version = versions.get_current_version("reference_videos", _UNIT)
    reqa = result["reqa"]

    assert generator.generate_calls == 1
    assert generator.resume_calls == 1
    assert final_ticket.provider_call_count == 1
    assert final_ticket.execution_identity == execution_identity_before
    assert final_ticket.ticket.ticket_id == ticket_id_before
    assert final_task.task_id == task_id_before
    assert provider_job_id_after == provider_job_id_before == generator.provider_job_id
    assert checkpoint_after == checkpoint_before
    assert task_count == 1
    assert ticket_count == 1
    assert final_ticket.lifecycle_state is H3RepairTicketLifecycleState.ACCEPTED
    assert final_ticket.reqa_outcome == "PASS"
    assert reqa["selected_current"] is True
    assert final_version == source_version + 1
    assert current.read_bytes() == b"assembled:provider-shot-resumed"
    assert evidence.lifecycle == [
        "awaiting_approval",
        "approved",
        "queued",
        "running",
        "provider_completed",
        "reassembling",
        "reqa_running",
        "accepted",
    ]

    evidence.payload = {
        "schema_version": 1,
        "scenario": "E2E-02 Interruption Resume",
        "tested_sha": os.environ.get("H3_PHASE5_TESTED_SHA"),
        "project_name": _PROJECT,
        "unit_id": _UNIT,
        "shot_id": _SHOT,
        "ticket": {
            "ticket_id_before": ticket_id_before,
            "ticket_id_after": final_ticket.ticket.ticket_id,
            "new_ticket_created": ticket_count != 1,
        },
        "execution": {
            "task_id_before": task_id_before,
            "task_id_after": final_task.task_id,
            "new_task_created": task_count != 1,
            "execution_identity_before": execution_identity_before,
            "execution_identity_after": final_ticket.execution_identity,
            "new_execution_identity": final_ticket.execution_identity != execution_identity_before,
            "provider_job_id_before": provider_job_id_before,
            "provider_job_id_after": provider_job_id_after,
            "checkpoint_stable": checkpoint_after == checkpoint_before,
            "provider_call_count": final_ticket.provider_call_count,
        },
        "provider": {
            "generate_calls": generator.generate_calls,
            "resume_calls": generator.resume_calls,
            "paid_minimax_calls": 0,
        },
        "recovery": {
            "interrupted_lifecycle_state": interrupted_ticket.lifecycle_state.value,
            "resumed_existing_job": provider_job_id_after == provider_job_id_before,
        },
        "reqa": {
            "outcome": final_ticket.reqa_outcome,
            "selected_current": reqa["selected_current"],
            "selected_artifact_id": final_ticket.selected_artifact_id,
            "selected_version_id": final_ticket.selected_version_id,
        },
        "versions": {
            "source_version": source_version,
            "selected_version": final_version,
        },
        "lifecycle": evidence.lifecycle,
    }
    _write_evidence(evidence.payload)
