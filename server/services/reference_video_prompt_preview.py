"""Read-only final provider-prompt preview for one reference-video unit.

This service deliberately reuses ArcReel's current request projection, prompt renderer,
and the H3 compiler seam.  It never enqueues a task, calls a media provider, persists an
execution checkpoint, or mutates the script.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any, Literal

from lib.db.base import DEFAULT_USER_ID
from lib.generation_queue import GenerationQueue
from lib.narration_delivery import POST_PRODUCTION, USE_TTS, NarrationDelivery
from lib.project_manager import ProjectManager, get_project_manager
from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from lib.reference_video.request_projection import ReferenceRequestOptions, project_reference_unit_request
from lib.reference_video.prompt_render import render_video_unit_prompt, resolve_reference_audio_paths
from lib.reference_video.voice_settings import VoiceRenderSettings
from lib.speech_composition import video_unit_replan_problems
from server.services.narration_delivery_tasks import (
    prepare_current_reference_video_request_options,
    tts_task_in_progress,
)
from server.services.video_caps import project_video_caps

PromptCompilerMode = Literal["auto", "h3_ref2va", "raw"]


async def preview_reference_video_provider_prompt(
    *,
    project_name: str,
    script_file: str,
    unit_id: str,
    prompt_override: str | None = None,
    reference_image_labels: list[str] | None = None,
    prompt_compiler: PromptCompilerMode = "auto",
    narration_delivery: NarrationDelivery = POST_PRODUCTION,
    confirmed_request_duration_seconds: int | None = None,
    user_id: str = DEFAULT_USER_ID,
    projects: ProjectManager | None = None,
    queue: GenerationQueue | None = None,
) -> dict[str, Any]:
    """Return the exact provider-prompt shape for the current project configuration.

    ``prompt_override`` is an in-memory draft only.  Reference numbering comes from
    ``projection.request_assets`` after availability checks and provider clamping, never
    from mention order in the editor.
    """
    manager = projects if projects is not None else get_project_manager()
    project = manager.load_project(project_name)
    project_path = manager.get_project_path(project_name)
    script = manager.load_script(project_name, script_file)
    units = script.get("video_units") or []
    saved = next(
        (unit for unit in units if isinstance(unit, dict) and unit.get("unit_id") == unit_id),
        None,
    )
    if saved is None:
        raise ValueError(f"unit not found: {unit_id}")

    unit = deepcopy(saved)
    if prompt_override is not None:
        unit["text"] = prompt_override
    if not str(unit.get("text") or "").strip():
        raise ValueError("reference video prompt must not be blank")
    if video_unit_replan_problems(unit):
        raise ValueError(f"unit needs replanning: {unit_id}")

    request_options = ReferenceRequestOptions(
        narration_delivery=narration_delivery,
        confirmed_request_duration_seconds=confirmed_request_duration_seconds,
    )
    in_progress = (
        await tts_task_in_progress(
            project_name=project_name,
            resource_id=unit_id,
            script_file=script_file,
            user_id=user_id,
            queue=queue,
        )
        if narration_delivery == USE_TTS
        else False
    )
    current_options = await prepare_current_reference_video_request_options(
        project=project,
        script=script,
        script_file=script_file,
        unit=unit,
        project_path=project_path,
        options=request_options,
        project_name=project_name,
        user_id=user_id,
        tts_in_progress=in_progress,
    )
    projection = await project_reference_unit_request(
        project=project,
        script=script,
        unit=unit,
        project_path=project_path,
        options=current_options,
        tts_in_progress=in_progress,
        current_options_materialized=True,
    )
    if projection.blocking_problems:
        first = projection.blocking_problems[0]
        raise ValueError(f"{first.code}: {first.parameters()}")
    if projection.request_duration is None:
        raise ValueError("reference request projection has no duration tier")
    candidate = projection.provider_candidate
    if candidate is None:
        raise ValueError("reference request projection has no provider candidate")

    caps = await project_video_caps(
        project,
        degraded_to="final provider prompt preview falls back to soft voice constraints",
        generation_type=candidate.generation_type,
    )
    audio_paths = await asyncio.to_thread(resolve_reference_audio_paths, project, project_path)
    rendered = render_video_unit_prompt(
        unit,
        project,
        VoiceRenderSettings.from_caps(caps, audio_ready=audio_paths),
        request_references=[entry.reference for entry in projection.request_assets],
    )
    prompt_limit = caps.get("max_prompt_chars")
    max_prompt_chars = (
        int(prompt_limit)
        if isinstance(prompt_limit, int) and not isinstance(prompt_limit, bool) and prompt_limit > 0
        else None
    )
    compile_payload: dict[str, Any] = {"prompt_compiler": prompt_compiler}
    if reference_image_labels:
        compile_payload["reference_image_labels"] = reference_image_labels

    compilation = compile_reference_video_provider_prompt(
        source_prompt=str(unit.get("text") or ""),
        fallback_prompt=rendered.prompt,
        model_name=candidate.model_id,
        duration_seconds=projection.request_duration.seconds,
        request_assets=projection.request_assets,
        payload=compile_payload,
        max_prompt_chars=max_prompt_chars,
    )
    return build_reference_prompt_preview_payload(compilation)


__all__ = ["preview_reference_video_provider_prompt"]
