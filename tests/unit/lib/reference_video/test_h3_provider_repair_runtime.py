from __future__ import annotations

from pathlib import Path

from lib.reference_video.execution_checkpoint import StagedProviderMedia
from lib.reference_video.h3_auto_repair_loop import plan_h3_auto_repair
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
from lib.reference_video.h3_prompt_execution import provider_prompt_sha256
from lib.reference_video.h3_provider_repair_runtime import (
    H3VideoStreamFacts,
    assemble_h3_shot_window,
    build_h3_shot_repair_prompt,
    resolve_h3_repair_source_version,
)
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_repair_ticket import H3RepairTicketContext, build_h3_repair_ticket
from lib.reference_video.h3_shot_repair_executor import H3ShotRepairRequest
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
    MediaQATimeRange,
)
from lib.resource_paths import resource_relative_path
from lib.version_manager import VersionManager


def _compiled_prompt() -> str:
    return """subject_definitions:
Character A is stable.

summary:
[REF2VA] Create one 15-second 16:9 video.

retention_analysis:
Keep Character A identity stable.

detailed_description:
Continuity level locked.
[Shot 1]
first beat only
[Shot 2] At 00:05.000
second approved beat
Character A says: <d>[Chinese] 保持一致</d>
[Shot 3] At 00:10.000
third beat only

overall_soundscape:
Room tone.

non_diegetic_music:
N/A"""


def _request() -> H3ShotRepairRequest:
    return H3ShotRepairRequest(
        ticket_id="h3rt_1234567890abcdef12345678",
        ticket_sha256="1" * 64,
        unit_id="E12U06",
        shot_id="E12U06-S02",
        start_seconds=5.0,
        end_seconds=10.0,
        repair_action=H3RepairAction.REGENERATE_SHOT,
        source_media_sha256="2" * 64,
        provider_prompt_sha256="3" * 64,
        reference_sha256=("4" * 64,),
    )


def _ticket(*, source_sha: str, prompt_sha: str, reference_sha: tuple[str, ...]):
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
            reference_sha256=reference_sha,
        ),
    )


def test_build_shot_repair_prompt_projects_only_approved_window() -> None:
    prompt = build_h3_shot_repair_prompt(
        source_provider_prompt=_compiled_prompt(),
        request=_request(),
    )

    assert "second approved beat" in prompt
    assert "保持一致" in prompt
    assert "first beat only" not in prompt
    assert "third beat only" not in prompt
    assert "[Shot 2]" not in prompt
    assert prompt.count("[Shot 1]") == 1
    assert "source Unit window 5.000s-10.000s" in prompt
    assert "Do not generate preceding or following shots" in prompt


def test_resolve_source_version_rehashes_prompt_and_provider_media(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    source_path = project_path / resource_relative_path("reference_videos", "E12U06")
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"accepted-unit")

    ref_path = project_path / "refs" / "character-a.png"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_bytes(b"reference-image")

    prompt = _compiled_prompt()
    source_sha = sha256_file(source_path)
    ref_sha = sha256_file(ref_path)
    ticket = _ticket(
        source_sha=source_sha,
        prompt_sha=provider_prompt_sha256(prompt),
        reference_sha=(ref_sha,),
    )

    media = StagedProviderMedia(
        index=0,
        role="reference_image",
        logical_type="character",
        logical_name="Character A",
        kind="character",
        source_locator="refs/character-a.png",
        staged_locator=".arcreel/tasks/task/provider_media/000_reference_image.png",
        sha256=ref_sha,
        size_bytes=ref_path.stat().st_size,
    )
    VersionManager(project_path).add_version(
        "reference_videos",
        "E12U06",
        prompt,
        source_file=source_path,
        execution_provider_id="minimax",
        execution_provider_model_id="MiniMax-H3",
        execution_backend_model_id="MiniMax-H3",
        execution_endpoint_guard="minimax-h3",
        execution_capability="r2v",
        execution_aspect_ratio="16:9",
        execution_resolution="768p",
        execution_generate_audio=True,
        execution_service_tier="default",
        execution_seed=None,
        execution_provider_media=[media.to_dict()],
    )

    resolved = resolve_h3_repair_source_version(project_path=project_path, ticket=ticket)

    assert resolved.media_sha256 == source_sha
    assert resolved.provider_prompt_sha256 == provider_prompt_sha256(prompt)
    assert resolved.provider_id == "minimax"
    assert resolved.provider_model == "MiniMax-H3"
    assert resolved.backend_model == "MiniMax-H3"
    assert resolved.endpoint_guard == "minimax-h3"
    assert resolved.reference_images == (ref_path.resolve(),)
    assert resolved.reference_audio_files == ()


def test_shot_reassembly_preserves_source_audio_and_exact_unit_duration(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    repair = tmp_path / "repair.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"source")
    repair.write_bytes(b"repair")

    source_facts = H3VideoStreamFacts(
        duration_seconds=15.0,
        fps=24.0,
        width=1920,
        height=1080,
        has_audio=True,
    )
    repair_facts = H3VideoStreamFacts(
        duration_seconds=4.8,
        fps=24.0,
        width=1280,
        height=720,
        has_audio=True,
    )

    commands: list[list[str]] = []

    def probe(path: Path) -> H3VideoStreamFacts:
        return source_facts if path == source else repair_facts

    def run(command) -> None:
        command_list = list(command)
        commands.append(command_list)
        Path(command_list[-1]).write_bytes(b"assembled")

    assemble_h3_shot_window(
        source,
        repair,
        output,
        _request(),
        probe_media=probe,
        run_command=run,
    )

    assert output.read_bytes() == b"assembled"
    assert len(commands) == 1
    joined = " ".join(commands[0])
    assert "trim=start=0:end=5.000000000" in joined
    assert "trim=start=10.000000000:end=15.000000000" in joined
    assert "0:a?" in joined
    assert "-c:a copy" in joined
    assert "-t 15.000000000" in joined
    assert "setpts=(PTS-STARTPTS)*1.041666666667" in joined
