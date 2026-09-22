"""QA: 《离婚后，我成了AI大佬》E01 native ArcReel import fixture.

This test intentionally uses the public project-archive seam, not a private JSON validator.
It proves that a 16:9 drama/reference_video project with E01's 11 video units can be
accepted by ArcReel's own ProjectArchiveService before the 11-episode package is shipped.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from lib.project_manager import ProjectManager
from server.services.project_archive import ProjectArchiveService


PROJECT_NAME = "lihunhou_ai_dalao_e01_qa"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _manual_zip(project_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(project_dir.rglob("*")):
            relative = item.relative_to(project_dir)
            arcname = f"{PROJECT_NAME}/{relative.as_posix()}"
            if item.is_dir():
                info = zipfile.ZipInfo(arcname.rstrip("/") + "/")
                archive.writestr(info, b"")
            else:
                archive.write(item, arcname=arcname)


def _unit(unit_id: str, duration: int, text: str) -> dict:
    return {
        "unit_id": unit_id,
        "duration_seconds": duration,
        "text": text,
        "transition_to_next": "cut",
        "generated_assets": {},
        "needs_replan": False,
    }


def _seed_source_project(pm: ProjectManager) -> Path:
    pm.create_project(PROJECT_NAME)
    pm.create_project_metadata(
        PROJECT_NAME,
        "离婚后，我成了AI大佬｜E01 QA",
        "写实电影感，16:9横屏，浅景深，低饱和",
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
                    "episode": 1,
                    "title": "生日礼物不是给我",
                    "script_file": "scripts/episode_1.json",
                }
            ],
            "characters": {
                "沈知意": {
                    "description": "约30岁中国女性，黑色长发低马尾，米白风衣。",
                    "character_sheet": "characters/沈知意.png",
                },
                "陆念": {
                    "description": "6岁中国女童，黑色齐耳短发，浅粉色家居服。",
                    "character_sheet": "characters/陆念.png",
                },
                "周姨": {
                    "description": "中年女性，深灰制服，发髻整齐。",
                    "character_sheet": "characters/周姨.png",
                },
            },
            "scenes": {
                "M国国际机场到达层": {
                    "description": "夜间国际机场到达层，冷白顶灯、玻璃与金属材质。",
                    "scene_sheet": "scenes/M国国际机场到达层.png",
                },
                "陆家别墅门厅与楼梯": {
                    "description": "夜间别墅门厅与楼梯，室外冷、门廊暖。",
                    "scene_sheet": "scenes/陆家别墅门厅与楼梯.png",
                },
                "陆念房间": {
                    "description": "暖黄台灯、矮桌、贝壳和丝线的儿童房。",
                    "scene_sheet": "scenes/陆念房间.png",
                },
                "二楼长走廊": {
                    "description": "陆家别墅二楼长走廊，冷暖交界。",
                    "scene_sheet": "scenes/二楼长走廊.png",
                },
                "二楼走廊照片墙区域": {
                    "description": "二楼走廊照片墙区域。",
                    "scene_sheet": "scenes/二楼走廊照片墙区域.png",
                },
            },
            "props": {
                "沈知意手机": {
                    "description": "现代智能手机。",
                    "prop_sheet": "props/沈知意手机.png",
                },
                "旅行箱": {
                    "description": "中型旅行箱。",
                    "prop_sheet": "props/旅行箱.png",
                },
                "贝壳生日礼物": {
                    "description": "贝壳与丝线手工生日礼物。",
                    "prop_sheet": "props/贝壳生日礼物.png",
                },
                "照片墙": {
                    "description": "陆念张贴的生活照片墙。",
                    "prop_sheet": "props/照片墙.png",
                },
            },
            "products": {},
        }
    )
    pm.save_project(PROJECT_NAME, project)

    project_dir = pm.get_project_path(PROJECT_NAME)
    for rel in (
        "characters/沈知意.png",
        "characters/陆念.png",
        "characters/周姨.png",
        "scenes/M国国际机场到达层.png",
        "scenes/陆家别墅门厅与楼梯.png",
        "scenes/陆念房间.png",
        "scenes/二楼长走廊.png",
        "scenes/二楼走廊照片墙区域.png",
        "props/沈知意手机.png",
        "props/旅行箱.png",
        "props/贝壳生日礼物.png",
        "props/照片墙.png",
    ):
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"QA-fixture-image")

    units = [
        _unit("E1U1", 10, "@[M国国际机场到达层] @[沈知意]拖着@[旅行箱]穿过人流，查看@[沈知意手机]。"),
        _unit("E1U2", 9, "@[陆家别墅门厅与楼梯] @[沈知意]到门口，@[周姨]开门。@[周姨]：{太太，您……怎么来了？}"),
        _unit("E1U3", 10, "@[陆家别墅门厅与楼梯] @[沈知意]把@[旅行箱]交给@[周姨]，随后上楼。"),
        _unit("E1U4", 10, "@[陆念房间] @[沈知意]推门，@[陆念]抬头。@[沈知意]：{念念。} @[陆念]：{妈妈！}"),
        _unit("E1U5", 9, "@[陆念房间] @[沈知意]抱住@[陆念]，桌上是@[贝壳生日礼物]。"),
        _unit(
            "E1U6",
            10,
            "16:9横屏。@[沈知意]站在孩子身后偏侧位置；@[陆念]坐在矮桌前串@[贝壳生日礼物]。"
            "[Shot 1] 0.0-5.0秒：50mm近景，平视，固定。"
            "[Shot 2] 5.0-8.0秒：100mm极微特写，镜头沿桌面向右小幅横移。"
            "[Shot 3] 8.0-10.0秒：100mm大特写，沈知意的手突然僵住。"
            "@[陆念]：{还有七天就是苏阿姨生日了，这些贝壳都是我和爸爸准备的，爸爸还帮我一颗一颗打磨呢。}",
        ),
        _unit("E1U7", 10, "@[陆念房间] @[陆念]继续低头，@[沈知意]轻声问她是否记得妈妈生日。"),
        _unit("E1U8", 9, "@[陆念房间] @[陆念]再次低头整理@[贝壳生日礼物]，@[沈知意]慢慢松开手。"),
        _unit("E1U9", 9, "@[二楼长走廊] @[沈知意]带上房门，走向@[照片墙]。"),
        _unit("E1U10", 8, "@[二楼走廊照片墙区域] @[沈知意]逐张看@[照片墙]，属于母亲的位置几乎没有出现。"),
        _unit("E1U11", 11, "@[二楼走廊照片墙区域] @[周姨]传话；@[沈知意]打开@[沈知意手机]拨号。"),
    ]
    units[-1]["transition_to_next"] = "black"
    _write_json(
        project_dir / "scripts" / "episode_1.json",
        {
            "episode": 1,
            "title": "生日礼物不是给我",
            "content_mode": "drama",
            "generation_mode": "reference_video",
            "duration_seconds": 105,
            "summary": "沈知意生日当天回国，连续确认丈夫与女儿都把苏晚放在她之前。",
            "novel": {"title": "离婚后，我成了AI大佬", "chapter": "第1集"},
            "video_units": units,
        },
    )
    return project_dir


def test_lihunhou_e01_manual_archive_imports_as_16x9_reference_video(tmp_path: Path) -> None:
    source_pm = ProjectManager(tmp_path / "source-projects")
    project_dir = _seed_source_project(source_pm)
    archive_path = tmp_path / "lihunhou-e01-qa.zip"
    _manual_zip(project_dir, archive_path)

    target_pm = ProjectManager(tmp_path / "target-projects")
    result = ProjectArchiveService(target_pm).import_project_archive(
        archive_path,
        uploaded_filename="lihunhou-e01-qa.zip",
    )

    assert result.project_name == PROJECT_NAME
    imported_project = target_pm.load_project(PROJECT_NAME)
    assert imported_project["aspect_ratio"] == "16:9"
    assert imported_project["generation_mode"] == "reference_video"
    assert imported_project["content_mode"] == "drama"
    assert imported_project["source_kind"] == "screenplay"
    assert len(imported_project["episodes"]) == 1

    imported = target_pm.load_script(PROJECT_NAME, "scripts/episode_1.json")
    assert len(imported["video_units"]) == 11
    assert sum(unit["duration_seconds"] for unit in imported["video_units"]) == 105
    assert [unit["unit_id"] for unit in imported["video_units"]] == [f"E1U{i}" for i in range(1, 12)]
    assert all(unit["generated_assets"]["status"] == "pending" for unit in imported["video_units"])

    u06 = imported["video_units"][5]
    assert u06["duration_seconds"] == 10
    assert "@[沈知意]" in u06["text"]
    assert "@[陆念]" in u06["text"]
    assert "@[贝壳生日礼物]" in u06["text"]

    imported_root = target_pm.get_project_path(PROJECT_NAME)
    assert (imported_root / "characters" / "沈知意.png").is_file()
    assert (imported_root / "characters" / "陆念.png").is_file()
    assert (imported_root / "props" / "贝壳生日礼物.png").is_file()
