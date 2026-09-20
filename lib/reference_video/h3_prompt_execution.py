"""MiniMax H3 prompt compilation at the reference-video execution boundary.

Compile *before* the immutable provider checkpoint is persisted. ArcReel's reference
video executor already knows the final clamped reference-image order and actual backend
model at this point, so this is the safest place to resolve labels and compiler mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lib.reference_video.prompt_compiler_options import (
    normalize_prompt_compiler,
    resolve_reference_image_labels,
)
from lib.video_prompt_compilers.h3_prompt_compiler import (
    compile_h3_ref2va_prompt,
    is_h3_model,
)


def _h3_kind(asset_type: str) -> str:
    if asset_type == "character":
        return "character"
    if asset_type == "scene":
        return "scene"
    if asset_type in {"product", "prop"}:
        return "object"
    return "unknown"


def should_compile_reference_video_h3(
    *,
    payload: Mapping[str, Any],
    model_name: str | None,
    has_references: bool,
) -> bool:
    """Whether this request changes ArcReel's normal provider prompt to H3 Ref2VA."""
    if not has_references:
        return False
    mode = normalize_prompt_compiler(payload.get("prompt_compiler"))
    return mode == "h3_ref2va" or (mode == "auto" and is_h3_model(model_name))


def compile_reference_video_provider_prompt(
    *,
    source_prompt: str,
    fallback_prompt: str,
    model_name: str | None,
    duration_seconds: int,
    request_assets: Sequence[Any],
    payload: Mapping[str, Any],
) -> str:
    """Return the exact prompt that should be checkpointed and submitted."""
    derived_labels = [str(entry.reference.name) for entry in request_assets]
    labels = resolve_reference_image_labels(
        payload.get("reference_image_labels"),
        derived=derived_labels,
    )

    if not should_compile_reference_video_h3(
        payload=payload,
        model_name=model_name,
        has_references=bool(request_assets),
    ):
        return fallback_prompt

    reference_kinds = {
        label: _h3_kind(str(entry.reference.type))
        for label, entry in zip(labels, request_assets, strict=True)
    }

    return compile_h3_ref2va_prompt(
        source_prompt=source_prompt,
        duration_seconds=duration_seconds,
        reference_count=len(request_assets),
        reference_image_labels=labels,
        options={
            "reference_kinds": reference_kinds,
            # Product references may legitimately expand to multiple images bearing
            # the same logical name, so label uniqueness is not an execution invariant.
            "strict_reference_labels": False,
        },
    )