"""Request-scoped prompt compiler options for reference-video generation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

PromptCompilerMode = Literal["auto", "h3_ref2va", "raw"]
PROMPT_COMPILER_MODES: frozenset[str] = frozenset({"auto", "h3_ref2va", "raw"})


def normalize_reference_image_labels(value: Sequence[object] | None) -> list[str] | None:
    """Trim UI/API labels without changing order.

    Empty input means "derive from the actual projected request assets".
    Blank elements are rejected because they create silent Subject/Picture drift.
    """
    if value is None:
        return None
    labels = [str(item).strip() for item in value]
    if not labels:
        return None
    if any(not label for label in labels):
        raise ValueError("reference_image_labels must not contain blank labels")
    return labels


def resolve_reference_image_labels(
    override: Sequence[object] | None,
    *,
    derived: Sequence[str],
) -> list[str]:
    """Resolve the exact labels for the exact provider reference-image order."""
    normalized = normalize_reference_image_labels(override)
    if normalized is None:
        return [str(item) for item in derived]
    if len(normalized) != len(derived):
        raise ValueError(
            "reference_image_labels must match the actual reference image count: "
            f"{len(normalized)} labels for {len(derived)} images"
        )
    return normalized


def normalize_prompt_compiler(value: object | None) -> PromptCompilerMode:
    if value is None:
        return "auto"
    normalized = str(value).strip().lower()
    if normalized not in PROMPT_COMPILER_MODES:
        raise ValueError(
            "prompt_compiler must be one of: auto, h3_ref2va, raw"
        )
    return normalized  # type: ignore[return-value]
