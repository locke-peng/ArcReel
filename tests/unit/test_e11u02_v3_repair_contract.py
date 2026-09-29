import importlib
import inspect

from scripts.experiments.run_e11u02_v3_deterministic_repair import (
    DURATION_SECONDS,
    FPS,
    HEIGHT,
    SHOT1_SCREEN_RECTS,
    SHOT2_LABEL_KEYFRAMES,
    SHOT3_EXIT_SIGN_RECT,
    SHOT3_LEFT_FEATHER_END,
    SHOT3_LEFT_FULL,
    SHOT3_RIGHT_FEATHER_START,
    SHOT3_RIGHT_FULL,
    SHOT_SECONDS,
    UNIT_ID,
    UPSTREAM_ARTIFACT_ID,
    UPSTREAM_HEAD_SHA,
    UPSTREAM_RUN_ID,
    UPSTREAM_SHA256,
    WIDTH,
    _shot2_rect_for,
)


def test_e11u02_v3_upstream_supplier_provenance_is_pinned() -> None:
    assert UNIT_ID == "E11U02"
    assert UPSTREAM_RUN_ID == 36148270693
    assert UPSTREAM_ARTIFACT_ID == 10870732082
    assert UPSTREAM_HEAD_SHA == "e3d5e8abd053442c5981ca76ff4e57a6a84beae4"
    assert UPSTREAM_SHA256 == {
        "shot1": "aecded93bd579ea89cb65f1f7c431446f55c4eac516ce85f90964a408d027a48",
        "shot2": "7effe252c0c0384a7697002d8d095b95cbade03f695949d46e014d2816091507",
        "shot3": "ad6dc5cec862220754b9ba082cdf12f2fb3e569e8777873294e7231b728b9751",
        "soundtrack": "dd8be354040d959ff7e94b2c6e7220148373a2c10c897b88d0b8c6984d9486d2",
    }


def test_e11u02_v3_timeline_is_exact_three_by_five_seconds() -> None:
    assert FPS == 24
    assert SHOT_SECONDS == 5
    assert DURATION_SECONDS == 15
    assert SHOT_SECONDS * 3 == DURATION_SECONDS
    assert (WIDTH, HEIGHT) == (864, 480)


def test_e11u02_v3_shot1_scrubs_only_explicit_screen_surfaces() -> None:
    assert len(SHOT1_SCREEN_RECTS) >= 7
    for x1, y1, x2, y2 in SHOT1_SCREEN_RECTS:
        assert 0 <= x1 < x2 <= WIDTH
        assert 0 <= y1 < y2 <= HEIGHT
    # Preserve the foreground physical status module around x~400-500/y~260-400.
    assert all(not (x1 <= 430 <= x2 and y1 <= 360 <= y2) for x1, y1, x2, y2 in SHOT1_SCREEN_RECTS)


def test_e11u02_v3_badge_text_scrub_tracks_full_five_second_action() -> None:
    assert SHOT2_LABEL_KEYFRAMES[0][0] == 0.0
    assert SHOT2_LABEL_KEYFRAMES[-1][0] == 5.0
    assert _shot2_rect_for(0.25) is None
    for t in (0.75, 1.25, 1.75, 2.25, 3.25, 4.75):
        rect = _shot2_rect_for(t)
        assert rect is not None
        x1, y1, x2, y2 = rect
        assert 0 <= x1 < x2 <= WIDTH
        assert 0 <= y1 < y2 <= HEIGHT


def test_e11u02_v3_media_defocus_preserves_center_pair_zone() -> None:
    assert SHOT3_LEFT_FULL < SHOT3_LEFT_FEATHER_END < SHOT3_RIGHT_FEATHER_START < SHOT3_RIGHT_FULL
    # Central canonical silhouettes around x=300..620 stay outside full side-defocus zones.
    assert SHOT3_LEFT_FEATHER_END <= 300
    assert SHOT3_RIGHT_FEATHER_START >= 600
    x1, y1, x2, y2 = SHOT3_EXIT_SIGN_RECT
    assert 0 <= x1 < x2 <= WIDTH
    assert 0 <= y1 < y2 <= HEIGHT


def test_e11u02_v3_is_deterministic_repair_not_new_provider_generation() -> None:
    # The repair module should have no provider imports or generation entry points.
    source = inspect.getsource(importlib.import_module("scripts.experiments.run_e11u02_v3_deterministic_repair"))
    assert "MediaGenerator" not in source
    assert "DeclarativeVideoBackend" not in source
    assert "MINIMAX_LIVE_API_KEY" not in source
    assert "provider_recalled" in source
