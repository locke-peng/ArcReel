from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from lib.reference_video.h3_prompt_execution import (
    compile_reference_video_provider_prompt,
    should_compile_reference_video_h3,
)
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from lib.video_backends.base import VideoGenerationRequest
from lib.video_prompt_compilers import compile_video_request_prompt

FIXTURE = Path(__file__).parent / "fixtures" / "e01_canonical_director_v1_2.json"


@dataclass(frozen=True)
class Ref:
    type: str
    name: str


@dataclass(frozen=True)
class Entry:
    reference: Ref


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _name(payload: dict, entity_id: str) -> str:
    return payload["registries"]["characters"][entity_id]["name"]


def _timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    minutes, rem = divmod(total_ms, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _source_from_unit(payload: dict, unit: dict, ref_labels: list[str] | None = None) -> str:
    lines: list[str] = []
    if ref_labels:
        lines.append(" ".join(f"@[{label}]" for label in ref_labels))
    for index, shot in enumerate(unit["shots"], start=1):
        if index == 1:
            lines.append("[Shot 1]")
        else:
            lines.append(f"[Shot {index}] At {_timestamp(float(shot['start_sec']))}")
        lines.append(str(shot["action"]))
        for dialogue in shot.get("dialogue", []):
            speaker = _name(payload, dialogue["speaker_id"])
            lines.append(f"@[{speaker}]：{{{dialogue['text']}}}")
    return "\n".join(lines)


def _entries(*names: str) -> list[Entry]:
    return [Entry(Ref("character", name)) for name in names]


def _compile_ref2va(payload: dict, unit_id: str, labels: list[str]) -> tuple[str, dict, VideoGenerationRequest]:
    unit = next(u for u in payload["units"] if u["unit_id"] == unit_id)
    source = _source_from_unit(payload, unit, labels)
    assets = _entries(*labels)
    provider_prompt = compile_reference_video_provider_prompt(
        source_prompt=source,
        fallback_prompt=f"LEGACY::{unit_id}",
        model_name="minimax_h3_zm_u24",
        duration_seconds=int(unit["duration_sec"]),
        request_assets=assets,
        payload={
            "prompt_compiler": "auto",
            "reference_image_labels": labels,
            # V3 ignores this future field; keeping it here proves that merely supplying
            # Canonical data does not make it a V3 compiler input.
            "canonical_director": {"registries": payload["registries"], "unit": unit},
        },
    )
    preview = build_reference_prompt_preview_payload(
        provider_prompt=provider_prompt,
        rendered_prompt=f"LEGACY::{unit_id}",
        model_id="minimax_h3_zm_u24",
        prompt_compiler="auto",
        compiler_applied=True,
        duration_seconds=int(unit["duration_sec"]),
        reference_labels=labels,
        max_prompt_chars=7000,
    )
    request = VideoGenerationRequest(
        prompt=provider_prompt,
        output_path=Path("/tmp") / f"{unit_id}.mp4",
        aspect_ratio=unit["aspect_ratio"],
        duration_seconds=int(unit["duration_sec"]),
        reference_images=[Path(f"/tmp/ref-{i}.png") for i in range(1, len(labels) + 1)],
    )
    # This is the lower V1 pre-backend compiler seam. Because the V2 execution seam has
    # already produced a complete six-section prompt, the lower compiler must be idempotent.
    runtime_request = compile_video_request_prompt(request, model="minimax_h3_zm_u24")
    return provider_prompt, preview, runtime_request


def test_e01_fixture_integrity() -> None:
    payload = _load()
    assert payload["episode"]["episode_id"] == "E01"
    assert payload["episode"]["duration_sec"] == 105
    assert payload["episode"]["unit_count"] == 11
    assert payload["episode"]["shot_count"] == 33
    assert len(payload["units"]) == 11
    assert sum(int(u["duration_sec"]) for u in payload["units"]) == 105
    assert sum(len(u["shots"]) for u in payload["units"]) == 33
    assert all(4 <= int(u["duration_sec"]) <= 15 for u in payload["units"])


@pytest.mark.parametrize("unit_index", range(11))
def test_v3_e01_zero_reference_auto_remains_legacy(unit_index: int) -> None:
    """Historical V3 characterization: auto H3 is Ref2VA-only."""
    payload = _load()
    unit = payload["units"][unit_index]
    fallback = f"LEGACY::{unit['unit_id']}"
    provider_prompt = compile_reference_video_provider_prompt(
        source_prompt=_source_from_unit(payload, unit),
        fallback_prompt=fallback,
        model_name="minimax_h3_zm_u24",
        duration_seconds=int(unit["duration_sec"]),
        request_assets=[],
        payload={
            "prompt_compiler": "auto",
            "canonical_director": {"registries": payload["registries"], "unit": unit},
        },
    )
    assert should_compile_reference_video_h3(
        payload={"prompt_compiler": "auto"},
        model_name="minimax_h3_zm_u24",
        has_references=False,
    ) is False
    assert provider_prompt == fallback


def test_v3_u04_ref2va_preview_equals_final_runtime_request_prompt() -> None:
    payload = _load()
    provider, preview, runtime = _compile_ref2va(payload, "E01-U04", ["沈知意", "陆念"])

    assert provider.startswith("subject_definitions:")
    assert preview["provider_prompt"] == provider
    assert runtime.prompt == provider
    assert preview["prompt_chars"] == len(provider)
    assert preview["reference_mapping"] == [
        {"index": 1, "picture": "<Picture 1>", "subject": "<Subject 1>", "label": "沈知意"},
        {"index": 2, "picture": "<Picture 2>", "subject": "<Subject 2>", "label": "陆念"},
    ]

    # V3 has preview equality under stable inputs, but no V6.1 cryptographic lock.
    assert "provider_prompt_sha256" not in preview

    assert "<Subject 1> (S1) says" in provider
    assert "<Subject 2> (S2) says" in provider
    assert "<d>[Chinese] 念念。</d>" in provider
    assert "<d>[Chinese] 妈妈！</d>" in provider


def test_v3_u04_dialogue_is_hoisted_after_authored_shot_body() -> None:
    payload = _load()
    provider, _, _ = _compile_ref2va(payload, "E01-U04", ["沈知意", "陆念"])

    last_authored_shot = provider.rindex("[Shot 3]")
    first_dialogue = provider.index("<d>[Chinese] 念念。</d>")
    assert last_authored_shot < first_dialogue


def test_v3_u06_reproduces_historical_cross_shot_limitations() -> None:
    payload = _load()
    provider, preview, runtime = _compile_ref2va(payload, "E01-U06", ["陆念", "沈知意"])

    assert preview["provider_prompt"] == runtime.prompt
    assert "<scenetrans>" not in provider
    assert "same sentence seamlessly across the cut" not in provider

    # The first Canonical fragment deliberately ends with a Chinese comma. V3 appends
    # a Chinese full stop because its terminal punctuation set excludes the comma.
    assert "准备的，。</d>" in provider

    # Sound design exists in E01 Canonical but V3 execution does not consume it.
    assert "overall_soundscape:\nN/A" in provider
    assert "non_diegetic_music:\nN/A" in provider

    last_authored_shot = provider.rindex("[Shot 3]")
    first_dialogue = provider.index("<d>[Chinese] 还有七天就是苏阿姨生日了")
    assert last_authored_shot < first_dialogue


def test_v3_u10_does_not_compile_depicted_subject_role_constraints() -> None:
    payload = _load()
    provider, _, _ = _compile_ref2va(payload, "E01-U10", ["沈知意"])

    # The action prose may mention people inside photos, but V3 has no structured
    # active/depicted/referenced role compiler.
    assert "Embedded-media-only subjects:" not in provider
    assert "do not render them as live people in the physical scene" not in provider


def test_v3_u11_does_not_invent_husband_dialogue_in_controlled_input() -> None:
    payload = _load()
    provider, preview, runtime = _compile_ref2va(payload, "E01-U11", ["沈知意", "周姨"])

    assert preview["provider_prompt"] == runtime.prompt
    assert provider.count("<d>[Chinese]") == 1
    assert "太太，我刚给先生打了电话。先生说今晚有事，让您先休息。" in provider
    assert "我还有事" not in provider
    assert "陆予深 (S" not in provider
    assert "接通轻响" in provider
    assert "立即切黑" in provider


def test_v3_canonical_director_field_is_not_a_compiler_input() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U06")

    # Same source/fallback/assets produce identical output regardless of the future
    # canonical_director payload key: V3 never reads this field.
    kwargs = dict(
        source_prompt=_source_from_unit(payload, unit, ["陆念", "沈知意"]),
        fallback_prompt="LEGACY::U06",
        model_name="minimax_h3_zm_u24",
        duration_seconds=10,
        request_assets=_entries("陆念", "沈知意"),
    )
    without = compile_reference_video_provider_prompt(payload={"prompt_compiler": "auto"}, **kwargs)
    with_canonical = compile_reference_video_provider_prompt(
        payload={
            "prompt_compiler": "auto",
            "canonical_director": {"registries": payload["registries"], "unit": unit},
        },
        **kwargs,
    )
    assert with_canonical == without
