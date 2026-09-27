from __future__ import annotations

from pathlib import Path

import pytest

from lib.reference_video.cut_detector import CutDetection
from lib.reference_video import h3_timeline_runtime
from lib.reference_video.h3_production_policy import H3FailureClass, H3RepairAction
from lib.reference_video.h3_timeline_runtime import (
    canonical_timeline_from_director,
    evaluate_h3_timeline_media,
)


def _canonical() -> dict:
    return {
        "units": [
            {
                "unit_id": "E15U03",
                "duration_sec": 15,
                "shots": [
                    {"shot_id": "S1", "start_sec": 0, "end_sec": 5},
                    {"shot_id": "S2", "start_sec": 5, "end_sec": 10},
                    {"shot_id": "S3", "start_sec": 10, "end_sec": 15},
                ],
            }
        ]
    }


def test_canonical_timeline_uses_shot_starts_as_target_cuts() -> None:
    timeline = canonical_timeline_from_director(_canonical(), unit_id="E15U03")

    assert timeline.unit_id == "E15U03"
    assert timeline.duration_seconds == 15
    assert timeline.target_cut_times == (5.0, 10.0)


def test_timeline_evaluator_emits_existing_timeline_failure_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"fake")
    timeline = canonical_timeline_from_director(_canonical(), unit_id="E15U03")

    monkeypatch.setattr(h3_timeline_runtime, "probe_video_fps", lambda _path: 24.0)
    monkeypatch.setattr(
        h3_timeline_runtime,
        "detect_expected_cuts",
        lambda *_args, **_kwargs: (
            CutDetection(118, 118 / 24, 120, 5.0, -2, -2 / 24, 0.4, "scene"),
            CutDetection(222, 222 / 24, 240, 10.0, -18, -18 / 24, 0.3, "scene"),
        ),
    )

    findings = evaluate_h3_timeline_media(media, timeline=timeline)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.failure_class is H3FailureClass.TIMELINE_ONLY_FAILURE
    assert finding.evidence_frames == (118, 222)
    assert ("cut_timing",) == finding.tags


def test_timeline_evaluator_passes_exact_cuts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"fake")
    timeline = canonical_timeline_from_director(_canonical(), unit_id="E15U03")

    monkeypatch.setattr(h3_timeline_runtime, "probe_video_fps", lambda _path: 24.0)
    monkeypatch.setattr(
        h3_timeline_runtime,
        "detect_expected_cuts",
        lambda *_args, **_kwargs: (
            CutDetection(120, 5.0, 120, 5.0, 0, 0.0, 0.4, "scene"),
            CutDetection(240, 10.0, 240, 10.0, 0, 0.0, 0.3, "scene"),
        ),
    )

    assert evaluate_h3_timeline_media(media, timeline=timeline) == ()


def test_timeline_evaluator_fails_closed_when_cuts_cannot_be_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"fake")
    timeline = canonical_timeline_from_director(_canonical(), unit_id="E15U03")

    monkeypatch.setattr(h3_timeline_runtime, "probe_video_fps", lambda _path: 24.0)

    def fail(*_args, **_kwargs):
        raise RuntimeError("no confident hard cut")

    monkeypatch.setattr(h3_timeline_runtime, "detect_expected_cuts", fail)

    findings = evaluate_h3_timeline_media(media, timeline=timeline)

    assert len(findings) == 1
    assert findings[0].failure_class is None
    assert findings[0].tags == ("cut_detection_unresolved",)


@pytest.mark.asyncio
async def test_timeline_runtime_bundle_uses_only_existing_av_retime_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"fake")
    evaluator, handlers = h3_timeline_runtime.build_h3_timeline_runtime_bundle(
        _canonical(),
        unit_id="E15U03",
    )

    monkeypatch.setattr(h3_timeline_runtime, "probe_video_fps", lambda _path: 24.0)
    monkeypatch.setattr(
        h3_timeline_runtime,
        "detect_expected_cuts",
        lambda *_args, **_kwargs: (
            CutDetection(118, 118 / 24, 120, 5.0, -2, -2 / 24, 0.4, "scene"),
            CutDetection(222, 222 / 24, 240, 10.0, -18, -18 / 24, 0.3, "scene"),
        ),
    )

    findings = await evaluator(media)

    assert findings[0].failure_class is H3FailureClass.TIMELINE_ONLY_FAILURE
    assert set(handlers) == {H3RepairAction.DETERMINISTIC_AV_RETIME}


def test_runtime_retime_trims_overlong_final_beat_instead_of_compressing_timing_debt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"source")
    timeline = canonical_timeline_from_director(_canonical(), unit_id="E15U03")

    monkeypatch.setattr(h3_timeline_runtime, "probe_video_fps", lambda _path: 24.0)
    monkeypatch.setattr(
        h3_timeline_runtime,
        "detect_expected_cuts",
        lambda *_args, **_kwargs: (
            CutDetection(118, 118 / 24, 120, 5.0, -2, -2 / 24, 0.4, "scene"),
            CutDetection(222, 222 / 24, 240, 10.0, -18, -18 / 24, 0.3, "scene"),
        ),
    )
    monkeypatch.setattr(
        h3_timeline_runtime,
        "_video_stream_facts",
        lambda _path: (360, 32000, 2),
    )

    captured: list[str] = []

    def fake_run(command, check=True):
        del check
        captured.extend(command)
        Path(command[-1]).write_bytes(b"retimed")

    monkeypatch.setattr(h3_timeline_runtime.subprocess, "run", fake_run)

    h3_timeline_runtime.retime_h3_media_to_canonical_timeline(
        media,
        timeline=timeline,
    )

    filter_complex = captured[captured.index("-filter_complex") + 1]
    assert "trim=start=9.250000000:end=14.250000000" in filter_complex
    assert "setpts=(PTS-STARTPTS)*1.000000000000" in filter_complex
    assert "atrim=start=9.250000000:end=14.250000000" in filter_complex
    assert "atempo=1.000000000000" in filter_complex
