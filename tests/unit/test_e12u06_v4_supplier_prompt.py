from __future__ import annotations

import hashlib
from pathlib import Path

from lib.video_prompt_compilers.h3_prompt_compiler import (
    compile_h3_ref2va_prompt,
    validate_h3_native_ref2va_prompt,
)


PROMPT_PATH = Path(".github/supplier-prompts/E12U06.v4.txt")


def test_e12u06_v4_is_strict_native_and_byte_stable() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    validated = validate_h3_native_ref2va_prompt(
        prompt,
        duration_seconds=10,
        reference_count=1,
    )
    compiled = compile_h3_ref2va_prompt(
        source_prompt=prompt,
        duration_seconds=10,
        reference_count=1,
        reference_source_names=["AI峰会"],
        options={"reference_kinds": {"AI峰会": "scene"}},
    )
    assert validated == prompt
    assert compiled == prompt


def test_e12u06_v4_uses_positive_concrete_visual_states() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    detailed = prompt.split("detailed_description:", 1)[1]
    assert "Three broad solid white horizontal rectangles" in detailed
    assert "One thin solid white rectangular bar" in detailed
    assert "the empty threshold, the adjacent wing wall, and the immediate stage floor" in detailed
    assert "this empty architectural view remains unchanged for the rest of the shot" in detailed
    assert "identity-title" not in prompt
    assert "anyone emerging" not in prompt
    assert "portrait" not in prompt.lower()
    assert "headshot" not in prompt.lower()
    assert '"沈知意' not in prompt


def test_e12u06_v4_prompt_sha_is_reportable() -> None:
    prompt = PROMPT_PATH.read_bytes()
    digest = hashlib.sha256(prompt).hexdigest()
    assert len(digest) == 64
    print("E12U06_V4_PROMPT_SHA256=" + digest)
