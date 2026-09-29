"""Phase 4 E13U01 canonical-audio runtime replay over existing accepted evidence.

No provider call is made. The replay keeps the formally accepted E13U01 picture,
injects an intentionally wrong AAC soundtrack, then exercises the production
AUDIO_ONLY_FAILURE -> AUDIO_REPAIR_REMUX runtime path.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from lib.reference_video.cut_detector import detect_expected_cuts
from lib.reference_video.evidence_schema import H3EvidenceRecord
from lib.reference_video.h3_audio_runtime import build_h3_canonical_audio_runtime_bundle
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_runtime_gate import run_h3_runtime_selection_gate

UNIT_ID = "E13U01"
SUPPLIER_RUN_ID = 36098803663
SUPPLIER_ARTIFACT_ID = 10848054150
AUDIO_SHA256 = "cbda309d698046b6ab185f5d36fdf23ee1a112f6f1f9d39a37368b6f985a7b33"
ACCEPTED_FINAL_SHA256 = "8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12"
DURATION_SECONDS = 10
FPS = 24
_SSIM_RE = re.compile(r"All:(?P<ssim>\d+(?:\.\d+)?)")


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _require_sha(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA mismatch: {actual} != {expected}")


def _decoded_digest(path: Path, selector: str) -> str:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            selector,
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(proc.stdout).hexdigest()


def _video_ssim(left: Path, right: Path) -> float:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(left),
            "-i",
            str(right),
            "-lavfi",
            "[0:v][1:v]ssim",
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    matches = _SSIM_RE.findall(proc.stderr)
    if not matches:
        raise RuntimeError("ffmpeg did not emit SSIM")
    return float(matches[-1])


def _probe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    video = next(s for s in payload["streams"] if s["codec_type"] == "video")
    audio = next(s for s in payload["streams"] if s["codec_type"] == "audio")
    return {
        "duration": float(payload["format"]["duration"]),
        "size": int(payload["format"]["size"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "video_codec": video["codec_name"],
        "fps": video["r_frame_rate"],
        "audio_codec": audio["codec_name"],
        "sample_rate": int(audio["sample_rate"]),
        "channels": int(audio["channels"]),
    }


def _build_wrong_audio_candidate(accepted: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(accepted),
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=880:sample_rate=32000:duration={DURATION_SECONDS}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-ar",
        "32000",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-t",
        str(DURATION_SECONDS),
        "-movflags",
        "+faststart",
        str(output),
    )


def _canonical() -> dict[str, Any]:
    return {
        "unit": {
            "unit_id": UNIT_ID,
            "duration_sec": DURATION_SECONDS,
            "audio_track_spec": {
                "schema_version": 1,
                "ownership": "deterministic_audio",
                "scope": "full_unit",
                "asset_path": "fixtures/E13U01_host_applause_audio.wav",
                "asset_sha256": AUDIO_SHA256,
                "codec": "aac",
                "sample_rate_hz": 32000,
                "channels": 2,
                "bitrate_bps": 128000,
            },
            "shots": [
                {"shot_id": "E13U01-S01", "start_sec": 0, "end_sec": 5},
                {"shot_id": "E13U01-S02", "start_sec": 5, "end_sec": 10},
            ],
        },
        "registries": {},
    }


def _write_chain(root: Path, records: tuple[H3EvidenceRecord, ...]) -> None:
    for record in records:
        record.verify()
    (root / "evidence_hash_chain.json").write_text(
        json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    tested_sha = os.environ.get("GITHUB_SHA", "").strip()
    if not tested_sha:
        raise RuntimeError("GITHUB_SHA is required")

    project = args.upstream_dir / "project"
    audio = project / "fixtures" / "E13U01_host_applause_audio.wav"
    accepted = project / "reference_videos" / "E13U01.mp4"
    _require_sha(audio, AUDIO_SHA256, "canonical audio")
    _require_sha(accepted, ACCEPTED_FINAL_SHA256, "accepted final")

    root = args.output_dir / UNIT_ID
    candidate = root / "project" / "reference_videos" / "E13U01.mp4"
    _build_wrong_audio_candidate(accepted, candidate)
    candidate_sha = sha256_file(candidate)

    accepted_video_digest = _decoded_digest(accepted, "0:v:0")
    candidate_video_digest = _decoded_digest(candidate, "0:v:0")
    if accepted_video_digest != candidate_video_digest:
        raise RuntimeError("wrong-audio fixture unexpectedly changed accepted picture")

    evaluator, handlers = build_h3_canonical_audio_runtime_bundle(
        _canonical(),
        unit_id=UNIT_ID,
        project_path=project,
    )
    if evaluator is None:
        raise RuntimeError("canonical audio runtime bundle was not created")

    result = asyncio.run(
        run_h3_runtime_selection_gate(
            candidate,
            evaluator=evaluator,
            repair_handlers=handlers,
        )
    )
    if result.provider_recalled or result.repair_passes != 1:
        raise RuntimeError(f"unexpected audio runtime result: {result}")

    first = result.passes[0]
    if first["plans"][0]["failure_class"] != "audio_only_failure":
        raise RuntimeError(f"unexpected failure class: {first}")
    if first["plans"][0]["repair_action"] != "audio_repair_remux":
        raise RuntimeError(f"unexpected repair action: {first}")

    final_video_digest = _decoded_digest(candidate, "0:v:0")
    if final_video_digest != accepted_video_digest:
        raise RuntimeError("AUDIO_REPAIR_REMUX changed accepted picture frames")

    accepted_audio_digest = _decoded_digest(accepted, "0:a:0")
    final_audio_digest = _decoded_digest(candidate, "0:a:0")
    if final_audio_digest != accepted_audio_digest:
        raise RuntimeError("canonical audio runtime did not restore accepted soundtrack")

    ssim = _video_ssim(candidate, accepted)
    if ssim < 0.999:
        raise RuntimeError(f"audio-only replay changed picture: SSIM={ssim}")

    cuts = detect_expected_cuts(
        candidate,
        target_cut_frames=(FPS * 5,),
        search_radius_frames=2,
        min_scene_score=0.15,
    )
    if tuple(c.actual_cut_frame for c in cuts) != (120,):
        raise RuntimeError(f"unexpected authored cut after audio repair: {cuts}")

    final_sha = sha256_file(candidate)
    probe = _probe(candidate)
    finding = first["findings"][0]
    plan = first["plans"][0]

    pre = H3EvidenceRecord(
        unit_id=UNIT_ID,
        stage="media_qa_structured_finding",
        tested_sha=tested_sha,
        repair_action="audio_repair_remux",
        provider_recalled=False,
        qa_verdict="FAIL_REPAIRABLE",
        source_media_sha256=(candidate_sha,),
        reference_sha256=(AUDIO_SHA256, ACCEPTED_FINAL_SHA256),
        provider_run_id=SUPPLIER_RUN_ID,
        provider_artifact_id=SUPPLIER_ARTIFACT_ID,
    ).sealed()
    post = H3EvidenceRecord(
        unit_id=UNIT_ID,
        stage="re_qa",
        tested_sha=tested_sha,
        repair_action="audio_repair_remux",
        provider_recalled=False,
        qa_verdict="PASS",
        source_media_sha256=(candidate_sha,),
        reference_sha256=(AUDIO_SHA256, ACCEPTED_FINAL_SHA256),
        provider_run_id=SUPPLIER_RUN_ID,
        provider_artifact_id=SUPPLIER_ARTIFACT_ID,
        post_media_sha256=final_sha,
        actual_cuts=(("final", [c.to_dict() for c in cuts]),),
        media_probe=tuple(sorted(probe.items())),
        previous_record_sha256=pre.record_sha256,
    ).sealed()
    root.mkdir(parents=True, exist_ok=True)
    _write_chain(root, (pre, post))

    report = {
        "status": "FINAL_PASS",
        "unit_id": UNIT_ID,
        "tested_sha": tested_sha,
        "finding": finding,
        "failure_class": plan["failure_class"],
        "repair_action": plan["repair_action"],
        "provider_recalled": result.provider_recalled,
        "runtime_gate": result.to_dict(),
        "source_hashes": {
            "canonical_audio": AUDIO_SHA256,
            "accepted_final": ACCEPTED_FINAL_SHA256,
            "wrong_audio_candidate": candidate_sha,
        },
        "final_media_sha256": final_sha,
        "accepted_video_framemd5_sha256": accepted_video_digest,
        "final_video_framemd5_sha256": final_video_digest,
        "accepted_audio_framemd5_sha256": accepted_audio_digest,
        "final_audio_framemd5_sha256": final_audio_digest,
        "accepted_vs_replay_video_ssim": ssim,
        "final_detected_cuts": [c.to_dict() for c in cuts],
        "media_probe": probe,
        "evidence_head_sha256": post.record_sha256,
    }
    (root / "phase4_e13u01_audio_repair_replay.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
