from __future__ import annotations

import pytest

from lib.generation_queue import GenerationQueue, reference_video_enqueue_payload
from lib.reference_video.h3_prompt_execution import (
    H3PromptCompileError,
    ProviderPromptCompilation,
    assert_provider_prompt_matches_preview,
    provider_prompt_sha256,
)
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload


def test_preview_fingerprint_hashes_exact_provider_prompt() -> None:
    compilation = ProviderPromptCompilation(
        provider_prompt="subject_definitions:\n完整 Prompt",
        rendered_prompt="legacy",
        model_id="minimax_h3_zm_u24",
        prompt_compiler="auto",
        compiler_applied=True,
        generation_mode="t2va",
        duration_seconds=8,
        reference_source_names=(),
        reference_image_labels=(),
        max_prompt_chars=7000,
    )
    payload = build_reference_prompt_preview_payload(compilation)
    assert payload["provider_prompt_sha256"] == provider_prompt_sha256(payload["provider_prompt"])


def test_runtime_preview_lock_accepts_exact_text_and_rejects_any_change() -> None:
    prompt = "A\nB\nC"
    expected = provider_prompt_sha256(prompt)
    assert_provider_prompt_matches_preview(provider_prompt=prompt, expected_sha256=expected)
    with pytest.raises(H3PromptCompileError, match="changed after preview"):
        assert_provider_prompt_matches_preview(
            provider_prompt=prompt + " ",
            expected_sha256=expected,
        )


def test_reference_queue_payload_preserves_v6_compiler_facts() -> None:
    canonical = {"unit": {"unit_id": "E01-U06"}, "registries": {}}
    payload = reference_video_enqueue_payload(
        {
            "reference_request_options": {"narration_delivery": "post_production"},
            "reference_image_labels": ["沈知意", "陆念"],
            "prompt_compiler": "auto",
            "canonical_director": canonical,
            "expected_provider_prompt_sha256": "a" * 64,
            "discard_me": "x",
        },
        script_file="scripts/episode_1.json",
    )
    assert payload["reference_image_labels"] == ["沈知意", "陆念"]
    assert payload["prompt_compiler"] == "auto"
    assert payload["canonical_director"] == canonical
    assert payload["expected_provider_prompt_sha256"] == "a" * 64
    assert "discard_me" not in payload


async def test_active_reference_task_rejects_a_different_preview_lock(db_factory) -> None:
    queue = GenerationQueue(session_factory=db_factory)
    base = {
        "reference_request_options": {"narration_delivery": "post_production"},
        "prompt_compiler": "auto",
        "expected_provider_prompt_sha256": "a" * 64,
    }
    first = await queue.enqueue_task(
        project_name="demo",
        task_type="reference_video",
        media_type="video",
        resource_id="E1U1",
        payload=base,
        script_file="episode_01.json",
        provider_id="video-provider",
    )
    assert first["deduped"] is False

    same = await queue.enqueue_task(
        project_name="demo",
        task_type="reference_video",
        media_type="video",
        resource_id="E1U1",
        payload=base,
        script_file="episode_01.json",
        provider_id="video-provider",
    )
    assert same["deduped"] is True
    assert same["task_id"] == first["task_id"]

    with pytest.raises(RuntimeError):
        await queue.enqueue_task(
            project_name="demo",
            task_type="reference_video",
            media_type="video",
            resource_id="E1U1",
            payload={**base, "expected_provider_prompt_sha256": "b" * 64},
            script_file="episode_01.json",
            provider_id="video-provider",
        )
