from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.db import safe_session_factory
from lib.reference_video.h3_production_projection import H3ProductionUnitState
from lib.reference_video.h3_repair_ticket import H3RepairScopeKind, H3RepairTicket, H3RepairTicketStatus
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketStore
from server.services.h3_production_control import resolve_h3_production_projection


def _write_project(root: Path, name: str) -> Path:
    project = root / name
    (project / "scripts").mkdir(parents=True)
    (project / "versions").mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "name": name,
                "generation_mode": "reference_video",
                "episodes": [
                    {"episode": 1, "script_file": "episode_1.json"},
                    {"episode": 2, "script_file": "episode_2.json"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "episode": 1,
                "video_units": [
                    {"unit_id": "E1U01", "duration_seconds": 5, "shots": []},
                    {"unit_id": "E1U02", "duration_seconds": 5, "shots": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "scripts" / "episode_2.json").write_text(
        json.dumps(
            {
                "episode": 2,
                "video_units": [
                    {"unit_id": "E2U01", "duration_seconds": 5, "shots": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "versions" / "versions.json").write_text(
        json.dumps(
            {
                "reference_videos": {
                    "E1U02": {"current_version": 1, "versions": [{"version": 1, "file": "versions/reference_videos/E1U02/v1.mp4", "prompt": "p"}]},
                    "E2U01": {"current_version": 2, "versions": [{"version": 2, "file": "versions/reference_videos/E2U01/v2.mp4", "prompt": "p"}]},
                }
            }
        ),
        encoding="utf-8",
    )
    return project


def _ticket(unit_id: str) -> H3RepairTicket:
    payload = dict(
        schema_version=1,
        status=H3RepairTicketStatus.AWAITING_APPROVAL,
        approval_eligible=True,
        unit_id=unit_id,
        shot_id=f"{unit_id}-S01",
        scope_kind=H3RepairScopeKind.SHOT,
        start_seconds=0.0,
        end_seconds=5.0,
        region=None,
        failure_class="large_semantic_failure",
        repair_action="regenerate_shot",
        provider_recall_required=True,
        canonical_violation="acceptance",
        planner_reason="acceptance",
        source_media_sha256="a" * 64,
        provider_prompt_sha256="b" * 64,
        reference_sha256=(),
        evidence_frames=(),
        tags=(),
        provider_task_id=None,
        provider_run_id=None,
        provider_artifact_id=None,
    )
    seed = H3RepairTicket(ticket_id="", ticket_sha256="", **payload)
    digest = seed.compute_sha256()
    return H3RepairTicket(ticket_id=f"h3rt_{digest[:24]}", ticket_sha256=digest, **payload)


@pytest.mark.asyncio
async def test_resolver_reads_project_scripts_versions_and_tickets(tmp_path: Path, monkeypatch) -> None:
    projects = tmp_path / "projects"
    _write_project(projects, "demo")
    monkeypatch.setenv("AI_ANIME_PROJECTS", str(projects))

    async with safe_session_factory() as session:
        await H3RepairTicketStore(session).persist(project_name="demo", ticket=_ticket("E2U01"))
        await session.commit()

    projection = await resolve_h3_production_projection(project_name="demo")
    by_unit = {
        unit.unit_id: unit
        for episode in projection.episodes
        for unit in episode.units
    }

    assert by_unit["E1U01"].current_version == 0
    assert by_unit["E1U01"].state is H3ProductionUnitState.NOT_STARTED
    assert by_unit["E1U02"].current_version == 1
    assert by_unit["E1U02"].state is H3ProductionUnitState.COMPLETE
    assert by_unit["E2U01"].current_version == 2
    assert by_unit["E2U01"].state is H3ProductionUnitState.AWAITING_APPROVAL
    assert by_unit["E2U01"].ticket_ids


@pytest.mark.asyncio
async def test_resolver_rejects_non_reference_video_project(tmp_path: Path, monkeypatch) -> None:
    projects = tmp_path / "projects"
    project = _write_project(projects, "demo")
    payload = json.loads((project / "project.json").read_text(encoding="utf-8"))
    payload["generation_mode"] = "storyboard"
    (project / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("AI_ANIME_PROJECTS", str(projects))

    with pytest.raises(RuntimeError, match="requires a reference_video project"):
        await resolve_h3_production_projection(project_name="demo")
