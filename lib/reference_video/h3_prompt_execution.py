"""Resolve and compile the final reference-video provider prompt.

This is the single deterministic seam shared by real execution and prompt preview.
Compilation must happen after the actual model and clamped reference-image order are
known, but before the execution checkpoint is persisted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from lib.reference_video.prompt_compiler_options import (
    PromptCompilerMode,
    normalize_prompt_compiler,
    resolve_reference_image_labels,
)
from lib.video_prompt_compilers.h3_prompt_compiler import (
    H3_DEFAULT_MAX_PROMPT_CHARS,
    H3PromptCompileError,
    compile_h3_ref2va_prompt,
    is_h3_model,
)


@dataclass(frozen=True)
class ProviderPromptCompilation:
    provider_prompt: str
    rendered_prompt: str
    model_id: str | None
    prompt_compiler: PromptCompilerMode
    compiler_applied: bool
    duration_seconds: int
    reference_source_names: tuple[str, ...]
    reference_image_labels: tuple[str, ...]
    max_prompt_chars: int | None


def _get_reference_field(entry: Any, field: str, default: str = "") -> str:
    ref = getattr(entry, "reference", None)
    if ref is None and isinstance(entry, Mapping):
        ref = entry.get("reference")
    if isinstance(ref, Mapping):
        value = ref.get(field, default)
    else:
        value = getattr(ref, field, default)
    return str(value or default).strip()


def _h3_kind(asset_type: str) -> str:
    if asset_type == "character":
        return "character"
    if asset_type == "scene":
        return "scene"
    if asset_type in {"product", "prop", "object"}:
        return "object"
    return "unknown"


def should_compile_reference_video_h3(
    *,
    payload: Mapping[str, Any],
    model_name: str | None,
    has_references: bool,
) -> bool:
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
    max_prompt_chars: int | None = None,
) -> ProviderPromptCompilation:
    """Produce the exact prompt to checkpoint and submit to the provider."""
    mode = normalize_prompt_compiler(payload.get("prompt_compiler"))
    source_names = [_get_reference_field(entry, "name") for entry in request_assets]
    labels = resolve_reference_image_labels(
        payload.get("reference_image_labels"),
        derived=source_names,
    )
    limit = int(max_prompt_chars) if max_prompt_chars else H3_DEFAULT_MAX_PROMPT_CHARS
    applied = should_compile_reference_video_h3(
        payload=payload,
        model_name=model_name,
        has_references=bool(request_assets),
    )

    if mode == "h3_ref2va" and not request_assets:
        raise H3PromptCompileError("h3_ref2va requires at least one actual provider reference image")

    if not applied:
        return ProviderPromptCompilation(
            provider_prompt=fallback_prompt,
            rendered_prompt=fallback_prompt,
            model_id=model_name,
            prompt_compiler=mode,
            compiler_applied=False,
            duration_seconds=int(duration_seconds),
            reference_source_names=tuple(source_names),
            reference_image_labels=tuple(labels),
            max_prompt_chars=max_prompt_chars,
        )

    reference_kinds = {
        source_name: _h3_kind(_get_reference_field(entry, "type"))
        for source_name, entry in zip(source_names, request_assets, strict=True)
    }
    compiled = compile_h3_ref2va_prompt(
        source_prompt=source_prompt,
        duration_seconds=duration_seconds,
        reference_count=len(request_assets),
        reference_source_names=source_names,
        reference_image_labels=labels,
        options={
            "reference_kinds": reference_kinds,
            "strict_reference_labels": False,
            "max_prompt_chars": limit,
        },
    )
    return ProviderPromptCompilation(
        provider_prompt=compiled,
        rendered_prompt=fallback_prompt,
        model_id=model_name,
        prompt_compiler=mode,
        compiler_applied=True,
        duration_seconds=int(duration_seconds),
        reference_source_names=tuple(source_names),
        reference_image_labels=tuple(labels),
        max_prompt_chars=max_prompt_chars or limit,
    )
