import pytest

from lib.reference_video.prompt_compiler_options import (
    normalize_prompt_compiler,
    normalize_reference_image_labels,
    resolve_reference_image_labels,
)


def test_reference_labels_blank_means_auto() -> None:
    assert normalize_reference_image_labels([]) is None
    assert normalize_reference_image_labels(None) is None


def test_reference_labels_preserve_order() -> None:
    assert normalize_reference_image_labels([" 沈家新房 ", "姜采苓", "沈延/被附身"]) == [
        "沈家新房",
        "姜采苓",
        "沈延/被附身",
    ]


def test_reference_labels_count_must_match_actual_send_order() -> None:
    with pytest.raises(ValueError, match="actual reference image count"):
        resolve_reference_image_labels(["A"], derived=["A", "B"])


def test_reference_labels_auto_derive_from_actual_send_order() -> None:
    assert resolve_reference_image_labels(None, derived=["沈家新房", "姜采苓"]) == [
        "沈家新房",
        "姜采苓",
    ]


@pytest.mark.parametrize("value", ["auto", "h3_ref2va", "raw", " H3_REF2VA "])
def test_prompt_compiler_valid_modes(value: str) -> None:
    assert normalize_prompt_compiler(value) in {"auto", "h3_ref2va", "raw"}


def test_prompt_compiler_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="prompt_compiler"):
        normalize_prompt_compiler("whatever")
