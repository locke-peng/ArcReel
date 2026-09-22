"""Standalone formal delivery QA for the exact v3.3 ArcReel archive.

Runs outside pytest so repository-wide server.app fixtures cannot mix a newer full-repo
server API with the user's true-machine Golden H3 overlay.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from lib.project_manager import ProjectManager
from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from server.services.project_archive import ProjectArchiveService

EXPECTED_DURATIONS = [10, 15, 15, 15, 15, 10]
EXPECTED_SHOT_COUNTS = [2, 3, 3, 3, 3, 2]
REQUIRED_SECTIONS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)


def asset(name: str, asset_type: str) -> dict:
    return {"reference": {"name": name, "type": asset_type}}


def preview(unit: dict, assets: list[dict]) -> dict:
    provider_prompt = compile_reference_video_provider_prompt(
        source_prompt=unit["text"],
        fallback_prompt=unit["text"],
        model_name="minimax_h3_zm_u24",
        duration_seconds=int(unit["duration_seconds"]),
        request_assets=assets,
        payload={"prompt_compiler": "auto"},
        max_prompt_chars=500_000,
    )
    labels = [entry["reference"]["name"] for entry in assets]
    payload = build_reference_prompt_preview_payload(
        provider_prompt=provider_prompt,
        rendered_prompt=unit["text"],
        model_id="minimax_h3_zm_u24",
        prompt_compiler="auto",
        compiler_applied=True,
        duration_seconds=int(unit["duration_seconds"]),
        reference_labels=labels,
        max_prompt_chars=500_000,
    )
    payload["generation_mode"] = "ref2va"
    payload["provider_prompt_sha256"] = hashlib.sha256(
        provider_prompt.encode("utf-8")
    ).hexdigest()

    assert payload["compiler_applied"] is True
    assert payload["generation_mode"] == "ref2va"
    assert payload["duration_seconds"] == int(unit["duration_seconds"])
    assert len(payload["provider_prompt_sha256"]) == 64
    assert all(section in provider_prompt for section in REQUIRED_SECTIONS)
    return payload


def main() -> None:
    package_env = os.environ.get("FORMAL_PACKAGE_ZIP")
    if not package_env:
        raise RuntimeError("FORMAL_PACKAGE_ZIP is required")
    package_zip = Path(package_env)
    if not package_zip.is_file():
        raise FileNotFoundError(package_zip)

    with tempfile.TemporaryDirectory(prefix="formal-v33-qa-") as temp_dir:
        root = Path(temp_dir)
        pm = ProjectManager(root / "projects")
        service = ProjectArchiveService(pm)

        result = service.import_project_archive(
            package_zip,
            uploaded_filename="lihunhou-ai-dalao-v33.zip",
            conflict_policy="prompt",
        )
        project_name = result.project_name
        project = pm.load_project(project_name)

        assert project["aspect_ratio"] == "16:9"
        assert project["generation_mode"] == "reference_video"
        assert project["content_mode"] == "drama"
        assert len(project["episodes"]) == 15

        total_units = 0
        total_shots = 0
        total_seconds = 0
        for episode_num in range(1, 16):
            script = pm.load_script(project_name, f"scripts/episode_{episode_num}.json")
            units = script["video_units"]
            assert len(units) == 6
            assert [int(unit["duration_seconds"]) for unit in units] == EXPECTED_DURATIONS
            assert [unit["text"].count("[Shot ") for unit in units] == EXPECTED_SHOT_COUNTS
            assert all(4 <= int(unit["duration_seconds"]) <= 15 for unit in units)
            assert all(isinstance(unit.get("generated_assets"), dict) for unit in units)
            assert all(unit["generated_assets"].get("status") == "pending" for unit in units)

            total_units += len(units)
            total_shots += sum(unit["text"].count("[Shot ") for unit in units)
            total_seconds += sum(int(unit["duration_seconds"]) for unit in units)

        assert total_units == 90
        assert total_shots == 240
        assert total_seconds == 1200

        imported_root = pm.get_project_path(project_name)
        assert (imported_root / "source" / "SOURCE_PROVENANCE.json").is_file()
        assert all(
            (imported_root / "source" / f"episode_{n}.md").is_file()
            for n in range(1, 16)
        )

        e1 = pm.load_script(project_name, "scripts/episode_1.json")
        e13 = pm.load_script(project_name, "scripts/episode_13.json")
        ten_second = e1["video_units"][0]
        fifteen_second = e13["video_units"][2]

        preview_10 = preview(
            ten_second,
            [
                asset("M国机场", "scene"),
                asset("沈知意", "character"),
                asset("手机", "prop"),
                asset("陆予深", "character"),
            ],
        )
        preview_15 = preview(
            fifteen_second,
            [
                asset("学校教室", "scene"),
                asset("陆念", "character"),
                asset("AI峰会", "scene"),
                asset("沈知意", "character"),
            ],
        )

        assert ten_second["text"].count("[Shot ") == 2
        assert preview_10["provider_prompt"].count("<scenetrans>") == 1
        assert "[Shot 1]" in preview_10["provider_prompt"]
        assert "[Shot 2]" in preview_10["provider_prompt"]

        assert fifteen_second["text"].count("[Shot ") == 3
        assert preview_15["provider_prompt"].count("<scenetrans>") == 2
        assert "[Shot 1]" in preview_15["provider_prompt"]
        assert "[Shot 2]" in preview_15["provider_prompt"]
        assert "[Shot 3]" in preview_15["provider_prompt"]
        assert "打开底层日志" in preview_15["provider_prompt"]

        preview_10_repeat = preview(
            ten_second,
            [
                asset("M国机场", "scene"),
                asset("沈知意", "character"),
                asset("手机", "prop"),
                asset("陆予深", "character"),
            ],
        )
        preview_15_repeat = preview(
            fifteen_second,
            [
                asset("学校教室", "scene"),
                asset("陆念", "character"),
                asset("AI峰会", "scene"),
                asset("沈知意", "character"),
            ],
        )
        assert preview_10_repeat["provider_prompt_sha256"] == preview_10["provider_prompt_sha256"]
        assert preview_15_repeat["provider_prompt_sha256"] == preview_15["provider_prompt_sha256"]

        exported_zip, _ = service.export_project(project_name)
        try:
            roundtrip_pm = ProjectManager(root / "roundtrip-projects")
            roundtrip = ProjectArchiveService(roundtrip_pm).import_project_archive(
                exported_zip,
                uploaded_filename="roundtrip.zip",
                conflict_policy="prompt",
            )
            roundtrip_project = roundtrip_pm.load_project(roundtrip.project_name)
            assert roundtrip_project["aspect_ratio"] == "16:9"
            assert roundtrip_project["generation_mode"] == "reference_video"
            assert len(roundtrip_project["episodes"]) == 15
            roundtrip_e13 = roundtrip_pm.load_script(
                roundtrip.project_name,
                "scripts/episode_13.json",
            )
            assert [int(u["duration_seconds"]) for u in roundtrip_e13["video_units"]] == EXPECTED_DURATIONS
            assert [u["text"].count("[Shot ") for u in roundtrip_e13["video_units"]] == EXPECTED_SHOT_COUNTS
        finally:
            exported_zip.unlink(missing_ok=True)

        evidence = {
            "status": "FORMAL_QA_PASS",
            "project_name": project_name,
            "episodes": 15,
            "video_units": total_units,
            "canonical_shots": total_shots,
            "duration_seconds": total_seconds,
            "aspect_ratio": project["aspect_ratio"],
            "generation_mode": project["generation_mode"],
            "content_mode": project["content_mode"],
            "import_diagnostics": result.diagnostics,
            "h3_10s": preview_10,
            "h3_15s": preview_15,
            "roundtrip_import": "PASS",
        }
        print("FORMAL_V33_EVIDENCE_START")
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print("FORMAL_V33_EVIDENCE_END")


if __name__ == "__main__":
    main()
