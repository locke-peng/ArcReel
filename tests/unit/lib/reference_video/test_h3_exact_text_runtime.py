from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from lib.reference_video.h3_exact_text_contract import (
    exact_text_plate_specs_from_unit,
)
from lib.reference_video.h3_exact_text_runtime import (
    build_h3_exact_text_runtime_bundle,
    evaluate_h3_exact_text_media,
)
from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_runtime_gate import run_h3_runtime_selection_gate
from lib.video_prompt_compilers.h3_director_compiler import compile_h3_director_prompt


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _audio_digest(path: Path) -> str:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(proc.stdout).hexdigest()


def _plate_spec(asset_path: str, asset_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "ownership": "deterministic_plate",
        "compositing": "full_frame_replace",
        "asset_path": asset_path,
        "asset_sha256": asset_sha256,
        "region": {
            "unit": "normalized",
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
        },
        "typography": {
            "authority": "asset_pixels",
            "layout": "canonical_asset",
        },
        "ssim_threshold": 0.99,
    }


def _canonical(asset_path: str, asset_sha256: str, *, text: str = "沈知意\n天枢联合创始人") -> dict:
    return {
        "unit": {
            "unit_id": "E13U01",
            "duration_sec": 4,
            "shots": [
                {
                    "shot_id": "E13U01-S01",
                    "start_sec": 0,
                    "end_sec": 2,
                    "action": "Deterministic identity plate.",
                    "screen_text": [
                        {
                            "kind": "identity_title",
                            "legibility": "exact",
                            "text": text,
                            "plate_spec": _plate_spec(asset_path, asset_sha256),
                        }
                    ],
                },
                {
                    "shot_id": "E13U01-S02",
                    "start_sec": 2,
                    "end_sec": 4,
                    "action": "Provider-owned entrance visual.",
                    "screen_text": [],
                },
            ],
        },
        "registries": {},
    }


def test_exact_text_plate_contract_digest_binds_text_without_provider_leak() -> None:
    sha = "a" * 64
    canonical = _canonical("fixtures/title.png", sha)
    prompt, _ = compile_h3_director_prompt(
        canonical_director=canonical,
        unit_id="E13U01",
        duration_seconds=4,
    )

    assert "沈知意" not in prompt
    assert "天枢联合创始人" not in prompt
    assert "ArcReel post-production owns this full-frame exact-text plate" in prompt
    assert "contract_sha256=" in prompt
    assert "Do not render readable text" in prompt

    first = exact_text_plate_specs_from_unit(canonical["unit"])[0]
    changed = _canonical("fixtures/title.png", sha, text="另一组精确文字")
    second = exact_text_plate_specs_from_unit(changed["unit"])[0]
    assert first.contract_sha256 != second.contract_sha256


def test_exact_text_plate_contract_is_strict_and_full_frame_only() -> None:
    canonical = _canonical("fixtures/title.png", "a" * 64)
    item = canonical["unit"]["shots"][0]["screen_text"][0]
    item["plate_spec"]["region"]["width"] = 0.5

    with pytest.raises(ValueError, match="full-frame replacement"):
        exact_text_plate_specs_from_unit(canonical["unit"])


@pytest.mark.asyncio
async def test_exact_text_runtime_repairs_only_video_window_and_preserves_audio(
    tmp_path: Path,
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    plate = fixtures / "title.png"
    media = tmp_path / "candidate.mp4"

    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=320x180:r=24",
        "-frames:v",
        "1",
        str(plate),
    )
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x180:r=24:d=4",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=32000:duration=4",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "24",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-shortest",
        str(media),
    )
    original_audio = _audio_digest(media)

    canonical = _canonical("fixtures/title.png", _sha256(plate))
    evaluator, handlers = build_h3_exact_text_runtime_bundle(
        canonical,
        unit_id="E13U01",
        project_path=tmp_path,
    )
    assert evaluator is not None
    assert set(handlers) == {H3RepairAction.DETERMINISTIC_TEXT_PLATE}

    before = await evaluator(media)
    assert len(before) == 1
    assert before[0].failure_class.value == "exact_text_required"
    assert before[0].shot_id == "E13U01-S01"

    result = await run_h3_runtime_selection_gate(
        media,
        evaluator=evaluator,
        repair_handlers=handlers,
    )
    assert result.status == "PASS"
    assert result.provider_recalled is False
    assert result.repair_passes == 1
    assert _audio_digest(media) == original_audio

    resolved_evaluator, _ = build_h3_exact_text_runtime_bundle(
        canonical,
        unit_id="E13U01",
        project_path=tmp_path,
    )
    assert resolved_evaluator is not None
    assert await resolved_evaluator(media) == ()


def test_exact_text_runtime_rejects_plate_sha_drift_before_media_qa(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    plate = fixtures / "title.png"
    plate.write_bytes(b"not-the-pinned-plate")

    canonical = _canonical("fixtures/title.png", "a" * 64)
    with pytest.raises(RuntimeError, match="plate SHA mismatch"):
        build_h3_exact_text_runtime_bundle(
            canonical,
            unit_id="E13U01",
            project_path=tmp_path,
        )
