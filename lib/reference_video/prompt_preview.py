"""Read-only response shaping for reference-video provider prompt preview."""

from __future__ import annotations

from typing import Any

from lib.reference_video.h3_prompt_execution import ProviderPromptCompilation


def build_reference_prompt_preview_payload(
    compilation: ProviderPromptCompilation,
) -> dict[str, Any]:
    prompt = compilation.provider_prompt
    return {
        "provider_prompt": prompt,
        "rendered_prompt": compilation.rendered_prompt,
        "model_id": compilation.model_id,
        "prompt_compiler": compilation.prompt_compiler,
        "compiler_applied": compilation.compiler_applied,
        "duration_seconds": compilation.duration_seconds,
        "prompt_chars": len(prompt),
        "max_prompt_chars": compilation.max_prompt_chars,
        "reference_mapping": [
            {
                "index": index,
                "picture": f"<Picture {index}>",
                "subject": f"<Subject {index}>",
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
