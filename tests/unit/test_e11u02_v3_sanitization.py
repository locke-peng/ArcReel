from scripts.experiments.sanitize_e11u02_v3 import (
    EXPECTED_DURATION_SECONDS,
    EXPECTED_HEIGHT,
    EXPECTED_WIDTH,
    MASKS,
    SOURCE_VIDEO_SHA256,
    UNIT_ID,
    _filter_graph,
)


def test_e11u02_v3_is_postprocess_only() -> None:
    assert UNIT_ID == "E11U02"
    assert SOURCE_VIDEO_SHA256 == "edff353aa05833b3fb523f2ec48b7b58adbd6e7aba1bdccd71f5a0142dde5055"
    assert EXPECTED_DURATION_SECONDS == 15.0
    assert EXPECTED_WIDTH == 864
    assert EXPECTED_HEIGHT == 480


def test_e11u02_v3_masks_cover_all_three_shots() -> None:
    names = {mask.name for mask in MASKS}
    assert any(name.startswith("shot1_") for name in names)
    assert any(name.startswith("shot2_") for name in names)
    assert any(name.startswith("shot3_") for name in names)


def test_e11u02_v3_shot1_masks_cover_known_screen_surfaces() -> None:
    names = {mask.name for mask in MASKS}
    assert {
        "shot1_left_wall_display",
        "shot1_rear_center_display",
        "shot1_front_left_display",
        "shot1_front_right_display",
        "shot1_far_right_display",
        "shot1_indicator_inner_screen",
    }.issubset(names)


def test_e11u02_v3_shot2_uses_time_scoped_badge_tracking_masks() -> None:
    badge_masks = [mask for mask in MASKS if mask.name.startswith("shot2_badge")]
    assert len(badge_masks) >= 5
    assert min(mask.start for mask in badge_masks) <= 5.5
    assert max(mask.end for mask in badge_masks) >= 10.0


def test_e11u02_v3_shot3_removes_corridor_exit_surface() -> None:
    exit_masks = [mask for mask in MASKS if mask.name == "shot3_exit_sign"]
    assert len(exit_masks) == 1
    assert exit_masks[0].start <= 10.8
    assert exit_masks[0].end >= 15.0


def test_e11u02_v3_masks_stay_inside_delivery_frame() -> None:
    for mask in MASKS:
        assert mask.start >= 0
        assert mask.end <= EXPECTED_DURATION_SECONDS
        assert mask.start < mask.end
        assert mask.x >= 0
        assert mask.y >= 0
        assert mask.x + mask.width <= EXPECTED_WIDTH
        assert mask.y + mask.height <= EXPECTED_HEIGHT
        assert mask.block >= 2


def test_e11u02_v3_filtergraph_is_deterministic_pixelation() -> None:
    graph = _filter_graph()
    assert "flags=area" in graph
    assert "flags=neighbor" in graph
    assert "overlay=" in graph
    assert "between(t,0.00,5.00)" in graph
    assert "between(t,7.00,10.00)" in graph
    assert "between(t,10.80,15.00)" in graph


def test_e11u02_v3_does_not_regenerate_timeline_or_audio() -> None:
    graph = _filter_graph()
    assert "trim=" not in graph
    assert "concat=" not in graph
    assert "setpts=PTS-STARTPTS" in graph
