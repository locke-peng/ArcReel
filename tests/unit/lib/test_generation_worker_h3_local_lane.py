from __future__ import annotations

import pytest

from lib.generation_worker import CapacityTable, GenerationWorker, _extract_provider


@pytest.mark.asyncio
async def test_h3_media_repair_routes_to_local_worker_provider() -> None:
    provider = await _extract_provider(
        {
            "task_type": "h3_media_repair",
            "media_type": "local",
            "project_name": "does-not-matter",
            "payload": {},
        }
    )
    assert provider == "local"


def test_local_worker_lane_has_independent_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_MAX_WORKERS", "2")
    capacity = CapacityTable.from_env()
    assert capacity.get("local", "local") == 2
    worker = GenerationWorker(capacity=capacity)
    assert "local" in worker._lanes
