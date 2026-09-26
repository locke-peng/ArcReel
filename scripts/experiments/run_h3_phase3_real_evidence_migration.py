"""Phase 3 real-evidence migration regression for H3 deterministic production executors.

Consumes immutable paid supplier evidence for E11U02, E15U03 and E13U01.
No provider client, credential, network generation, or semantic repair is available here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.reference_video.h3_media_pipeline import (
    EvidenceChain,
    EvidenceNode,
    RepairAction,
    RepairRegion,
    RepairRegionKeyframe,
    RepairRegionTrack,
    RepairRequest,
    TimelineSegment,
    sha256_file,
)
from lib.reference_video.h3_repair_executors import (
    VisualAuthoringSegment,
    append_authoring_evidence,
    append_repair_evidence,
    execute_av_retime,
    execute_pixel_sanitization,
    execute_sequence_authoring,
)

E11_HASHES = {
    "shot1": "aecded93bd579ea89cb65f1f7c431446f55c4eac516ce85f90964a408d027a48",
    "shot2": "7effe252c0c0384a7697002d8d095b95cbade03f695949d46e014d2816091507",
    "shot3": "ad6dc5cec862220754b9ba082cdf12f2fb3e569e8777873294e7231b728b9751",
    "soundtrack": "dd8be354040d959ff7e94b2c6e7220148373a2c10c897b88d0b8c6984d9486d2",
}
E15_SOURCE_SHA = "17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36"
E13_HASHES = {
    "entry": "e408e2bf93e3b0bbbc02495ecb6500ea5390facfe69b8e43b1a4873c420c246f",
    "screen": "6054ad83540f888caf8b8ceec76cdf20e6047c124fef81144860d1db36105d57",
    "audio": "cbda309d698046b6ab185f5d36fdf23ee1a112f6f1f9d39a37368b6f985a7b33",
}
LEGACY_ACCEPTED_FINAL_SHA = {
    "E11U02": "7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949",
    "E15U03": "607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b",
    "E13U01": "8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12",
}


def _require_sha(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"immutable source SHA mismatch for {path}: {actual} != {expected}")


def _root(stage: str, path: Path, **metadata: object) -> EvidenceNode:
    return EvidenceNode.create(stage=stage, artifact_path=path, metadata=metadata)


def _probe_contract(chain: EvidenceChain, *, duration: float, width: int, height: int) -> dict:
    probe = chain.nodes[-1].metadata["probe"]
    actual_duration = float(probe["format"]["duration"])
    video = next(item for item in probe["streams"] if item["codec_type"] == "video")
    audio = next(item for item in probe["streams"] if item["codec_type"] == "audio")
    if abs(actual_duration - duration) > 0.08:
        raise RuntimeError(f"duration contract failed: {actual_duration} != {duration}")
    if (video.get("width"), video.get("height")) != (width, height):
        raise RuntimeError(f"resolution contract failed: {video}")
    if video.get("codec_name") != "h264" or video.get("r_frame_rate") != "24/1":
        raise RuntimeError(f"video stream contract failed: {video}")
    if audio.get("codec_name") != "aac":
        raise RuntimeError(f"audio codec contract failed: {audio}")
    if audio.get("sample_rate") != "32000" or audio.get("channels") != 2:
        raise RuntimeError(f"audio stream contract failed: {audio}")
    return probe


def _e11(upstream: Path, output: Path) -> dict:
    shot1 = upstream / "E11U02_SHOT1_provider_raw.mp4"
    shot2 = upstream / "E11U02_SHOT2_provider_raw.mp4"
    shot3 = upstream / "E11U02_SHOT3_provider_raw.mp4"
    soundtrack = upstream / "project" / "fixtures" / "E11U02_canonical_soundtrack.wav"
    for key, path in (("shot1", shot1), ("shot2", shot2), ("shot3", shot3), ("soundtrack", soundtrack)):
        _require_sha(path, E11_HASHES[key])

    chain = EvidenceChain(
        unit_id="E11U02",
        nodes=(
            _root("provider_output", shot1, supplier_run_id=36148270693, plate="shot1"),
            _root("provider_output", shot2, supplier_run_id=36148270693, plate="shot2"),
            _root("provider_output", shot3, supplier_run_id=36148270693, plate="shot3"),
            _root("canonical_asset", soundtrack, asset="detached_soundtrack"),
        ),
    )
    chain.validate()

    output.mkdir(parents=True, exist_ok=True)
    processed1 = output / "shot1_scrubbed.mp4"
    processed2 = output / "shot2_badge_scrubbed.mp4"
    processed3 = output / "shot3_media_scrubbed.mp4"

    rects = (
        (0, 45, 90, 270), (345, 135, 495, 245), (250, 245, 370, 350),
        (316, 228, 370, 275), (470, 230, 530, 280), (515, 235, 568, 345),
        (595, 245, 660, 335), (690, 125, 855, 275),
    )
    request1 = RepairRequest(
        action=RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
        source_path=shot1,
        output_path=processed1,
        regions=tuple(
            RepairRegion("E11U02_SHOT03", 0, 5, x1, y1, x2 - x1, y2 - y1, 18, 1)
            for x1, y1, x2, y2 in rects
        ),
    )
    execute_pixel_sanitization(request1)
    chain = append_repair_evidence(chain=chain, request=request1, output_path=processed1)

    raw_keyframes = (
        (0.00, None), (0.45, None), (0.60, (540, 75, 740, 205)),
        (0.75, (510, 85, 720, 200)), (1.00, (350, 80, 550, 220)),
        (1.25, (210, 95, 410, 245)), (1.50, (245, 140, 420, 290)),
        (1.75, (285, 185, 410, 315)), (2.00, (260, 235, 420, 360)),
        (2.25, (245, 265, 425, 395)), (2.75, (245, 270, 420, 395)),
        (5.00, (245, 270, 420, 395)),
    )
    keyframes = []
    for time_sec, rect in raw_keyframes:
        if rect is None:
            keyframes.append(RepairRegionKeyframe(time_sec, 0, 0, 0, 0, False))
        else:
            x1, y1, x2, y2 = rect
            keyframes.append(RepairRegionKeyframe(time_sec, x1, y1, x2 - x1, y2 - y1))
    request2 = RepairRequest(
        action=RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
        source_path=shot2,
        output_path=processed2,
        region_tracks=(
            RepairRegionTrack(
                "E11U02_SHOT04", 0, 5, tuple(keyframes), blur_radius=24, opacity=1
            ),
        ),
    )
    execute_pixel_sanitization(request2)
    chain = append_repair_evidence(chain=chain, request=request2, output_path=processed2)

    request3 = RepairRequest(
        action=RepairAction.DETERMINISTIC_PIXEL_SANITIZATION,
        source_path=shot3,
        output_path=processed3,
        regions=(
            RepairRegion("E11U02_SHOT05", 0, 5, 0, 0, 210, 480, 9, 1),
            RepairRegion("E11U02_SHOT05", 0, 5, 210, 0, 50, 480, 9, 0.5),
            RepairRegion("E11U02_SHOT05", 0, 5, 675, 0, 189, 480, 9, 1),
            RepairRegion("E11U02_SHOT05", 0, 5, 625, 0, 50, 480, 9, 0.5),
            RepairRegion("E11U02_SHOT05", 0, 5, 430, 35, 70, 55, 9, 1),
        ),
    )
    execute_pixel_sanitization(request3)
    chain = append_repair_evidence(chain=chain, request=request3, output_path=processed3)

    final = output / "E11U02.mp4"
    execute_sequence_authoring(
        segments=(
            VisualAuthoringSegment(processed1, 0, 5, 5),
            VisualAuthoringSegment(processed2, 0, 5, 5),
            VisualAuthoringSegment(processed3, 0, 5, 5),
        ),
        audio_path=soundtrack,
        output_path=final,
        width=864,
        height=480,
    )
    chain = append_authoring_evidence(
        chain=chain,
        parent_paths=(processed1, processed2, processed3, soundtrack),
        output_path=final,
        metadata={"canonical_timeline": [5, 5, 5], "provider_recalled": False},
    )
    probe = _probe_contract(chain, duration=15, width=864, height=480)
    return {
        "unit_id": "E11U02",
        "source_hashes": E11_HASHES,
        "final_sha256": sha256_file(final),
        "legacy_accepted_final_sha256": LEGACY_ACCEPTED_FINAL_SHA["E11U02"],
        "byte_equivalent_to_legacy": sha256_file(final) == LEGACY_ACCEPTED_FINAL_SHA["E11U02"],
        "probe": probe,
        "evidence_chain": json.loads(chain.to_json()),
    }


def _e15(upstream: Path, output: Path) -> dict:
    source = upstream / "E15U03.mp4"
    _require_sha(source, E15_SOURCE_SHA)
    chain = EvidenceChain(
        unit_id="E15U03",
        nodes=(_root("provider_output", source, supplier_run_id=36009732060),),
    )
    output.mkdir(parents=True, exist_ok=True)
    final = output / "E15U03.mp4"
    request = RepairRequest(
        action=RepairAction.DETERMINISTIC_AV_RETIME,
        source_path=source,
        output_path=final,
        timeline=(
            TimelineSegment(0, 118 / 24, 5),
            TimelineSegment(118 / 24, 222 / 24, 5),
            TimelineSegment(222 / 24, 342 / 24, 5),
        ),
    )
    execute_av_retime(request)
    chain = append_repair_evidence(chain=chain, request=request, output_path=final)
    probe = _probe_contract(chain, duration=15, width=864, height=480)
    return {
        "unit_id": "E15U03",
        "source_sha256": E15_SOURCE_SHA,
        "canonical_visible_text": ["TIANSHU NEXT"],
        "final_sha256": sha256_file(final),
        "legacy_accepted_final_sha256": LEGACY_ACCEPTED_FINAL_SHA["E15U03"],
        "byte_equivalent_to_legacy": sha256_file(final) == LEGACY_ACCEPTED_FINAL_SHA["E15U03"],
        "probe": probe,
        "evidence_chain": json.loads(chain.to_json()),
    }


def _e13(upstream: Path, output: Path) -> dict:
    entry = upstream / "E13U01_v2_entry_provider_raw.mp4"
    screen = upstream / "project" / "fixtures" / "E13U01_exact_screen.png"
    audio = upstream / "project" / "fixtures" / "E13U01_host_applause_audio.wav"
    for key, path in (("entry", entry), ("screen", screen), ("audio", audio)):
        _require_sha(path, E13_HASHES[key])

    chain = EvidenceChain(
        unit_id="E13U01",
        nodes=(
            _root("provider_output", entry, supplier_run_id=36098803663, plate="C01_entry"),
            _root("canonical_asset", screen, asset="exact_text_plate"),
            _root("canonical_asset", audio, asset="detached_host_applause_audio"),
        ),
    )
    chain.validate()
    output.mkdir(parents=True, exist_ok=True)
    final = output / "E13U01.mp4"
    execute_sequence_authoring(
        segments=(
            VisualAuthoringSegment(screen, 0, 5, 5, fade_in_sec=0.2),
            VisualAuthoringSegment(entry, 0, 5, 5),
        ),
        audio_path=audio,
        output_path=final,
        width=1280,
        height=720,
    )
    chain = append_authoring_evidence(
        chain=chain,
        parent_paths=(screen, entry, audio),
        output_path=final,
        metadata={
            "canonical_timeline": [5, 5],
            "canonical_visible_text": ["沈知意", "天枢联合创始人"],
            "provider_recalled": False,
        },
    )
    probe = _probe_contract(chain, duration=10, width=1280, height=720)
    return {
        "unit_id": "E13U01",
        "source_hashes": E13_HASHES,
        "canonical_visible_text": ["沈知意", "天枢联合创始人"],
        "final_sha256": sha256_file(final),
        "legacy_accepted_final_sha256": LEGACY_ACCEPTED_FINAL_SHA["E13U01"],
        "byte_equivalent_to_legacy": sha256_file(final) == LEGACY_ACCEPTED_FINAL_SHA["E13U01"],
        "probe": probe,
        "evidence_chain": json.loads(chain.to_json()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e11-dir", type=Path, required=True)
    parser.add_argument("--e15-dir", type=Path, required=True)
    parser.add_argument("--e13-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = {
        "phase": "phase3_real_evidence_migration",
        "provider_calls": 0,
        "units": {
            "E11U02": _e11(args.e11_dir, args.output_dir / "E11U02"),
            "E15U03": _e15(args.e15_dir, args.output_dir / "E15U03"),
            "E13U01": _e13(args.e13_dir, args.output_dir / "E13U01"),
        },
    }
    report_path = args.output_dir / "phase3_real_evidence_migration_report.json"
    report_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == "__main__":
    main()
