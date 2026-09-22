"""Response shaping for the read-only reference-video provider prompt preview."""

from __future__ import annotations

from typing import Any, Sequence


def build_reference_prompt_preview_payload(
    *,
    provider_prompt: str,
    rendered_prompt: str,
    model_id: str | None,
    prompt_compiler: str,
    compiler_applied: bool,
    duration_seconds: int,
    reference_labels: Sequence[str],
    max_prompt_chars: int | None = None,
) -> dict[str, Any]:
    """Build the browser-facing preview without mutating project/task state."""
    return {
        "provider_prompt": provider_prompt,
        "rendered_prompt": rendered_prompt,
        "model_id": model_id,
        "prompt_compiler": prompt_compiler,
        "compiler_applied": compiler_applied,
        "duration_seconds": int(duration_seconds),
        "prompt_chars": len(provider_prompt),
        "max_prompt_chars": int(max_prompt_chars) if max_prompt_chars else None,
        "reference_mapping": [
            {
                "index": index,
                "picture": f"<Picture {index}>",
                "subject": f"<Subject {index}>",
                "label": str(label),
            }
            for index, label in enumerate(reference_labels, start=1)
        ],
    }
