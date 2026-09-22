"""Delivery compatibility QA for 《离婚后我成了AI大佬》 v3.3 family.

This test intentionally separates ArcReel-native import compatibility from the current
shipping contract (11 episodes / 16:9 / reference_video / H3 Ref2VA preview).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from lib.project_manager import ProjectManager
from lib.reference_video.h3_prompt_execution import compile_reference_video_provider_prompt
from lib.reference_video.prompt_preview import build_reference_prompt_preview_payload
from server.services.project_archive import ProjectArchiveService

PROJECT_NAME = "lihunhou-ai-dalao-v33-qa"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _manual_zip(project_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(project_dir.rglob("*")):
            relative = item.relative_to(project_dir)
            arcname = f"{PROJECT_NAME}/{relative.as_posix()}"
            if item.is_dir():
                archive.writestr(zipfile.ZipInfo(arcname.rstrip("/") + "/"), b"")
            else:
                archive.write(item, arcname=arcname)


def _seed_v33_source(pm: ProjectManager) -> Path:
    pm.create_project(PROJECT_NAME)
    pm.create_project_metadata(
        PROJECT_NAME,
        "离婚后，我成了AI大佬 v3.3 QA",
        "写实电影感，横屏16:9，低饱和，都市科技质感",
        "drama",
    )
    project = pm.load_project(PROJECT_NAME)
    project.update(
        {
            "source_kind": "screenplay",
            "aspect_ratio": "16:9",
            "generation_mode": "reference_video",
            "grid_storyboard": False,
            "episodes": [
                {
                    "episode": episode,
                    "title": f"第{episode:02d}集",
                    "script_file": f"scripts/episode_{episode}.json",
                }
                for episode in range(1, 16)
            ],
            "characters": {
                "沈知意": {"description": "女主，都市职业女性，AI领域核心人才。"},
                "陆予深": {"description": "男主，商务西装，克制冷感。"},
                "陆念": {"description": "六岁女童。"},
                "苏晚": {"description": "都市女性，社交形象精致。"},
            },
            "scenes": {
                "M国机场": {"description": "国际机场到达层，冷白灯。"},
                "陆家别墅": {"description": "现代别墅。"},
                "国际AI峰会主会场": {"description": "白色科技舞台与巨幅屏幕。"},
                "天枢新品发布会": {"description": "现代科技发布会舞台。"},
            },
            "props": {},
            "products": {},
        }
    )
    pm.save_project(PROJECT_NAME, project)

    root = pm.get_project_path(PROJECT_NAME)
    for episode in range(1, 16):
        units = []
        for shot in range(1, 17):
            unit_id = f"E{episode}U{shot:02d}"
            if episode == 1 and shot == 1:
                text = (
                    "@[M国机场] 中景，50mm，平视，缓慢推近。"
                    "@[沈知意]拖着行李走出机场，手机生日祝福不断亮起。"
                    "@[沈知意]：{今天是我生日。}"
                )
            elif episode == 13 and shot == 7:
                text = (
                    "@[国际AI峰会主会场] 近景，50mm，平视，固定镜头。"
                    "@[沈知意]走到故障控制台，要求技术人员开放底层日志。"
                    "@[沈知意]：{打开底层日志。}"
                )
            elif episode == 15 and shot == 15:
                text = (
                    "@[天枢新品发布会] 特写，85mm，缓慢推近。"
                    "@[沈知意]微微抬眼，语气平静。"
                    "@[沈知意]：{只是回来，拿回原本属于我的东西。}"
                )
            else:
                text = f"第{episode:02d}集第{shot:02d}镜，5秒，横屏16:9，剧情镜头。"
            units.append(
                {
                    "unit_id": unit_id,
                    "duration_seconds": 5,
                    "text": text,
                    "transition_to_next": "cut",
                    "generated_assets": {},
                    "needs_replan": False,
                }
            )
        if episode == 15:
            units[-1]["transition_to_next"] = "black"
        _write_json(
            root / "scripts" / f"episode_{episode}.json",
            {
                "episode": episode,
                "title": f"第{episode:02d}集",
                "content_mode": "drama",
                "generation_mode": "reference_video",
                "duration_seconds": 80,
                "summary": "v3.3 compatibility QA",
                "novel": {"title": "离婚后，我成了AI大佬", "chapter": f"第{episode:02d}集"},
                "video_units": units,
            },
        )
    return root


def test_v33_native_archive_imports_but_preserves_15_episode_shape(tmp_path: Path) -> None:
    source_pm = ProjectManager(tmp_path / "source-projects")
    source_root = _seed_v33_source(source_pm)
    archive_path = tmp_path / "v33.zip"
    _manual_zip(source_root, archive_path)

    target_pm = ProjectManager(tmp_path / "target-projects")
    result = ProjectArchiveService(target_pm).import_project_archive(
        archive_path,
        uploaded_filename="v33.zip",
    )

    assert result.project_name == PROJECT_NAME
    imported_project = target_pm.load_project(PROJECT_NAME)
    assert imported_project["aspect_ratio"] == "16:9"
    assert imported_project["generation_mode"] == "reference_video"
    assert len(imported_project["episodes"]) == 15

    total_units = 0
    total_seconds = 0
    for episode in range(1, 16):
        script = target_pm.load_script(PROJECT_NAME, f"scripts/episode_{episode}.json")
        assert len(script["video_units"]) == 16
        assert all(unit["duration_seconds"] == 5 for unit in script["video_units"])
        assert all(unit["generated_assets"]["status"] == "pending" for unit in script["video_units"])
        total_units += len(script["video_units"])
        total_seconds += sum(unit["duration_seconds"] for unit in script["video_units"])

    assert total_units == 240
    assert total_seconds == 1200


def test_v33_representative_shot_compiles_to_h3_ref2va_preview() -> None:
    source_prompt = (
        "@[国际AI峰会主会场] 近景，50mm，平视，固定镜头。"
        "@[沈知意]走到故障控制台，要求技术人员开放底层日志。"
        "@[沈知意]：{打开底层日志。}"
    )
    request_assets = [
        {"reference": {"name": "国际AI峰会主会场", "type": "scene"}},
        {"reference": {"name": "沈知意", "type": "character"}},
    ]
    compilation = compile_reference_video_provider_prompt(
        source_prompt=source_prompt,
        fallback_prompt=source_prompt,
        model_name="minimax_h3_zm_u24",
        duration_seconds=5,
        request_assets=request_assets,
        payload={"prompt_compiler": "auto"},
        max_prompt_chars=500000,
        unit_id="E13U07",
    )
    preview = build_reference_prompt_preview_payload(compilation)
    print("\\nV33_H3_PREVIEW_START")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    print("V33_H3_PREVIEW_END")

    assert preview["compiler_applied"] is True
    assert preview["generation_mode"] == "ref2va"
    assert preview["duration_seconds"] == 5
    assert preview["reference_mapping"] == [
        {
            "index": 1,
            "picture": "<Picture 1>",
            "subject": "<Subject 1>",
            "label": "国际AI峰会主会场",
            "source_name": "国际AI峰会主会场",
        },
        {
            "index": 2,
            "picture": "<Picture 2>",
            "subject": "<Subject 2>",
            "label": "沈知意",
            "source_name": "沈知意",
        },
    ]
    assert "subject_definitions:" in preview["provider_prompt"]
    assert "summary:" in preview["provider_prompt"]
    assert "retention_analysis:" in preview["provider_prompt"]
    assert "detailed_description:" in preview["provider_prompt"]
    assert "overall_soundscape:" in preview["provider_prompt"]
    assert "non_diegetic_music:" in preview["provider_prompt"]
    assert "<Subject 1>" in preview["provider_prompt"]
    assert "<Subject 2>" in preview["provider_prompt"]
    assert "<d>[Chinese] 打开底层日志。</d>" in preview["provider_prompt"]
    assert len(preview["provider_prompt_sha256"]) == 64
