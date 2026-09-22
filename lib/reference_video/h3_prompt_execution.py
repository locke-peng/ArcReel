"""Resolve and compile the final reference-video provider prompt.

V6 keeps preview/runtime on one deterministic seam and adds:
- H3 T2VA when the resolved H3 request carries zero reference images
- Canonical Director structured compilation
- generation-mode reporting
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import hmac
import re
from typing import Any

from lib.reference_video.prompt_compiler_options import (
    PromptCompilerMode,
    normalize_prompt_compiler,
    resolve_reference_image_labels,
)
from lib.video_prompt_compilers.h3_director_compiler import (
    H3DirectorCompileError,
    compile_h3_director_prompt,
    compile_h3_text_t2va_prompt,
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
    generation_mode: str
    duration_seconds: int
    reference_source_names: tuple[str, ...]
    reference_image_labels: tuple[str, ...]
    max_prompt_chars: int | None


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def provider_prompt_sha256(prompt: str) -> str:
    """Stable fingerprint of the exact UTF-8 provider prompt text."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def assert_provider_prompt_matches_preview(
    *,
    provider_prompt: str,
    expected_sha256: object | None,
) -> None:
    """Refuse provider submission if the prompt differs from the previewed text."""
    if expected_sha256 is None:
        return
    expected = str(expected_sha256).strip().lower()
    if not _SHA256_RE.fullmatch(expected):
        raise H3PromptCompileError(
            "expected_provider_prompt_sha256 must be a 64-character lowercase SHA-256 hex digest"
        )
    actual = provider_prompt_sha256(provider_prompt)
    if not hmac.compare_digest(actual, expected):
        raise H3PromptCompileError(
            "final provider prompt changed after preview; preview again before generation"
        )


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
    """Whether H3 prompt compilation applies.

    V6 deliberately does *not* require references for auto mode: an H3 model with no
    actual provider images compiles as T2VA.  h3_ref2va is still strict and fails later
    when no actual provider reference image exists.
    """
    del has_references  # kept in signature for call-site compatibility
    mode = normalize_prompt_compiler(payload.get("prompt_compiler"))
    if mode == "raw":
        return False
    return mode == "h3_ref2va" or (mode == "auto" and is_h3_model(model_name))


def _canonical_director(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = payload.get("canonical_director")
    return value if isinstance(value, Mapping) else None


def compile_reference_video_provider_prompt(
    *,
    source_prompt: str,
    fallback_prompt: str,
    model_name: str | None,
    duration_seconds: int,
    request_assets: Sequence[Any],
    payload: Mapping[str, Any],
    max_prompt_chars: int | None = None,
    unit_id: str | None = None,
) -> ProviderPromptCompilation:
    """Produce the exact prompt to checkpoint, preview, and submit to the provider."""
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
            generation_mode="raw",
            duration_seconds=int(duration_seconds),
            reference_source_names=tuple(source_names),
            reference_image_labels=tuple(labels),
            max_prompt_chars=max_prompt_chars,
        )

    reference_kinds = {
        source_name: _h3_kind(_get_reference_field(entry, "type"))
        for source_name, entry in zip(source_names, request_assets, strict=True)
    }
    canonical = _canonical_director(payload)
    if canonical is not None:
        try:
            compiled, generation_mode = compile_h3_director_prompt(
                canonical_director=canonical,
                unit_id=unit_id,
                duration_seconds=duration_seconds,
                reference_source_names=source_names,
                reference_image_labels=labels,
                reference_kinds=reference_kinds,
                max_prompt_chars=limit,
            )
        except H3DirectorCompileError as exc:
            raise H3PromptCompileError(str(exc)) from exc
    elif request_assets:
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
        generation_mode = "ref2va"
    else:
        try:
            compiled = compile_h3_text_t2va_prompt(
                source_prompt=source_prompt,
                duration_seconds=duration_seconds,
                max_prompt_chars=limit,
            )
        except H3DirectorCompileError as exc:
            raise H3PromptCompileError(str(exc)) from exc
        generation_mode = "t2va"

    return ProviderPromptCompilation(
        provider_prompt=compiled,
        rendered_prompt=fallback_prompt,
        model_id=model_name,
        prompt_compiler=mode,
        compiler_applied=True,
        generation_mode=generation_mode,
        duration_seconds=int(duration_seconds),
        reference_source_names=tuple(source_names),
        reference_image_labels=tuple(labels),
        max_prompt_chars=max_prompt_chars or limit,
    )
