"""Phase 6 Slice 1 authoritative IO resolver for the H3 production projection.

The resolver reads existing ArcReel sources of truth and feeds the pure projection model.
It persists no control-plane lifecycle state.
"""

from __future__ import annotations

import asyncio

from lib.db import safe_session_factory
from lib.project_manager import ProjectManager, get_project_manager, is_reference_video_project
from lib.reference_video.h3_production_projection import (
    H3ProductionProjectProjection,
    H3ProductionUnitInventory,
    build_h3_production_projection,
)
from lib.reference_video.h3_repair_ticket_store import H3RepairTicketStore
from lib.script_editor import resolve_items
from lib.version_manager import VersionManager


def _inventory_from_project(
    *,
    project_name: str,
    project_manager: ProjectManager,
) -> tuple[H3ProductionUnitInventory, ...]:
    project = project_manager.load_project_readonly(project_name)
    if not is_reference_video_project(project):
        raise RuntimeError("H3 production projection requires a reference_video project")

    raw_episodes = project.get("episodes")
    if not isinstance(raw_episodes, list):
        raise RuntimeError("project episodes index is missing or invalid")

    project_path = project_manager.get_project_path(project_name)
    versions = VersionManager(project_path)
    inventory: list[H3ProductionUnitInventory] = []

    for entry in sorted(
        (item for item in raw_episodes if isinstance(item, dict)),
        key=lambda item: int(item.get("episode") or 0),
    ):
        episode = entry.get("episode")
        script_file = entry.get("script_file")
        if type(episode) is not int or episode <= 0:
            raise RuntimeError("project episode index contains an invalid episode number")
        if not isinstance(script_file, str) or not script_file.strip():
            raise RuntimeError(f"episode {episode} has no bound script_file")

        script = project_manager.load_script_readonly(project_name, script_file)
        items, id_field, kind = resolve_items(script)
        if kind != "video_units" or id_field != "unit_id":
            raise RuntimeError(
                f"episode {episode} is not a reference-video Unit script: kind={kind} id_field={id_field}"
            )

        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError(f"episode {episode} contains a non-object video Unit")
            unit_id = item.get("unit_id")
            if not isinstance(unit_id, str) or not unit_id.strip():
                raise RuntimeError(f"episode {episode} contains a video Unit without unit_id")
            inventory.append(
                H3ProductionUnitInventory(
                    episode=episode,
                    unit_id=unit_id.strip(),
                    current_version=versions.get_current_version("reference_videos", unit_id.strip()),
                )
            )

    return tuple(inventory)


async def resolve_h3_production_projection(
    *,
    project_name: str,
    project_manager: ProjectManager | None = None,
) -> H3ProductionProjectProjection:
    """Resolve the current project projection from authoritative persisted facts."""

    manager = project_manager or get_project_manager()
    normalized = manager.normalize_project_name(project_name)

    inventory = await asyncio.to_thread(
        _inventory_from_project,
        project_name=normalized,
        project_manager=manager,
    )

    async with safe_session_factory() as session:
        tickets = await H3RepairTicketStore(session).list_for_project(
            project_name=normalized,
            limit=500,
        )

    return build_h3_production_projection(
        project_name=normalized,
        inventory=inventory,
        tickets=tickets,
    )
