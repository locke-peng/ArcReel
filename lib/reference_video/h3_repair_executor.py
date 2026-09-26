"""Execution boundary for H3 repair decisions.

The executor consumes an already-planned H3RepairDecision. It deliberately does not
reclassify failures or choose actions, and provider recall is disabled by default.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from lib.reference_video.h3_production_policy import H3RepairDecision

RepairRunner = Callable[[], None]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class H3RepairExecutionResult:
    action: str
    provider_recalled: bool
    source_media_sha256: tuple[str, ...]
    output_media_sha256: str
    output_media_path: str


def execute_h3_media_repair(
    decision: H3RepairDecision,
    *,
    source_media: Iterable[Path],
    output_media: Path,
    deterministic_runner: RepairRunner | None = None,
    provider_runner: RepairRunner | None = None,
    allow_provider_recall: bool = False,
) -> H3RepairExecutionResult:
    """Execute exactly the action chosen by the Phase 3 planner.

    Deterministic actions require deterministic_runner. Provider actions fail closed
    unless both an explicit provider runner and allow_provider_recall=True are supplied.
    """

    sources = tuple(Path(path) for path in source_media)
    if not sources:
        raise ValueError("source_media must not be empty")
    for path in sources:
        if not path.is_file():
            raise FileNotFoundError(path)

    if decision.provider_recall_required:
        if not allow_provider_recall or provider_runner is None:
            raise RuntimeError(
                "repair requires provider recall but provider execution is disabled"
            )
        runner = provider_runner
        provider_recalled = True
    else:
        if deterministic_runner is None:
            raise RuntimeError("deterministic repair requires deterministic_runner")
        runner = deterministic_runner
        provider_recalled = False

    source_hashes = tuple(sha256_file(path) for path in sources)
    runner()

    if not output_media.is_file() or output_media.stat().st_size == 0:
        raise RuntimeError(f"repair did not produce output media: {output_media}")

    return H3RepairExecutionResult(
        action=decision.action.value,
        provider_recalled=provider_recalled,
        source_media_sha256=source_hashes,
        output_media_sha256=sha256_file(output_media),
        output_media_path=str(output_media),
    )
