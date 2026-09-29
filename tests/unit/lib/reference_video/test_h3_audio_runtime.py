from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from lib.reference_video.h3_audio_contract import parse_canonical_audio_track_spec
from lib.reference_video.h3_audio_runtime import build_h3_canonical_audio_runtime_bundle
from lib.reference_video.h3_production_policy import H3RepairAction
from lib.reference_video.h3_runtime_gate import run_h3_runtime_selection_gate
from lib.video_prompt_compilers.h3_director_compiler import compile_h3_director_prompt


def _run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _video_digest(path: Path) -> str:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-an",
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(proc.stdout).hexdigest()


def _canonical(asset_path: str, asset_sha256: str) -> dict:
    return {
        "unit": {
            "unit_id": "E13U01",
            "duration_sec": 4,
            "audio_track_spec": {
                "schema_version": 1,
                "ownership": "deterministic_audio",
                "scope": "full_unit",
                "asset_path": asset_path,
                "asset_sha256": asset_sha256,
                "codec": "aac",
                "sample_rate_hz": 32000,
                "channels": 2,
                "bitrate_bps": 128000,
            },
            "shots": [
                {
                    "shot_id": "S1",
                    "start_sec": 0,
                    "end_sec": 4,
                    "action": "Provider-owned visual, ArcReel-owned soundtrack.",
                }
            ],
        },
        "registries": {},
    }


def test_audio_contract_is_bound_into_prompt_without_soundtrack_transcript() -> None:
    canonical = _canonical("fixtures/canonical.wav", "a" * 64)
    spec = parse_canonical_audio_track_spec(canonical["unit"])
    assert spec is not None

    prompt, _ = compile_h3_director_prompt(
        canonical_director=canonical,
        unit_id="E13U01",
        duration_seconds=4,
    )

    assert spec.contract_sha256 in prompt
    assert "Provider audio is non-authoritative" in prompt
    assert "ArcReel replaces the complete audio layer" in prompt
    assert "spoken soundtrack content" in prompt


def test_audio_contract_rejects_unsafe_or_unsupported_specs() -> None:
    canonical = _canonical("../escape.wav", "a" * 64)
    with pytest.raises(ValueError, match="project-relative"):
        parse_canonical_audio_track_spec(canonical["unit"])

    canonical = _canonical("fixtures/canonical.wav", "a" * 64)
    canonical["unit"]["audio_track_spec"]["scope"] = "shot"
    with pytest.raises(ValueError, match="full_unit"):
        parse_canonical_audio_track_spec(canonical["unit"])


@pytest.mark.asyncio
async def test_audio_runtime_remuxes_only_audio_and_preserves_video(
    tmp_path: Path,
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    canonical_audio = fixtures / "canonical.wav"
    candidate = tmp_path / "candidate.mp4"

    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=32000:duration=4",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(canonical_audio),
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
        "-ar",
        "32000",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-shortest",
        str(candidate),
    )

    canonical = _canonical("fixtures/canonical.wav", _sha256(canonical_audio))
    evaluator, handlers = build_h3_canonical_audio_runtime_bundle(
        canonical,
        unit_id="E13U01",
        project_path=tmp_path,
    )
    assert evaluator is not None
    assert set(handlers) == {H3RepairAction.AUDIO_REPAIR_REMUX}

    findings = await evaluator(candidate)
    assert len(findings) == 1
    assert findings[0].failure_class.value == "audio_only_failure"
    before_video = _video_digest(candidate)

    result = await run_h3_runtime_selection_gate(
        candidate,
        evaluator=evaluator,
        repair_handlers=handlers,
    )
    assert result.status == "PASS"
    assert result.provider_recalled is False
    assert result.repair_passes == 1
    assert _video_digest(candidate) == before_video
    assert await evaluator(candidate) == ()


def test_audio_runtime_rejects_asset_sha_drift_before_provider(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    audio = fixtures / "canonical.wav"
    audio.write_bytes(b"drift")

    canonical = _canonical("fixtures/canonical.wav", "a" * 64)
    with pytest.raises(RuntimeError, match="canonical audio SHA mismatch"):
        build_h3_canonical_audio_runtime_bundle(
            canonical,
            unit_id="E13U01",
            project_path=tmp_path,
        )
