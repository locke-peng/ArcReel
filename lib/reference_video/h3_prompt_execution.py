"""Resolve and compile the final reference-video provider prompt."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lib.reference_video.prompt_compiler_options import (
    PromptCompilerMode,
    normalize_prompt_compiler,
)
from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3_MAX_PROMPT_CHARS,
    compile_h3_ref2va_prompt,
    is_h3_model,
)


def should_compile_reference_video_h3(
    *,
    payload: Mapping[str, Any],
    model_name: str | None,
    has_references: bool,
) -> bool:
    """Whether H3 prompt compilation applies."""
    del has_references  # kept for call-site compatibility
    mode = normalize_prompt_compiler(payload.get("prompt_compiler"))
    if mode == "raw":
        return False
    return mode == "h3_ref2va" or (mode == "auto" and is_h3_model(model_name))


def compile_reference_video_provider_prompt(
    *,
    source_prompt: str,
    fallback_prompt: str,
    model_name: str | None,
    duration_seconds: int,
    request_assets: Sequence[Any],
    payload: Mapping[str, Any],
    max_prompt_chars: int | None = None,
) -> str:
    """Produce the exact prompt to checkpoint, preview, and submit to the provider."""
    mode = normalize_prompt_compiler(payload.get("prompt_compiler"))
    applied = should_compile_reference_video_h3(
        payload=payload,
        model_name=model_name,
        has_references=bool(request_assets),
    )

    if not applied or not request_assets:
        return fallback_prompt

    compiled = compile_h3_ref2va_prompt(
        source_prompt=source_prompt,
        duration_seconds=duration_seconds,
        reference_count=len(request_assets),
        options={
            "max_prompt_chars": max_prompt_chars or H3_MAX_PROMPT_CHARS,
        },
    )
    return compiled
