from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.db.models.task import Task
from lib.db.repositories.task_repo import TaskRepository
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_provider_repair_runtime import (
    H3RepairSourceVersion,
    build_h3_shot_repair_prompt,
)
from lib.reference_video.h3_repair_approval_service import (
    H3ProviderRepairApprovalBinding,
    H3RepairApprovalFacts,
    H3RepairApprovalService,
)
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_queue import (
    H3RepairProviderRequestFacts,
    H3RepairQueueService,
)
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState, H3RepairTicketStore
from lib.reference_video.h3_shot_repair_executor import build_h3_shot_repair_request
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)
from lib.resource_paths import resource_relative_path
from server.services import h3_repair_tasks


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


def _ticket(*, source_sha: str, prompt_sha: str):
    finding = MediaQAFinding(
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
    return build_h3_repair_ticket(
        plan_h3_auto_repair(finding),
        source_media_sha256=source_sha,
        context=H3RepairTicketContext(
            provider_prompt_sha256=prompt_sha,
            reference_sha256=(),
        ),
    )


def _facts(ticket) -> H3RepairApprovalFacts:
    assert ticket.shot_id is not None
    return H3RepairApprovalFacts(
        source_media_sha256=ticket.source_media_sha256,
        shot_id=ticket.shot_id,
        repair_action=ticket.repair_action,
        provider_prompt_sha256=ticket.provider_prompt_sha256,
        reference_sha256=ticket.reference_sha256,
    )


async def _persist_approve_claim(db_factory, ticket) -> tuple[str, str]:
    async with db_factory() as session:
        await H3RepairTicketStore(session).persist(project_name="ai-boss", ticket=ticket)
        await session.commit()
        approval = await H3RepairApprovalService(session).approve(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            approved_by="operator:test",
            current_facts=_facts(ticket),
        )
        assert isinstance(approval.approval, H3ProviderRepairApprovalBinding)
        queued = await H3RepairQueueService(session).enqueue_approved_ticket(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
        )
        claim = await H3RepairQueueService(session).claim_next()
        assert claim is not None
        assert claim.task_id == queued.task_id
        return queued.task_id, queued.execution_identity


class _FakeProjectManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path

    def load_project(self, _project_name: str) -> dict[str, object]:
        return {"generation_mode": "reference_video"}

    def get_project_path(self, _project_name: str) -> Path:
        return self.project_path


class _FakeGenerator:
    def __init__(self, project_path: Path, *, allow_generate: bool, cancel_generate: bool = False):
        self.project_path = project_path
        self.allow_generate = allow_generate
        self.cancel_generate = cancel_generate
        self.generate_calls = 0
        self.resume_calls = 0

    def _write(self, resource_type: str, resource_id: str, payload: bytes) -> Path:
        output = self.project_path / resource_relative_path(resource_type, resource_id)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        return output

    async def generate_video_async(self, **kwargs):
        if not self.allow_generate:
            raise AssertionError("resume path must not submit a new provider generation")
        self.generate_calls += 1
        if self.cancel_generate:
            raise asyncio.CancelledError
        before_submit = kwargs["before_submit"]
        on_provider_job_id = kwargs["on_provider_job_id"]
        assert before_submit is not None
        assert on_provider_job_id is not None
        await before_submit()
        await on_provider_job_id(
            "provider-job-001",
            "minimax-h3",
            "https://api.minimax.test",
        )
        output = self._write(
            kwargs["resource_type"],
            kwargs["resource_id"],
            b"provider-shot-fresh",
        )
        return output, 1, None, None

    async def resume_video_async(self, **kwargs):
        self.resume_calls += 1
        output = self._write(
            kwargs["resource_type"],
            kwargs["resource_id"],
            b"provider-shot-resumed",
        )
        return output, 1, None, None


def _source(project_path: Path, ticket, source_path: Path) -> H3RepairSourceVersion:
    prompt = _accepted_prompt()
    return H3RepairSourceVersion(
        media_path=source_path,
        media_sha256=ticket.source_media_sha256,
        version=1,
        provider_prompt=prompt,
        provider_prompt_sha256=provider_prompt_sha256(prompt),
        provider_id="minimax",
        provider_model="MiniMax-H3",
        backend_model="MiniMax-H3",
        endpoint_guard="minimax-h3",
        generation_type="r2v",
        aspect_ratio="16:9",
        resolution="768p",
        generate_audio=True,
        service_tier="default",
        seed=None,
        reference_images=(),
        reference_audio_files=(),
        reference_audio_targets=None,
    )


def _patch_runtime(monkeypatch, db_factory, project_path: Path, source, generator: _FakeGenerator) -> None:
    monkeypatch.setattr(h3_repair_tasks, "safe_session_factory", db_factory)
    monkeypatch.setattr(
        h3_repair_tasks,
        "get_project_manager",
        lambda: _FakeProjectManager(project_path),
    )
    monkeypatch.setattr(
        h3_repair_tasks,
        "resolve_h3_repair_source_version",
        lambda **_kwargs: source,
    )

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

    async def _defer_reqa(**_kwargs):
        return {
            "reqa_outcome": "DEFERRED_SLICE4_TEST",
            "lifecycle_state": H3RepairTicketLifecycleState.REQA_RUNNING.value,
            "selected_current": False,
            "followup_ticket_ids": [],
        }

    monkeypatch.setattr(h3_repair_tasks, "execute_h3_repair_reqa", _defer_reqa)

    def assemble(_source: Path, provider: Path, output: Path, _request) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"assembled:" + provider.read_bytes())

    monkeypatch.setattr(h3_repair_tasks, "assemble_h3_shot_window", assemble)


async def _task_snapshot(db_factory, task_id: str) -> dict[str, object]:
    async with db_factory() as session:
        task = await TaskRepository(session).get(task_id)
    assert task is not None
    return task


@pytest.mark.usefixtures("db_factory")
async def test_fresh_repair_executes_one_submit_and_advances_to_reqa(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    source_path = project_path / resource_relative_path("reference_videos", "E12U06")
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"accepted-source-unit")
    ticket = _ticket(
        source_sha=sha256_file(source_path),
        prompt_sha=provider_prompt_sha256(_accepted_prompt()),
    )
    task_id, execution_identity = await _persist_approve_claim(db_factory, ticket)
    source = _source(project_path, ticket, source_path)
    generator = _FakeGenerator(project_path, allow_generate=True)
    _patch_runtime(monkeypatch, db_factory, project_path, source, generator)

    result = await h3_repair_tasks.execute_h3_repair_task(await _task_snapshot(db_factory, task_id))

    assert generator.generate_calls == 1
    assert generator.resume_calls == 0
    assert result["execution_identity"] == execution_identity
    assert result["lifecycle_state"] == H3RepairTicketLifecycleState.REQA_RUNNING.value

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.REQA_RUNNING
        assert persisted.provider_call_count == 1
        assert persisted.repair_output_sha256 is not None
        task = await session.get(Task, task_id)
        assert task is not None
        assert task.provider_job_id == "provider-job-001"
        assert task.execution_checkpoint_json is not None


@pytest.mark.usefixtures("db_factory")
async def test_restart_with_persisted_job_resumes_without_new_submit(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    source_path = project_path / resource_relative_path("reference_videos", "E12U06")
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"accepted-source-unit")
    ticket = _ticket(
        source_sha=sha256_file(source_path),
        prompt_sha=provider_prompt_sha256(_accepted_prompt()),
    )
    task_id, _execution_identity = await _persist_approve_claim(db_factory, ticket)
    source = _source(project_path, ticket, source_path)

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.approval_json is not None
        binding = H3ProviderRepairApprovalBinding.from_json(persisted.approval_json)
        request = build_h3_shot_repair_request(ticket, binding.to_phase4_approval())
        repair_prompt = build_h3_shot_repair_prompt(
            source_provider_prompt=source.provider_prompt,
            request=request,
        )
        provider_request = H3RepairProviderRequestFacts(
            generation_type=source.generation_type,
            backend_model=source.backend_model,
            endpoint_guard=source.endpoint_guard,
            prompt=repair_prompt,
            prompt_sha256=provider_prompt_sha256(repair_prompt),
            duration_seconds=5,
            aspect_ratio=source.aspect_ratio,
            resolution=source.resolution,
            generate_audio=source.generate_audio,
            service_tier=source.service_tier,
            seed=source.seed,
        )
        queue = H3RepairQueueService(session)
        reservation = await queue.reserve_provider_submission(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            current_facts=_facts(ticket),
            provider_id=source.provider_id,
            provider_model=source.provider_model,
            provider_request=provider_request,
        )
        assert reservation.provider_call_count == 1
        await queue.persist_provider_job_identity(
            project_name="ai-boss",
            ticket_id=ticket.ticket_id,
            provider_job_id="provider-job-resume",
            endpoint="minimax-h3",
            base_url="https://api.minimax.test",
        )

    generator = _FakeGenerator(project_path, allow_generate=False)
    _patch_runtime(monkeypatch, db_factory, project_path, source, generator)

    result = await h3_repair_tasks.execute_h3_repair_task(await _task_snapshot(db_factory, task_id))

    assert generator.generate_calls == 0
    assert generator.resume_calls == 1
    assert result["lifecycle_state"] == H3RepairTicketLifecycleState.REQA_RUNNING.value

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.REQA_RUNNING
        assert persisted.provider_call_count == 1
        task = await session.get(Task, task_id)
        assert task is not None
        assert task.provider_job_id == "provider-job-resume"



async def test_cancelled_fresh_repair_cancels_ticket_without_spending_allowance(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    source_path = project_path / resource_relative_path("reference_videos", "E12U06")
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"accepted-source-unit")
    ticket = _ticket(
        source_sha=sha256_file(source_path),
        prompt_sha=provider_prompt_sha256(_accepted_prompt()),
    )
    task_id, _execution_identity = await _persist_approve_claim(db_factory, ticket)
    source = _source(project_path, ticket, source_path)
    generator = _FakeGenerator(project_path, allow_generate=True, cancel_generate=True)
    _patch_runtime(monkeypatch, db_factory, project_path, source, generator)

    with pytest.raises(asyncio.CancelledError):
        await h3_repair_tasks.execute_h3_repair_task(await _task_snapshot(db_factory, task_id))

    async with db_factory() as session:
        persisted = await H3RepairTicketStore(session).load(project_name="ai-boss", ticket_id=ticket.ticket_id)
        assert persisted is not None
        assert persisted.lifecycle_state is H3RepairTicketLifecycleState.CANCELLED
        assert persisted.provider_call_count == 0
        task = await session.get(Task, task_id)
        assert task is not None
        assert task.provider_job_id is None
        assert task.execution_checkpoint_json is None


async def test_restart_from_reqa_running_does_not_replay_provider_repair(
    db_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "ai-boss"
    source_path = project_path / resource_relative_path("reference_videos", "E12U06")
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"accepted-source-unit")
    ticket = _ticket(
        source_sha=sha256_file(source_path),
        prompt_sha=provider_prompt_sha256(_accepted_prompt()),
    )
    task_id, _execution_identity = await _persist_approve_claim(db_factory, ticket)
    source = _source(project_path, ticket, source_path)
    generator = _FakeGenerator(project_path, allow_generate=True)
    _patch_runtime(monkeypatch, db_factory, project_path, source, generator)

    first = await h3_repair_tasks.execute_h3_repair_task(await _task_snapshot(db_factory, task_id))
    assert first["lifecycle_state"] == H3RepairTicketLifecycleState.REQA_RUNNING.value
    assert generator.generate_calls == 1
    assert generator.resume_calls == 0

    second = await h3_repair_tasks.execute_h3_repair_task(await _task_snapshot(db_factory, task_id))

    assert second["lifecycle_state"] == H3RepairTicketLifecycleState.REQA_RUNNING.value
    assert second["recovered_reqa"] is True
    assert generator.generate_calls == 1
    assert generator.resume_calls == 0
