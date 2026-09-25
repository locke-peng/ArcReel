from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path("scripts/experiments/postprocess_e13u01_v4.py")


def _module():
    spec = importlib.util.spec_from_file_location("e13v4", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_e13u01_v4_keeps_canonical_unit_geometry() -> None:
    mod = _module()
    assert mod.WIDTH == 864
    assert mod.HEIGHT == 480
    assert mod.FPS == 24
    assert mod.UNIT_SECONDS == 10
    assert mod.SHOT_CUT_SECONDS == 5


def test_e13u01_v4_title_plate_has_exact_two_strings() -> None:
    mod = _module()
    assert mod.TITLE_LINE_1 == "沈知意"
    assert mod.TITLE_LINE_2 == "天枢联合创始人"


def test_e13u01_v4_spotlight_path_moves_toward_stage() -> None:
    mod = _module()
    x5, _ = mod.subject_center(5.0)
    x75, _ = mod.subject_center(7.5)
    x10, _ = mod.subject_center(10.0)
    assert x5 < x75 < x10


def test_e13u01_v4_is_deterministic_post_not_new_provider_generation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "MINIMAX_H3_API_KEY" not in source
    assert "httpx" not in source
    assert "supplier task" not in source.lower()
