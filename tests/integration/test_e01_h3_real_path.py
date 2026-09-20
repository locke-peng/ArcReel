from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from lib.reference_video.h3_prompt_execution import (
    assert_provider_prompt_matches_preview,
    compile_reference_video_provider_prompt,
)
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from lib.video_backends.base import VideoGenerationRequest

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


def _bundle(payload: dict, unit: dict) -> dict:
    return {"registries": payload["registries"], "unit": unit}


def _compile(payload: dict, unit: dict, request_assets=()):
    compilation = compile_reference_video_provider_prompt(
        source_prompt=f"E01 canonical {unit['unit_id']}",
        fallback_prompt="legacy rendered prompt",
        model_name="MiniMax-H3",
        duration_seconds=int(unit["duration_sec"]),
        request_assets=list(request_assets),
        payload={
            "prompt_compiler": "auto",
            "canonical_director": _bundle(payload, unit),
        },
        max_prompt_chars=7000,
        unit_id=unit["unit_id"],
    )
    preview = build_reference_prompt_preview_payload(compilation)
    request = VideoGenerationRequest(
        prompt=compilation.provider_prompt,
        output_path=Path("/tmp") / f"{unit['unit_id']}.mp4",
        aspect_ratio=unit.get("aspect_ratio", "16:9"),
        duration_seconds=int(unit["duration_sec"]),
        reference_images=[] if not request_assets else [Path(f"/tmp/ref-{i}.png") for i, _ in enumerate(request_assets, 1)],
    )
    return compilation, preview, request


def test_e01_fixture_integrity() -> None:
    payload = _load()
    assert payload["episode"]["episode_id"] == "E01"
    assert payload["episode"]["duration_sec"] == 105
    assert payload["episode"]["unit_count"] == 11
    assert payload["episode"]["shot_count"] == 33
    assert len(payload["units"]) == 11
    assert sum(int(u["duration_sec"]) for u in payload["units"]) == 105
    assert sum(len(u["shots"]) for u in payload["units"]) == 33
    cursor = 0.0
    for unit in payload["units"]:
        assert float(unit["start_sec"]) == pytest.approx(cursor)
        assert float(unit["end_sec"]) - float(unit["start_sec"]) == pytest.approx(float(unit["duration_sec"]))
        assert 4 <= int(unit["duration_sec"]) <= 15
        shot_cursor = 0.0
        for shot in unit["shots"]:
            assert float(shot["start_sec"]) == pytest.approx(shot_cursor)
            assert float(shot["end_sec"]) - float(shot["start_sec"]) == pytest.approx(float(shot["duration_sec"]))
            shot_cursor = float(shot["end_sec"])
        assert shot_cursor == pytest.approx(float(unit["duration_sec"]))
        cursor = float(unit["end_sec"])
    assert cursor == pytest.approx(105.0)


@pytest.mark.parametrize("unit_index", range(11))
def test_e01_all_units_preview_equals_final_video_generation_request(unit_index: int) -> None:
    payload = _load()
    unit = payload["units"][unit_index]
    compilation, preview, request = _compile(payload, unit)

    assert compilation.compiler_applied is True
    assert compilation.generation_mode == "t2va"
    assert preview["generation_mode"] == "t2va"
    assert preview["provider_prompt"] == compilation.provider_prompt
    assert request.prompt == preview["provider_prompt"]
    assert preview["prompt_chars"] == len(request.prompt)
    assert "<Picture " not in request.prompt

    # V6.1 hard invariant immediately before provider submission.
    assert_provider_prompt_matches_preview(
        provider_prompt=request.prompt,
        expected_sha256=preview["provider_prompt_sha256"],
    )

    # A one-character drift must be rejected before any provider call.
    with pytest.raises(Exception, match="changed after preview"):
        assert_provider_prompt_matches_preview(
            provider_prompt=request.prompt + " ",
            expected_sha256=preview["provider_prompt_sha256"],
        )


def test_e01_u01_semantics() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U01")
    _, preview, request = _compile(payload, unit)
    prompt = request.prompt
    assert "Referenced-only entities: 陆予深." in prompt
    assert "do not visually spawn them" in prompt
    assert 'render exactly "陆予深"' in prompt
    assert "deliberately unreadable" in prompt
    assert "机场广播、人流、行李箱轮子、手机提示音。" in prompt
    assert preview["provider_prompt"] == prompt


def test_e01_u04_dialogue_stays_in_authored_shots_and_speaker_ids_are_stable() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U04")
    _, _, request = _compile(payload, unit)
    prompt = request.prompt
    shot2 = prompt.index("[Shot 2]")
    szy = prompt.index("沈知意 (S1) says")
    ln = prompt.index("陆念 (S2) says")
    shot3 = prompt.index("[Shot 3]")
    final_ln = prompt.index("妈妈你先别打断我，我刚摆好的又乱了。")
    assert shot2 < szy < ln < shot3 < final_ln


def test_e01_u06_cross_shot_dialogue_and_soundscape() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U06")
    _, _, request = _compile(payload, unit)
    prompt = request.prompt
    assert "<scenetrans>" in prompt
    assert "陆念 (S1) says" in prompt
    assert "陆念 (S1) continues the same utterance" in prompt
    assert "same sentence seamlessly across the cut" in prompt
    assert "，。</d>" not in prompt
    assert "贝壳与丝线轻响、陆念连续说话、沈知意浅呼吸；第三镜环境声短暂降低。" in prompt
    assert "极弱持续低音弦乐进入。" in prompt


def test_e01_u10_depicted_people_never_spawn_live() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U10")
    _, _, request = _compile(payload, unit)
    prompt = request.prompt
    assert "Embedded-media-only subjects: 陆予深, 陆念, 苏晚." in prompt
    assert "do not render them as live people in the physical scene" in prompt


def test_e01_u11_stops_at_connection_click_and_does_not_leak_e02_dialogue() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U11")
    _, _, request = _compile(payload, unit)
    prompt = request.prompt
    assert "Referenced-only entities: 陆予深." in prompt
    assert "拨号" in prompt
    assert "接通轻响" in prompt
    assert "切黑" in prompt
    assert "我还有事" not in prompt
    assert prompt.count("<d>[Chinese]") == 1
    assert "陆予深 (S" not in prompt


def test_e01_u04_ref2va_switch_uses_only_actual_provider_references() -> None:
    payload = _load()
    unit = next(u for u in payload["units"] if u["unit_id"] == "E01-U04")
    refs = [
        Entry(Ref("character", "沈知意")),
        Entry(Ref("character", "陆念")),
    ]
    compilation = compile_reference_video_provider_prompt(
        source_prompt="E01 U04",
        fallback_prompt="legacy rendered prompt",
        model_name="MiniMax-H3",
        duration_seconds=int(unit["duration_sec"]),
        request_assets=refs,
        payload={
            "prompt_compiler": "auto",
            "canonical_director": _bundle(payload, unit),
            "reference_image_labels": ["沈知意", "陆念"],
        },
        max_prompt_chars=7000,
        unit_id=unit["unit_id"],
    )
    preview = build_reference_prompt_preview_payload(compilation)
    request = VideoGenerationRequest(
        prompt=compilation.provider_prompt,
        output_path=Path("/tmp/E01-U04-ref.mp4"),
        aspect_ratio="16:9",
        duration_seconds=int(unit["duration_sec"]),
        reference_images=[Path("/tmp/szy.png"), Path("/tmp/ln.png")],
    )
    assert compilation.generation_mode == "ref2va"
    assert preview["generation_mode"] == "ref2va"
    assert "<Picture 1>" in request.prompt
    assert "<Picture 2>" in request.prompt
    assert "<Picture 3>" not in request.prompt
    assert "<Subject 1> (S1) says" in request.prompt
    assert "<Subject 2> (S2) says" in request.prompt
    assert_provider_prompt_matches_preview(
        provider_prompt=request.prompt,
        expected_sha256=preview["provider_prompt_sha256"],
    )
