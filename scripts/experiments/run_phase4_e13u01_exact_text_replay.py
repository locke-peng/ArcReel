"""Phase 4 E13U01 exact-text runtime replay over existing supplier evidence.

The replay never calls MiniMax. It builds a deterministic wrong-plate candidate from the
accepted H3 entrance plate plus detached canonical audio, then lets the production
exact-text runtime bundle detect and repair the first Canonical shot.
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
from lib.reference_video.h3_exact_text_runtime import build_h3_exact_text_runtime_bundle
from lib.reference_video.h3_repair_executor import sha256_file
from lib.reference_video.h3_runtime_gate import run_h3_runtime_selection_gate

UNIT_ID = "E13U01"
SUPPLIER_RUN_ID = 36098803663
SUPPLIER_ARTIFACT_ID = 10848054150
SUPPLIER_ARTIFACT_NAME = "e13u01-v2-deterministic-screen-identity-continuity-evidence"

SCREEN_SHA256 = "6054ad83540f888caf8b8ceec76cdf20e6047c124fef81144860d1db36105d57"
ENTRY_SHA256 = "e408e2bf93e3b0bbbc02495ecb6500ea5390facfe69b8e43b1a4873c420c246f"
AUDIO_SHA256 = "cbda309d698046b6ab185f5d36fdf23ee1a112f6f1f9d39a37368b6f985a7b33"
ACCEPTED_FINAL_SHA256 = "8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12"
PROMPT_SHA256 = "938d9588ade693f7b6ee8feb7007fd0cdb3b9b9cb2dd56062f56cb642be8a831"
REFERENCE_SHA256 = "c6e78a59dd0db3c3cfbab821c3e069d351f1ce7e7455e7b72709733858171bcd"

EXACT_TEXT = "沈知意\n天枢联合创始人"
FPS = 24
SHOT_SECONDS = 5
DURATION_SECONDS = 10
WIDTH = 1280
HEIGHT = 720

_SSIM_RE = re.compile(r"All:(?P<ssim>\d+(?:\.\d+)?)")


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA mismatch: {actual} != {expected}")


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
    video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in payload["streams"] if stream["codec_type"] == "audio")
    result = {
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
    if abs(result["duration"] - DURATION_SECONDS) > 0.05:
        raise RuntimeError(f"unexpected duration: {result}")
    if (result["width"], result["height"]) != (WIDTH, HEIGHT):
        raise RuntimeError(f"unexpected resolution: {result}")
    if result["video_codec"] != "h264" or result["audio_codec"] != "aac":
        raise RuntimeError(f"unexpected codecs: {result}")
    return result


def _make_wrong_plate(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}",
        "-frames:v",
        "1",
        str(path),
    )


def _build_candidate(wrong_plate: Path, entry: Path, audio: Path, output: Path) -> None:
    """Create the same 5s+5s authored structure with an intentionally wrong shot-1 plate."""

    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-t",
        str(SHOT_SECONDS),
        "-i",
        str(wrong_plate),
        "-i",
        str(entry),
        "-i",
        str(audio),
        "-filter_complex",
        (
            "[0:v]scale=1280:720,format=yuv420p,"
            "trim=duration=5,setpts=PTS-STARTPTS[v0];"
            "[1:v]trim=start=0:end=5,setpts=PTS-STARTPTS,"
            "scale=1280:720:force_original_aspect_ratio=increase,"
            "crop=1280:720,format=yuv420p[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[v]"
        ),
        "-map",
        "[v]",
        "-map",
        "2:a:0",
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
        "-t",
        str(DURATION_SECONDS),
        "-movflags",
        "+faststart",
        str(output),
    )


def _canonical_director() -> dict[str, Any]:
    return {
        "unit": {
            "unit_id": UNIT_ID,
            "duration_sec": DURATION_SECONDS,
            "shots": [
                {
                    "shot_id": "E13U01-S01",
                    "start_sec": 0,
                    "end_sec": SHOT_SECONDS,
                    "screen_text": [
                        {
                            "kind": "identity_title",
                            "legibility": "exact",
                            "text": EXACT_TEXT,
                            "plate_spec": {
                                "schema_version": 1,
                                "ownership": "deterministic_plate",
                                "compositing": "full_frame_replace",
                                "asset_path": "fixtures/E13U01_exact_screen.png",
                                "asset_sha256": SCREEN_SHA256,
                                "region": {
                                    "unit": "normalized",
                                    "x": 0,
                                    "y": 0,
                                    "width": 1,
                                    "height": 1,
                                },
                                "typography": {
                                    "authority": "asset_pixels",
                                    "layout": "accepted_e13u01_identity_plate",
                                },
                                "ssim_threshold": 0.99,
                            },
                        }
                    ],
                },
                {
                    "shot_id": "E13U01-S02",
                    "start_sec": SHOT_SECONDS,
                    "end_sec": DURATION_SECONDS,
                    "screen_text": [],
                },
            ],
        },
        "registries": {},
    }


def _decoded_stream_digest(path: Path, selector: str) -> str:
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
        raise RuntimeError("ffmpeg did not emit an SSIM summary")
    return float(matches[-1])


def _extract_review_frames(video: Path, output_dir: Path) -> tuple[int, ...]:
    frames = (6, 114, 119, 120, 126, 234)
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
    return frames


def _write_chain(root: Path, records: tuple[H3EvidenceRecord, ...]) -> None:
    for record in records:
        record.verify()
    (root / "evidence_hash_chain.json").write_text(
        json.dumps([record.to_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    tested_sha = os.environ.get("GITHUB_SHA", "").strip()
    if not tested_sha:
        raise RuntimeError("GITHUB_SHA is required for acceptance evidence")

    upstream_project = args.upstream_dir / "project"
    screen = upstream_project / "fixtures" / "E13U01_exact_screen.png"
    entry = args.upstream_dir / "E13U01_v2_entry_provider_raw.mp4"
    audio = upstream_project / "fixtures" / "E13U01_host_applause_audio.wav"
    accepted_final = upstream_project / "reference_videos" / "E13U01.mp4"

    _require_sha(screen, SCREEN_SHA256, "exact screen plate")
    _require_sha(entry, ENTRY_SHA256, "accepted entry provider plate")
    _require_sha(audio, AUDIO_SHA256, "detached canonical audio")
    _require_sha(accepted_final, ACCEPTED_FINAL_SHA256, "accepted final reference")

    root = args.output_dir / UNIT_ID
    wrong_plate = root / "wrong_plate.png"
    final_video = root / "project" / "reference_videos" / "E13U01.mp4"
    _make_wrong_plate(wrong_plate)
    _build_candidate(wrong_plate, entry, audio, final_video)
    candidate_sha256 = sha256_file(final_video)

    evaluator, handlers = build_h3_exact_text_runtime_bundle(
        _canonical_director(),
        unit_id=UNIT_ID,
        project_path=upstream_project,
    )
    if evaluator is None:
        raise RuntimeError("E13U01 exact-text runtime bundle was not created")

    runtime_result = asyncio.run(
        run_h3_runtime_selection_gate(
            final_video,
            evaluator=evaluator,
            repair_handlers=handlers,
        )
    )
    if runtime_result.provider_recalled:
        raise RuntimeError("E13U01 exact-text runtime unexpectedly recalled provider")
    if runtime_result.repair_passes != 1:
        raise RuntimeError(f"unexpected exact-text repair pass count: {runtime_result}")

    first_pass = runtime_result.passes[0]
    findings = first_pass.get("findings") or []
    plans = first_pass.get("plans") or []
    if len(findings) != 1 or len(plans) != 1:
        raise RuntimeError(f"unexpected E13U01 runtime routing: {runtime_result}")
    finding = findings[0]
    plan = plans[0]
    if plan.get("failure_class") != "exact_text_required":
        raise RuntimeError(f"unexpected E13U01 failure class: {plan}")
    if plan.get("repair_action") != "deterministic_text_plate":
        raise RuntimeError(f"unexpected E13U01 repair action: {plan}")

    probe = _probe(final_video)
    cuts = detect_expected_cuts(
        final_video,
        target_cut_frames=(FPS * SHOT_SECONDS,),
        search_radius_frames=2,
        min_scene_score=0.15,
    )
    if tuple(cut.actual_cut_frame for cut in cuts) != (FPS * SHOT_SECONDS,):
        raise RuntimeError(f"unexpected E13U01 authored cut: {cuts}")

    accepted_audio_digest = _decoded_stream_digest(accepted_final, "0:a:0")
    replay_audio_digest = _decoded_stream_digest(final_video, "0:a:0")
    if accepted_audio_digest != replay_audio_digest:
        raise RuntimeError("E13U01 detached canonical audio changed during runtime repair")

    ssim = _video_ssim(final_video, accepted_final)
    if ssim < 0.99:
        raise RuntimeError(f"E13U01 runtime replay diverged from accepted final: SSIM={ssim}")

    review_frames = _extract_review_frames(final_video, root / "review_frames")
    final_sha256 = sha256_file(final_video)

    pre = H3EvidenceRecord(
        unit_id=UNIT_ID,
        stage="media_qa_structured_finding",
        tested_sha=tested_sha,
        repair_action="deterministic_text_plate",
        provider_recalled=False,
        qa_verdict="FAIL_REPAIRABLE",
        source_media_sha256=(candidate_sha256,),
        prompt_sha256=PROMPT_SHA256,
        reference_sha256=(REFERENCE_SHA256, SCREEN_SHA256),
        provider_run_id=SUPPLIER_RUN_ID,
        provider_artifact_id=SUPPLIER_ARTIFACT_ID,
        evidence_frames=(0,),
    ).sealed()

    post = H3EvidenceRecord(
        unit_id=UNIT_ID,
        stage="re_qa",
        tested_sha=tested_sha,
        repair_action="deterministic_text_plate",
        provider_recalled=False,
        qa_verdict="PASS",
        source_media_sha256=(candidate_sha256,),
        prompt_sha256=PROMPT_SHA256,
        reference_sha256=(REFERENCE_SHA256, SCREEN_SHA256),
        provider_run_id=SUPPLIER_RUN_ID,
        provider_artifact_id=SUPPLIER_ARTIFACT_ID,
        post_media_sha256=final_sha256,
        actual_cuts=(("final", [cut.to_dict() for cut in cuts]),),
        media_probe=tuple(sorted(probe.items())),
        evidence_frames=review_frames,
        previous_record_sha256=pre.record_sha256,
    ).sealed()
    _write_chain(root, (pre, post))

    report = {
        "status": "FINAL_PASS",
        "unit_id": UNIT_ID,
        "tested_sha": tested_sha,
        "finding": finding,
        "failure_class": plan["failure_class"],
        "repair_action": plan["repair_action"],
        "provider_recalled": runtime_result.provider_recalled,
        "runtime_gate": runtime_result.to_dict(),
        "source_supplier_run_id": SUPPLIER_RUN_ID,
        "source_supplier_artifact_id": SUPPLIER_ARTIFACT_ID,
        "source_supplier_artifact_name": SUPPLIER_ARTIFACT_NAME,
        "source_hashes": {
            "exact_screen": SCREEN_SHA256,
            "entry_provider_video": ENTRY_SHA256,
            "detached_audio": AUDIO_SHA256,
            "accepted_final": ACCEPTED_FINAL_SHA256,
            "runtime_candidate": candidate_sha256,
        },
        "final_media_sha256": final_sha256,
        "media_probe": probe,
        "final_detected_cuts": [cut.to_dict() for cut in cuts],
        "accepted_vs_replay_video_ssim": ssim,
        "accepted_vs_replay_audio_framemd5_sha256": accepted_audio_digest,
        "review_frames": list(review_frames),
        "evidence_head_sha256": post.record_sha256,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase4_e13u01_exact_text_replay.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
