"""Phase 4 end-to-end replay over existing paid supplier evidence.

No provider API is imported or called. The script runs the Phase 4 chain:
Media QA -> Structured Finding -> Classifier -> Phase 3 Planner -> Executor
-> Re-QA -> hash-chained evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from lib.reference_video.cut_detector import CutDetection, detect_expected_cuts
from lib.reference_video.evidence_schema import H3EvidenceRecord
from lib.reference_video.h3_failure_classifier import classify_h3_media_finding
from lib.reference_video.h3_production_policy import H3RepairAction, plan_h3_media_repair
from lib.reference_video.h3_repair_executor import (
    execute_h3_media_repair,
    sha256_file,
)
from lib.reference_video.media_qa_schema import (
    MediaQAFinding,
    MediaQARepairability,
    MediaQASeverity,
)

FPS = 24
TARGET_CUT_FRAMES = (120, 240)
EXPECTED_PHASE3_REPLAY_SHA256 = {
    "E11U02": "4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18",
    "E15U03": "208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de",
}
E11_RUN_ID = 36148270693
E11_ARTIFACT_ID = 10870732082
E15_RUN_ID = 36009732060
E15_ARTIFACT_ID = 10812256991


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _probe_media(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in payload["streams"] if stream["codec_type"] == "audio")
    probe = {
        "duration": float(payload["format"]["duration"]),
        "size": int(payload["format"]["size"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "video_codec": video["codec_name"],
        "fps": video["avg_frame_rate"],
        "audio_codec": audio["codec_name"],
        "sample_rate": int(audio["sample_rate"]),
        "channels": int(audio["channels"]),
    }
    if abs(probe["duration"] - 15.0) > 0.05:
        raise RuntimeError(f"unexpected duration for {path}: {probe['duration']}")
    if (probe["width"], probe["height"]) != (864, 480):
        raise RuntimeError(f"unexpected resolution for {path}: {probe}")
    if probe["video_codec"] != "h264" or probe["audio_codec"] != "aac":
        raise RuntimeError(f"unexpected codecs for {path}: {probe}")
    return probe


def _count_video_frames(path: Path) -> int:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return int(proc.stdout.strip())


def _extract_review_frames(video: Path, output_dir: Path, frames: tuple[int, ...]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        output = output_dir / f"frame_{frame:04d}.png"
        _run(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"select=eq(n\\,{frame})",
            "-frames:v",
            "1",
            str(output),
        )
        if not output.is_file():
            raise RuntimeError(f"failed to extract review frame {frame} from {video}")


def _retime_from_detected_cuts(
    source: Path,
    output: Path,
    cuts: tuple[CutDetection, ...],
) -> None:
    if len(cuts) != 2:
        raise RuntimeError("E15U03 requires exactly two detected cuts")

    source_frames = _count_video_frames(source)
    cut1 = cuts[0].actual_cut_frame
    cut2 = cuts[1].actual_cut_frame
    target_frames = FPS * 5
    source_end_frame = cut2 + target_frames
    if not (0 < cut1 < cut2 < source_end_frame <= source_frames):
        raise RuntimeError(
            "invalid detected cut/source ordering: "
            f"{cut1}, {cut2}, source_end_frame={source_end_frame}, source_frames={source_frames}"
        )

    source_segments = (cut1, cut2 - cut1, source_end_frame - cut2)
    pts_factors = tuple(target_frames / frames for frames in source_segments)
    atempo_factors = tuple(frames / target_frames for frames in source_segments)
    cut1_s = cut1 / FPS
    cut2_s = cut2 / FPS
    end_s = source_end_frame / FPS

    filter_complex = (
        f"[0:v]trim=start=0:end={cut1_s:.9f},"
        f"setpts=(PTS-STARTPTS)*{pts_factors[0]:.12f},fps={FPS}[v0];"
        f"[0:a]atrim=start=0:end={cut1_s:.9f},asetpts=PTS-STARTPTS,"
        f"atempo={atempo_factors[0]:.12f}[a0];"
        f"[0:v]trim=start={cut1_s:.9f}:end={cut2_s:.9f},"
        f"setpts=(PTS-STARTPTS)*{pts_factors[1]:.12f},fps={FPS}[v1];"
        f"[0:a]atrim=start={cut1_s:.9f}:end={cut2_s:.9f},asetpts=PTS-STARTPTS,"
        f"atempo={atempo_factors[1]:.12f}[a1];"
        f"[0:v]trim=start={cut2_s:.9f}:end={end_s:.9f},"
        f"setpts=(PTS-STARTPTS)*{pts_factors[2]:.12f},fps={FPS}[v2];"
        f"[0:a]atrim=start={cut2_s:.9f}:end={end_s:.9f},asetpts=PTS-STARTPTS,"
        f"atempo={atempo_factors[2]:.12f}[a2];"
        "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "32000",
        "-ac",
        "2",
        "-t",
        "15",
        "-movflags",
        "+faststart",
        str(output),
    )


def _write_chain(root: Path, records: tuple[H3EvidenceRecord, ...]) -> None:
    for record in records:
        record.verify()
    (root / "evidence_hash_chain.json").write_text(
        json.dumps([record.to_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_e11(upstream: Path, output_root: Path, tested_sha: str) -> dict[str, Any]:
    source_paths = (
        upstream / "E11U02_SHOT1_provider_raw.mp4",
        upstream / "E11U02_SHOT2_provider_raw.mp4",
        upstream / "E11U02_SHOT3_provider_raw.mp4",
    )
    source_report_path = upstream / "E11U02_v2_live_report.json"
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))

    finding = MediaQAFinding(
        unit_id="E11U02",
        canonical_violation="non-canonical readable or pseudo-readable text on local screen, badge, and side-media surfaces",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=True,
        audio_is_accepted=True,
        repairability=MediaQARepairability.DETERMINISTIC,
        affected_fraction=0.05,
        evidence_frames=(60, 180, 300),
        tags=("noncanonical_text", "surface_pollution"),
    )
    failure = classify_h3_media_finding(finding)
    decision = plan_h3_media_repair(failure)
    if decision.action is not H3RepairAction.DETERMINISTIC_SURFACE_REPAIR:
        raise RuntimeError(f"unexpected E11U02 repair decision: {decision}")

    root = output_root / "E11U02"
    final_video = root / "project" / "reference_videos" / "E11U02.mp4"

    def runner() -> None:
        _run(
            sys.executable,
            "scripts/experiments/run_e11u02_v3_deterministic_repair.py",
            "--upstream-dir",
            str(upstream),
            "--output-dir",
            str(root),
        )

    execution = execute_h3_media_repair(
        decision,
        source_media=source_paths,
        output_media=final_video,
        deterministic_runner=runner,
    )
    if execution.provider_recalled:
        raise RuntimeError("E11U02 unexpectedly recalled provider")

    probe = _probe_media(final_video)
    if execution.output_media_sha256 != EXPECTED_PHASE3_REPLAY_SHA256["E11U02"]:
        raise RuntimeError(
            "E11U02 final MP4 does not match Phase 3 visually accepted replay bytes: "
            f"{execution.output_media_sha256}"
        )

    _extract_review_frames(
        final_video,
        root / "review_frames",
        (60, 119, 120, 180, 239, 240, 300),
    )

    prompt_hashes = tuple(
        plate["provider_prompt_sha256"] for plate in source_report.get("plates", [])
    )
    reference_hashes = tuple(
        value
        for value in (source_report.get("scene_bridge_sha256"),)
        if isinstance(value, str)
    )
    source_hashes = execution.source_media_sha256

    pre = H3EvidenceRecord(
        unit_id="E11U02",
        stage="media_qa_structured_finding",
        tested_sha=tested_sha,
        repair_action=decision.action.value,
        provider_recalled=False,
        qa_verdict="FAIL_REPAIRABLE",
        source_media_sha256=source_hashes,
        prompt_sha256=prompt_hashes[0] if prompt_hashes else None,
        reference_sha256=reference_hashes,
        provider_run_id=E11_RUN_ID,
        provider_artifact_id=E11_ARTIFACT_ID,
        evidence_frames=finding.evidence_frames,
    ).sealed()

    post = H3EvidenceRecord(
        unit_id="E11U02",
        stage="re_qa",
        tested_sha=tested_sha,
        repair_action=decision.action.value,
        provider_recalled=False,
        qa_verdict="PASS_BYTE_IDENTICAL_TO_PHASE3_ACCEPTED_REPLAY",
        source_media_sha256=source_hashes,
        prompt_sha256=prompt_hashes[0] if prompt_hashes else None,
        reference_sha256=reference_hashes,
        provider_run_id=E11_RUN_ID,
        provider_artifact_id=E11_ARTIFACT_ID,
        post_media_sha256=execution.output_media_sha256,
        media_probe=tuple(sorted(probe.items())),
        evidence_frames=(60, 119, 120, 180, 239, 240, 300),
        previous_record_sha256=pre.record_sha256,
    ).sealed()
    _write_chain(root, (pre, post))

    return {
        "unit_id": "E11U02",
        "finding": finding.to_dict(),
        "failure_class": failure.failure_class.value,
        "repair_action": decision.action.value,
        "provider_recalled": execution.provider_recalled,
        "source_supplier_run_id": E11_RUN_ID,
        "source_supplier_artifact_id": E11_ARTIFACT_ID,
        "final_media_sha256": execution.output_media_sha256,
        "phase3_accepted_replay_sha256": EXPECTED_PHASE3_REPLAY_SHA256["E11U02"],
        "byte_identity_with_phase3_accepted_replay": True,
        "media_probe": probe,
        "evidence_head_sha256": post.record_sha256,
        "qa_verdict": "PASS_BYTE_IDENTICAL_TO_PHASE3_ACCEPTED_REPLAY",
    }


def _run_e15(upstream: Path, output_root: Path, tested_sha: str) -> dict[str, Any]:
    source_video = upstream / "E15U03.mp4"
    summary_path = upstream / "live_test_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    source_cuts = detect_expected_cuts(
        source_video,
        target_cut_frames=TARGET_CUT_FRAMES,
        search_radius_frames=24,
        min_scene_score=0.15,
    )
    actual_frames = tuple(cut.actual_cut_frame for cut in source_cuts)
    if actual_frames != (118, 222):
        raise RuntimeError(f"E15U03 detected cuts changed: {actual_frames}")

    finding = MediaQAFinding(
        unit_id="E15U03",
        canonical_violation="actual hard cuts do not land on canonical 5s and 10s boundaries",
        severity=MediaQASeverity.BLOCKING,
        provider_result_usable=True,
        audio_is_accepted=True,
        repairability=MediaQARepairability.DETERMINISTIC,
        affected_fraction=1.0,
        evidence_frames=actual_frames,
        tags=("cut_timing",),
    )
    failure = classify_h3_media_finding(finding)
    decision = plan_h3_media_repair(failure)
    if decision.action is not H3RepairAction.DETERMINISTIC_AV_RETIME:
        raise RuntimeError(f"unexpected E15U03 repair decision: {decision}")

    root = output_root / "E15U03"
    final_video = root / "project" / "reference_videos" / "E15U03.mp4"

    def runner() -> None:
        _retime_from_detected_cuts(source_video, final_video, source_cuts)

    execution = execute_h3_media_repair(
        decision,
        source_media=(source_video,),
        output_media=final_video,
        deterministic_runner=runner,
    )
    if execution.provider_recalled:
        raise RuntimeError("E15U03 unexpectedly recalled provider")

    probe = _probe_media(final_video)
    final_cuts = detect_expected_cuts(
        final_video,
        target_cut_frames=TARGET_CUT_FRAMES,
        search_radius_frames=2,
        min_scene_score=0.15,
    )
    if tuple(cut.actual_cut_frame for cut in final_cuts) != TARGET_CUT_FRAMES:
        raise RuntimeError(
            "E15U03 re-QA did not land on exact target cuts: "
            f"{tuple(c.actual_cut_frame for c in final_cuts)}"
        )
    if execution.output_media_sha256 != EXPECTED_PHASE3_REPLAY_SHA256["E15U03"]:
        raise RuntimeError(
            "E15U03 final MP4 does not match Phase 3 visually accepted replay bytes: "
            f"{execution.output_media_sha256}"
        )

    _extract_review_frames(
        final_video,
        root / "review_frames",
        (60, 119, 120, 180, 239, 240, 300),
    )

    prompt_sha = summary.get("prompt_sha256")
    reference_sha = tuple(summary.get("reference_sha256") or ())
    source_sha = sha256_file(source_video)

    pre = H3EvidenceRecord(
        unit_id="E15U03",
        stage="media_qa_structured_finding",
        tested_sha=tested_sha,
        repair_action=decision.action.value,
        provider_recalled=False,
        qa_verdict="FAIL_REPAIRABLE",
        source_media_sha256=(source_sha,),
        prompt_sha256=prompt_sha,
        reference_sha256=reference_sha,
        provider_task_id=summary.get("task_id"),
        provider_run_id=E15_RUN_ID,
        provider_artifact_id=E15_ARTIFACT_ID,
        pre_media_sha256=source_sha,
        actual_cuts=(("source", [cut.to_dict() for cut in source_cuts]),),
        evidence_frames=actual_frames,
    ).sealed()

    post = H3EvidenceRecord(
        unit_id="E15U03",
        stage="re_qa",
        tested_sha=tested_sha,
        repair_action=decision.action.value,
        provider_recalled=False,
        qa_verdict="PASS_BYTE_IDENTICAL_TO_PHASE3_ACCEPTED_REPLAY",
        source_media_sha256=(source_sha,),
        prompt_sha256=prompt_sha,
        reference_sha256=reference_sha,
        provider_task_id=summary.get("task_id"),
        provider_run_id=E15_RUN_ID,
        provider_artifact_id=E15_ARTIFACT_ID,
        pre_media_sha256=source_sha,
        post_media_sha256=execution.output_media_sha256,
        actual_cuts=(
            ("source", [cut.to_dict() for cut in source_cuts]),
            ("final", [cut.to_dict() for cut in final_cuts]),
        ),
        media_probe=tuple(sorted(probe.items())),
        evidence_frames=(119, 120, 239, 240),
        previous_record_sha256=pre.record_sha256,
    ).sealed()
    _write_chain(root, (pre, post))

    return {
        "unit_id": "E15U03",
        "finding": finding.to_dict(),
        "failure_class": failure.failure_class.value,
        "repair_action": decision.action.value,
        "provider_recalled": execution.provider_recalled,
        "source_supplier_run_id": E15_RUN_ID,
        "source_supplier_artifact_id": E15_ARTIFACT_ID,
        "source_detected_cuts": [cut.to_dict() for cut in source_cuts],
        "final_detected_cuts": [cut.to_dict() for cut in final_cuts],
        "final_media_sha256": execution.output_media_sha256,
        "phase3_accepted_replay_sha256": EXPECTED_PHASE3_REPLAY_SHA256["E15U03"],
        "byte_identity_with_phase3_accepted_replay": True,
        "media_probe": probe,
        "evidence_head_sha256": post.record_sha256,
        "qa_verdict": "PASS_BYTE_IDENTICAL_TO_PHASE3_ACCEPTED_REPLAY",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e11-upstream-dir", type=Path, required=True)
    parser.add_argument("--e15-upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    tested_sha = os.environ.get("GITHUB_SHA", "").strip()
    if not tested_sha:
        raise RuntimeError("GITHUB_SHA is required for acceptance evidence")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        _run_e11(args.e11_upstream_dir, args.output_dir, tested_sha),
        _run_e15(args.e15_upstream_dir, args.output_dir, tested_sha),
    ]
    if any(result["provider_recalled"] for result in results):
        raise RuntimeError("provider_recalled must remain false for Phase 4 first acceptance")

    summary = {
        "status": "FINAL_PASS",
        "tested_sha": tested_sha,
        "provider_recalled": False,
        "units": results,
    }
    (args.output_dir / "phase4_auto_repair_e2e_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
