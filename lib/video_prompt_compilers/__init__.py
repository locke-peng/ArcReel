"""Video prompt compiler dispatch.

Keep provider/backend request builders unaware of authoring syntax. Compilation happens
immediately before ``backend.generate`` so every endpoint receives the final prompt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .h3_prompt_compiler import compile_h3_video_request, is_h3_model

if TYPE_CHECKING:
    from lib.video_backends.base import VideoGenerationRequest


def compile_video_request_prompt(
    request: "VideoGenerationRequest",
    *,
    model: str | None,
) -> "VideoGenerationRequest":
    """Compile provider-specific prompt structure while preserving request payload fields.

    Current rule:
    - MiniMax H3 + reference_images => H3 Ref2VA six-section compiler.
    - Everything else => unchanged request.

    Explicit request fields let callers override/disable future dispatch behavior.
    """
    compiler = request.prompt_compiler
    if compiler == "raw":
        return request

    should_h3 = compiler == "h3_ref2va" or (
        compiler is None and is_h3_model(model) and bool(request.reference_images)
    )
    if not should_h3:
        return request

    return compile_h3_video_request(
        request,
        reference_image_labels=request.reference_image_labels,
        options=request.prompt_compiler_options,
    )