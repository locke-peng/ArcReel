"""CI QA for 《离婚后，我成了AI大佬》 E01 ArcReel import contract."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from lib.project_manager import ProjectManager
from server.services.project_archive import ProjectArchiveService


NAME = "lihunhou-ai-dalao-e01-qa"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _manual_zip(project_dir: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(project_dir.rglob("*")):
            rel = item.relative_to(project_dir)
            name = f"{NAME}/{rel.as_posix()}"
            if item.is_dir():
                archive.writestr(zipfile.ZipInfo(name.rstrip("/") + "/"), b"")
            else:
                archive.write(item, arcname=name)


def test_lihunhou_e01_manual_zip_imports_as_16x9_reference_video(tmp_path: Path) -> None:
    source = ProjectManager(tmp_path / "source-projects")
    source.create_project(NAME)
    source.create_project_metadata(NAME, "离婚后，我成了AI大佬｜E01 QA", "写实电影感，16:9横屏", "drama")

    project = source.load_project(NAME)
    project.update(
        {
            "source_kind": "screenplay",
            "aspect_ratio": "16:9",
            "generation_mode": "reference_video",
            "grid_storyboard": False,
            "episodes": [{"episode": 1, "title": "生日礼物不是给我", "script_file": "scripts/episode_1.json"}],
            "characters": {
                "沈知意": {"description": "约30岁中国女性。", "character_sheet": "characters/沈知意.png"},
                "陆念": {"description": "6岁中国女童。", "character_sheet": "characters/陆念.png"},
            },
            "scenes": {
                "陆念房间": {"description": "暖黄台灯、矮桌、贝壳和丝线。", "scene_sheet": "scenes/陆念房间.png"}
            },
            "props": {
                "贝壳生日礼物": {"description": "贝壳与丝线手工礼物。", "prop_sheet": "props/贝壳生日礼物.png"}
            },
            "products": {},
        }
    )
    source.save_project(NAME, project)
    project_dir = source.get_project_path(NAME)

    for rel in (
        "characters/沈知意.png",
        "characters/陆念.png",
        "scenes/陆念房间.png",
        "props/贝壳生日礼物.png",
    ):
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"qa-fixture")

    durations = [10, 9, 10, 10, 9, 10, 10, 9, 9, 8, 11]
    units = []
    for index, duration in enumerate(durations, start=1):
        text = "@[陆念房间] @[沈知意] 与 @[陆念] 同框，桌上有 @[贝壳生日礼物]。"
        if index == 6:
            text += (
                "[Shot 1] 0.0-5.0秒：50mm近景，固定。"
                "[Shot 2] 5.0-8.0秒：100mm极微特写，向右小幅横移。"
                "[Shot 3] 8.0-10.0秒：100mm大特写，沈知意的手突然僵住。"
                "@[陆念]：{还有七天就是苏阿姨生日了，这些贝壳都是我和爸爸准备的，爸爸还帮我一颗一颗打磨呢。}"
            )
        units.append(
            {
                "unit_id": f"E1U{index}",
                "duration_seconds": duration,
                "text": text,
                "transition_to_next": "black" if index == 11 else "cut",
                "generated_assets": {},
                "needs_replan": False,
            }
        )

    _write_json(
        project_dir / "scripts" / "episode_1.json",
        {
            "episode": 1,
            "title": "生日礼物不是给我",
            "content_mode": "drama",
            "generation_mode": "reference_video",
            "duration_seconds": 105,
            "summary": "E01 QA",
            "novel": {"title": "离婚后，我成了AI大佬", "chapter": "第1集"},
            "video_units": units,
        },
    )

    archive_path = tmp_path / "lihunhou-e01-qa.zip"
    _manual_zip(project_dir, archive_path)

    target = ProjectManager(tmp_path / "target-projects")
    result = ProjectArchiveService(target).import_project_archive(
        archive_path,
        uploaded_filename="lihunhou-e01-qa.zip",
    )

    assert result.project_name == NAME
    imported_project = target.load_project(NAME)
    assert imported_project["aspect_ratio"] == "16:9"
    assert imported_project["generation_mode"] == "reference_video"
    assert imported_project["content_mode"] == "drama"
    assert imported_project["source_kind"] == "screenplay"

    imported = target.load_script(NAME, "scripts/episode_1.json")
    assert len(imported["video_units"]) == 11
    assert sum(unit["duration_seconds"] for unit in imported["video_units"]) == 105
    assert [unit["unit_id"] for unit in imported["video_units"]] == [f"E1U{i}" for i in range(1, 12)]
    assert all(unit["generated_assets"]["status"] == "pending" for unit in imported["video_units"])

    root = target.get_project_path(NAME)
    assert (root / "characters" / "沈知意.png").is_file()
    assert (root / "characters" / "陆念.png").is_file()
    assert (root / "props" / "贝壳生日礼物.png").is_file()
