import importlib
import inspect

from scripts.experiments.run_e15u03_v2_deterministic_timeline import (
    CANONICAL_VISIBLE_TEXT,
    DURATION_SECONDS,
    FPS,
    HEIGHT,
    SHOT1_PAD_FRAMES,
    SHOT1_SOURCE_END_FRAME,
    SHOT1_SOURCE_FRAMES,
    SHOT2_PAD_FRAMES,
    SHOT2_SOURCE_END_FRAME,
    SHOT2_SOURCE_FRAMES,
    SHOT2_SOURCE_START_FRAME,
    SHOT3_SOURCE_END_FRAME,
    SHOT3_SOURCE_FRAMES,
    SHOT3_SOURCE_START_FRAME,
    SHOT_SECONDS,
    SOURCE_C01_IDENTITY_SHA256,
    SOURCE_PROMPT_SHA256,
    SOURCE_REFERENCE_SHA256,
    SOURCE_SUPPLIER_ARTIFACT_ID,
    SOURCE_SUPPLIER_HEAD_SHA,
    SOURCE_SUPPLIER_RUN_ID,
    SOURCE_SUPPLIER_TASK_ID,
    SOURCE_VIDEO_SHA256,
    TARGET_SHOT_FRAMES,
    UNIT_ID,
    WIDTH,
)


def test_e15u03_v2_upstream_supplier_provenance_is_pinned() -> None:
    assert UNIT_ID == "E15U03"
    assert SOURCE_SUPPLIER_RUN_ID == 36009732060
    assert SOURCE_SUPPLIER_ARTIFACT_ID == 10812256991
    assert SOURCE_SUPPLIER_HEAD_SHA == "a5c192427d47c94fe9e60c9c0e5ca62aa35b4be8"
    assert SOURCE_SUPPLIER_TASK_ID == "53944e96-e4b3-465f-b046-a8b6f111de3b"
    assert SOURCE_PROMPT_SHA256 == "b8143dfe1e500a83d6f45f0ca133cf3fed9ab55c7ab6739686c11b0f1eb87dd0"
    assert SOURCE_VIDEO_SHA256 == "17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36"


def test_e15u03_v2_reference_identity_chain_is_pinned() -> None:
    assert SOURCE_REFERENCE_SHA256 == (
        "87d54ccd76abd21e2a03e83036cac6af9469b6de50614a44c67196d0e8b9674a",
        "50893f22ed6e38bd3764f088ec2cd7e1f5ccecaaadd707e0d63ee2e217782bb9",
    )
    assert SOURCE_C01_IDENTITY_SHA256 == SOURCE_REFERENCE_SHA256[1]


def test_e15u03_v2_detected_source_cuts_are_exact() -> None:
    assert FPS == 24
    assert SHOT1_SOURCE_END_FRAME == 118
    assert SHOT2_SOURCE_START_FRAME == 118
    assert SHOT2_SOURCE_END_FRAME == 222
    assert SHOT3_SOURCE_START_FRAME == 222
    assert SHOT3_SOURCE_END_FRAME == 342
    assert SHOT1_SOURCE_FRAMES == 118
    assert SHOT2_SOURCE_FRAMES == 104
    assert SHOT3_SOURCE_FRAMES == 120


def test_e15u03_v2_retimes_each_authored_beat_to_exact_five_seconds() -> None:
    assert SHOT_SECONDS == 5
    assert TARGET_SHOT_FRAMES == 120
    assert SHOT1_PAD_FRAMES == 2
    assert SHOT2_PAD_FRAMES == 16
    assert SHOT1_SOURCE_FRAMES + SHOT1_PAD_FRAMES == TARGET_SHOT_FRAMES
    assert SHOT2_SOURCE_FRAMES + SHOT2_PAD_FRAMES == TARGET_SHOT_FRAMES
    assert SHOT3_SOURCE_FRAMES == TARGET_SHOT_FRAMES
    assert TARGET_SHOT_FRAMES * 3 == FPS * DURATION_SECONDS


def test_e15u03_v2_final_media_contract_is_locked() -> None:
    assert DURATION_SECONDS == 15
    assert (WIDTH, HEIGHT) == (864, 480)
    assert CANONICAL_VISIBLE_TEXT == ("TIANSHU NEXT",)


def test_e15u03_v2_is_deterministic_timeline_repair_not_provider_generation() -> None:
    module = importlib.import_module("scripts.experiments.run_e15u03_v2_deterministic_timeline")
    source = inspect.getsource(module)
    assert "MediaGenerator" not in source
    assert "DeclarativeVideoBackend" not in source
    assert "MINIMAX_LIVE_API_KEY" not in source
    assert '"provider_recalled": False' in source
