"""Read-only response shaping for reference-video provider prompt preview."""

from __future__ import annotations

import re
from typing import Any

from lib.reference_video.h3_prompt_execution import (
    ProviderPromptCompilation,
    provider_prompt_sha256,
)


def _subject_label_for_picture(prompt: str, index: int) -> str:
    picture = f"<Picture {index}>"
    for line in prompt.splitlines():
        if picture not in line:
            continue
        match = re.search(r"<Subject\s+(\d+)>", line)
        if match is not None:
            return f"<Subject {match.group(1)}>"
    return f"<Subject {index}>"


def build_reference_prompt_preview_payload(
    compilation: ProviderPromptCompilation,
) -> dict[str, Any]:
    prompt = compilation.provider_prompt
    return {
        "provider_prompt": prompt,
        "provider_prompt_sha256": provider_prompt_sha256(prompt),
        "rendered_prompt": compilation.rendered_prompt,
        "model_id": compilation.model_id,
        "prompt_compiler": compilation.prompt_compiler,
        "compiler_applied": compilation.compiler_applied,
        "generation_mode": compilation.generation_mode,
        "duration_seconds": compilation.duration_seconds,
        "prompt_chars": len(prompt),
        "max_prompt_chars": compilation.max_prompt_chars,
        "reference_mapping": [
            {
                "index": index,
                "picture": f"<Picture {index}>",
                "subject": _subject_label_for_picture(prompt, index),
                "label": label,
                "source_name": source_name,
            }
            for index, (source_name, label) in enumerate(
                zip(
                    compilation.reference_source_names,
                    compilation.reference_image_labels,
                    strict=True,
                ),
                start=1,
            )
        ],
    }
