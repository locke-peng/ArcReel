"""Formal acceptance for the exact v3.3 delivery ZIP bytes."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

from lib.project_manager import ProjectManager
from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from server.services.project_archive import ProjectArchiveService

EXPECTED_ZIP_SHA256 = "ce0c602b9f3085fe8dfafd4f1840b3914e7b4220867f814adcd83474149c7b8d"
PROJECT_NAME = "lihunhou-ai-dalao-v33"
DURATIONS = [10, 15, 15, 15, 15, 10]
SHOT_COUNTS = [2, 3, 3, 3, 3, 2]


def _materialize_exact_package(tmp_path: Path) -> Path:
    fixture_dir = Path(__file__).parents[3] / "fixtures"
    encoded = "".join(
        (fixture_dir / f"v33_exact_part{i}.b64").read_text(encoding="utf-8")
        for i in range(1, 5)
    )
    data = base64.b64decode(encoded)
    assert hashlib.sha256(data).hexdigest() == EXPECTED_ZIP_SHA256
    archive = tmp_path / "v33-exact.zip"
    archive.write_bytes(data)
    return archive


def _assert_project_contract(pm: ProjectManager, name: str) -> None:
    project = pm.load_project(name)
    assert project["aspect_ratio"] == "16:9"
    assert project["generation_mode"] == "reference_video"
    assert project["content_mode"] == "drama"
    assert len(project["episodes"]) == 15

    total_units = total_shots = total_seconds = 0
    for episode in range(1, 16):
        script = pm.load_script(name, f"scripts/episode_{episode}.json")
        units = script["video_units"]
        assert len(units) == 6
        assert [unit["duration_seconds"] for unit in units] == DURATIONS
        assert [unit["text"].count("[Shot ") for unit in units] == SHOT_COUNTS
        assert all(unit["duration_seconds"] <= 15 for unit in units)
        assert all(unit["generated_assets"]["status"] == "pending" for unit in units)
        assert all(unit.get("needs_replan") is False for unit in units)
        total_units += len(units)
        total_shots += sum(unit["text"].count("[Shot ") for unit in units)
        total_seconds += sum(unit["duration_seconds"] for unit in units)

    assert total_units == 90
    assert total_shots == 240
    assert total_seconds == 1200


def test_exact_zip_import_export_reimport_contract(tmp_path: Path) -> None:
    archive = _materialize_exact_package(tmp_path)
    pm = ProjectManager(tmp_path / "projects")
    service = ProjectArchiveService(pm)

    result = service.import_project_archive(
        archive,
        uploaded_filename="离婚后我成了AI大佬_v3.3_ArcReel_15集_16x9_ReferenceVideo_H3.zip",
    )
    assert result.project_name == PROJECT_NAME
    assert not result.diagnostics["auto_fixed"] or isinstance(result.diagnostics["auto_fixed"], list)
    _assert_project_contract(pm, PROJECT_NAME)

    # Re-open through a fresh manager instance.
    pm_reopen = ProjectManager(tmp_path / "projects")
    _assert_project_contract(pm_reopen, PROJECT_NAME)

    # Official ArcReel export -> delete -> official archive re-import.
    export_service = ProjectArchiveService(pm_reopen)
    exported_archive, _ = export_service.export_project(PROJECT_NAME)
    exported_bytes = exported_archive.read_bytes()
    assert exported_bytes.startswith(b"PK")

    shutil.rmtree(pm_reopen.get_project_path(PROJECT_NAME))
    assert not pm_reopen.project_exists(PROJECT_NAME)

    reimport = export_service.import_project_archive(
        exported_archive,
        uploaded_filename="official-roundtrip.zip",
    )
    assert reimport.project_name == PROJECT_NAME
    _assert_project_contract(pm_reopen, PROJECT_NAME)


def _compile_preview(unit: dict, request_assets: list[dict]) -> dict:
    compilation = compile_reference_video_provider_prompt(
        source_prompt=unit["text"],
        fallback_prompt=unit["text"],
        model_name="minimax_h3_zm_u24",
        duration_seconds=unit["duration_seconds"],
        request_assets=request_assets,
        payload={"prompt_compiler": "auto"},
        max_prompt_chars=500000,
        unit_id=unit["unit_id"],
    )
    return build_reference_prompt_preview_payload(compilation)


def test_exact_package_10s_and_15s_h3_previews(tmp_path: Path) -> None:
    archive = _materialize_exact_package(tmp_path)
    pm = ProjectManager(tmp_path / "projects")
    ProjectArchiveService(pm).import_project_archive(archive, uploaded_filename="v33.zip")

    e1 = pm.load_script(PROJECT_NAME, "scripts/episode_1.json")
    preview10 = _compile_preview(
        e1["video_units"][0],
        [
            {"reference": {"name": "M国机场", "type": "scene"}},
            {"reference": {"name": "沈知意", "type": "character"}},
        ],
    )
    assert preview10["compiler_applied"] is True
    assert preview10["generation_mode"] == "ref2va"
    assert preview10["duration_seconds"] == 10
    assert "[Shot 1]" in preview10["provider_prompt"]
    assert "[Shot 2]" in preview10["provider_prompt"]
    assert preview10["provider_prompt"].count("<scenetrans>") == 1
    assert len(preview10["provider_prompt_sha256"]) == 64

    e13 = pm.load_script(PROJECT_NAME, "scripts/episode_13.json")
    preview15 = _compile_preview(
        e13["video_units"][2],
        [
            {"reference": {"name": "AI峰会", "type": "scene"}},
            {"reference": {"name": "沈知意", "type": "character"}},
        ],
    )
    assert preview15["compiler_applied"] is True
    assert preview15["generation_mode"] == "ref2va"
    assert preview15["duration_seconds"] == 15
    assert "[Shot 1]" in preview15["provider_prompt"]
    assert "[Shot 2]" in preview15["provider_prompt"]
    assert "[Shot 3]" in preview15["provider_prompt"]
    assert preview15["provider_prompt"].count("<scenetrans>") == 2
    assert len(preview15["provider_prompt_sha256"]) == 64

    print("FORMAL_PREVIEW_10S_START")
    print(json.dumps(preview10, ensure_ascii=False, indent=2))
    print("FORMAL_PREVIEW_10S_END")
    print("FORMAL_PREVIEW_15S_START")
    print(json.dumps(preview15, ensure_ascii=False, indent=2))
    print("FORMAL_PREVIEW_15S_END")


def test_exact_package_discloses_reference_asset_binary_gap(tmp_path: Path) -> None:
    archive = _materialize_exact_package(tmp_path)
    import zipfile

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        image_names = [
            name
            for name in names
            if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            and any(f"/{bucket}/" in name for bucket in ("characters", "scenes", "props", "products"))
        ]
    # Formal finding: this delivery ZIP has registries but no reference image binaries.
    assert image_names == []
