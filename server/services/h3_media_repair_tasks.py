"""Production worker for post-provider H3 deterministic media repair."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from lib.async_thread import run_noninterruptible_sync
from lib.reference_video.h3_media_pipeline import (
    EvidenceChain,
    H3MediaPipelineError,
    sha256_file,
    sha256_text,
)
from lib.reference_video.h3_repair_executors import (
    append_repair_evidence,
    execute_deterministic_repair,
)
from lib.reference_video.h3_repair_task import H3RepairTaskPlan
from lib.resource_paths import resource_relative_path
from lib.version_manager import VersionManager
from server.services.generation_tasks import get_project_manager


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)



def _allocate_staging_path(current_path: Path, resource_id: str) -> Path:
    staged_path = await asyncio.to_thread(_allocate_staging_path, current_path, resource_id)
    return staged_path


def _current_version(versions: VersionManager, resource_id: str) -> int:
    history = versions.get_versions("reference_videos", resource_id) or {}
    value = history.get("current_version")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise H3MediaPipelineError("H3 repair requires a tracked current reference-video version")
    return value


def _load_evidence(path: Path, *, unit_id: str) -> EvidenceChain:
    if not path.is_file():
        raise H3MediaPipelineError("H3 provider evidence root is missing; repair is fail-closed")
    chain = EvidenceChain.from_json(path.read_text(encoding="utf-8"))
    if chain.unit_id != unit_id:
        raise H3MediaPipelineError(
            f"H3 evidence unit mismatch: {chain.unit_id!r} != {unit_id!r}"
        )
    return chain


async def execute_h3_media_repair_task(
    project_name: str,
    resource_id: str,
    payload: dict[str, Any],
    *,
    user_id: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Execute one local deterministic repair against the current H3 provider artifact.

    The worker never calls a provider. The submitted plan must already contain normalized
    QA observations and deterministic repair facts. Semantic issues are rejected by the
    planner contract before media execution.
    """

    del user_id
    plan = H3RepairTaskPlan.from_payload(payload)

    pm = get_project_manager()
    project_path = await asyncio.to_thread(pm.get_project_path, project_name)
    current_path = project_path / resource_relative_path("reference_videos", resource_id)
    evidence_path = project_path / "reference_videos" / "evidence" / f"{resource_id}.json"

    if not current_path.is_file():
        raise H3MediaPipelineError(f"current reference video is missing: {resource_id}")

    source_sha256 = await asyncio.to_thread(sha256_file, current_path)
    if source_sha256 != plan.expected_source_sha256:
        raise H3MediaPipelineError(
            "current video changed after QA; expected_source_sha256 no longer matches"
        )

    chain = await asyncio.to_thread(_load_evidence, evidence_path, unit_id=resource_id)
    if source_sha256 not in {node.artifact_sha256 for node in chain.nodes}:
        raise H3MediaPipelineError(
            "current video SHA is not present in the persisted H3 evidence chain"
        )

    versions = VersionManager(project_path)
    expected_current_version = await asyncio.to_thread(_current_version, versions, resource_id)

    current_path.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_name = tempfile.mkstemp(
        prefix=f".{resource_id}.h3-repair.",
        suffix=".mp4",
        dir=current_path.parent,
    )
    os.close(fd)
    staged_path = Path(staged_name)
    staged_path.unlink(missing_ok=True)

    try:
        request = plan.to_request(current_path, staged_path)
        await run_noninterruptible_sync(execute_deterministic_repair, request)
        if not await asyncio.to_thread(staged_path.is_file):
            raise H3MediaPipelineError("deterministic repair completed without an output file")

        updated_chain = await asyncio.to_thread(
            append_repair_evidence,
            chain=chain,
            request=request,
            output_path=staged_path,
            metadata=plan.evidence_metadata(),
        )
        evidence_json = updated_chain.to_json()
        repaired_sha256 = sha256_file(staged_path)

        def _select_only_if_source_is_still_current() -> bool:
            return current_path.is_file() and sha256_file(current_path) == source_sha256

        def _persist_selected_evidence() -> None:
            _atomic_write_text(evidence_path, evidence_json)

        committed = await run_noninterruptible_sync(
            versions.commit_staged_paid_version,
            "reference_videos",
            resource_id,
            f"h3_media_repair:{plan.action.value}",
            staged_file=staged_path,
            current_file=current_path,
            select_current=_select_only_if_source_is_still_current,
            expected_current_version=expected_current_version,
            on_select=_persist_selected_evidence,
            h3_media_repair=True,
            h3_media_repair_action=plan.action.value,
            h3_media_repair_source_sha256=source_sha256,
            h3_media_repair_output_sha256=repaired_sha256,
            h3_media_repair_evidence_sha256=sha256_text(evidence_json),
            provider_recalled=False,
        )
        if not committed.selected:
            raise H3MediaPipelineError(
                "current video/version changed while repair was executing; repaired output was not selected"
            )

        return {
            "resource_type": "reference_videos",
            "resource_id": resource_id,
            "version": committed.version,
            "file_path": f"reference_videos/{resource_id}.mp4",
            "repair_action": plan.action.value,
            "source_sha256": source_sha256,
            "output_sha256": repaired_sha256,
            "evidence_sha256": sha256_text(evidence_json),
            "provider_recalled": False,
        }
    finally:
        await asyncio.to_thread(staged_path.unlink, missing_ok=True)
