import shutil
import subprocess
from pathlib import Path

import pytest

from lib.reference_video.h3_media_pipeline import (
    EvidenceChain,
    EvidenceNode,
    H3MediaPipelineError,
    RepairAction,
    RepairRegion,
    RepairRequest,
    TimelineSegment,
)
from lib.reference_video.h3_repair_executors import (
    append_repair_evidence,
    execute_av_retime,
    execute_deterministic_repair,
    execute_pixel_sanitization,
)


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="Phase 3 media executor regression requires ffmpeg/ffprobe",
)


def _make_av_fixture(path: Path, *, seconds: int = 3) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x180:rate=24:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=32000:duration={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(proc.stdout.strip())


def test_phase3_pixel_sanitization_executes_without_provider(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "scrubbed.mp4"
    _make_av_fixture(source, seconds=2)
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
        source_path=source,
        output_path=output,
        regions=(
            RepairRegion(
                shot_id="S1",
                start_sec=0,
                end_sec=2,
                x=20,
                y=20,
                width=120,
                height=70,
            ),
        ),
    )
    execute_pixel_sanitization(request)
    assert output.is_file()
    assert abs(_probe_duration(output) - 2) < 0.15


def test_phase3_av_retime_authors_exact_target_duration(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "retimed.mp4"
    _make_av_fixture(source, seconds=3)
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_AV_RETIME,
        source_path=source,
        output_path=output,
        timeline=(
            TimelineSegment(0, 0.8, 1),
            TimelineSegment(0.8, 1.6, 1),
            TimelineSegment(1.6, 3.0, 1),
        ),
    )
    execute_av_retime(request)
    assert output.is_file()
    assert abs(_probe_duration(output) - 3) < 0.08


def test_phase3_repair_evidence_requires_exact_source_parent(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    _make_av_fixture(source, seconds=1)
    output.write_bytes(source.read_bytes())

    provider = EvidenceNode.create(stage="provider_output", artifact_path=source)
    chain = EvidenceChain(unit_id="TEST", nodes=(provider,))
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
        source_path=source,
        output_path=tmp_path / "unused.mp4",
        regions=(RepairRegion("S1", 0, 1, 0, 0, 10, 10),),
    )
    updated = append_repair_evidence(chain=chain, request=request, output_path=output)
    assert len(updated.nodes) == 2
    assert updated.nodes[-1].parent_sha256 == (provider.artifact_sha256,)

    source.write_bytes(b"mutated")
    with pytest.raises(H3MediaPipelineError, match="source bytes"):
        append_repair_evidence(chain=chain, request=request, output_path=output)


def test_phase3_dispatcher_rejects_semantic_regeneration(tmp_path: Path) -> None:
    request = RepairRequest(
        action=RepairAction.REGENERATE_SHOT,
        source_path=tmp_path / "source.mp4",
        output_path=tmp_path / "output.mp4",
    )
    with pytest.raises(H3MediaPipelineError, match="no deterministic executor"):
        execute_deterministic_repair(request)


def test_phase3_module_has_no_provider_or_secret_dependency() -> None:
    source = Path("lib/reference_video/h3_repair_executors.py").read_text(encoding="utf-8")
    assert "MediaGenerator" not in source
    assert "DeclarativeVideoBackend" not in source
    assert "MINIMAX" not in source
    assert "API_KEY" not in source
