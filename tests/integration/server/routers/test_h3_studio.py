from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import h3_studio


@pytest.fixture
def studio_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(h3_studio.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="u1", sub="alice", role="admin")
    return TestClient(app)


def test_summary_and_control_routes_delegate_authoritative_services(
    studio_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary_mock = AsyncMock(
        return_value={
            "project": {"project_name": "demo", "state_counts": {"complete": 2}},
            "control": {"paused": False, "max_running_tasks": 2},
            "budget": {"reserved_provider_calls": 1},
            "queues": {"pending_approvals": [], "active_executions": [], "human_review_required": []},
        }
    )
    control_mock = AsyncMock(
        return_value={
            "project_name": "demo",
            "paused": False,
            "max_running_tasks": 2,
            "explicit": True,
        }
    )
    monkeypatch.setattr(h3_studio, "get_h3_studio_summary", summary_mock)
    monkeypatch.setattr(h3_studio, "get_h3_studio_control", control_mock)

    summary = studio_client.get("/api/v1/projects/demo/reference-videos/studio/summary")
    control = studio_client.get("/api/v1/projects/demo/reference-videos/studio/control")

    assert summary.status_code == 200
    assert summary.json()["project"]["state_counts"]["complete"] == 2
    assert control.status_code == 200
    assert control.json()["max_running_tasks"] == 2
    summary_mock.assert_awaited_once_with(project_name="demo")
    control_mock.assert_awaited_once_with(project_name="demo")


def test_pause_and_running_cap_routes_delegate_control_service(
    studio_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pause_mock = AsyncMock(
        return_value={"project_name": "demo", "paused": True, "max_running_tasks": None, "explicit": True}
    )
    cap_mock = AsyncMock(
        return_value={"project_name": "demo", "paused": True, "max_running_tasks": 3, "explicit": True}
    )
    monkeypatch.setattr(h3_studio, "set_h3_studio_paused", pause_mock)
    monkeypatch.setattr(h3_studio, "set_h3_studio_running_cap", cap_mock)

    pause = studio_client.put(
        "/api/v1/projects/demo/reference-videos/studio/control/pause",
        json={"paused": True},
    )
    cap = studio_client.put(
        "/api/v1/projects/demo/reference-videos/studio/control/running-cap",
        json={"max_running_tasks": 3},
    )

    assert pause.status_code == 200
    assert pause.json()["paused"] is True
    assert cap.status_code == 200
    assert cap.json()["max_running_tasks"] == 3
    pause_mock.assert_awaited_once_with(project_name="demo", paused=True)
    cap_mock.assert_awaited_once_with(project_name="demo", max_running_tasks=3)


def test_batch_preview_is_read_only_and_batch_execute_propagates_authenticated_actor(
    studio_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_mock = AsyncMock(
        return_value={
            "project_name": "demo",
            "action": "approve",
            "items": [
                {
                    "ticket_id": "h3rt_one",
                    "eligible": True,
                    "reason": "approval_pending",
                }
            ],
        }
    )
    execute_mock = AsyncMock(
        return_value={
            "project_name": "demo",
            "action": "approve",
            "items": [{"ticket_id": "h3rt_one", "success": True}],
        }
    )
    monkeypatch.setattr(h3_studio, "preview_h3_studio_batch", preview_mock)
    monkeypatch.setattr(h3_studio, "execute_h3_studio_batch", execute_mock)

    payload = {
        "action": "approve",
        "ticket_ids": ["h3rt_one"],
        "reason": "operator reviewed",
    }
    preview = studio_client.post(
        "/api/v1/projects/demo/reference-videos/studio/batch/preview",
        json=payload,
    )
    execute = studio_client.post(
        "/api/v1/projects/demo/reference-videos/studio/batch/execute",
        json=payload,
    )

    assert preview.status_code == 200
    assert preview.json()["items"][0]["eligible"] is True
    assert execute.status_code == 200
    assert execute.json()["items"][0]["success"] is True
    preview_mock.assert_awaited_once_with(
        project_name="demo",
        action="approve",
        ticket_ids=["h3rt_one"],
    )
    execute_mock.assert_awaited_once_with(
        project_name="demo",
        action="approve",
        ticket_ids=["h3rt_one"],
        actor="u1",
        reason="operator reviewed",
    )


def test_evidence_route_exposes_sanitized_ticket_view(
    studio_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_mock = AsyncMock(
        return_value={
            "ticket_id": "h3rt_one",
            "execution": {"task_id": "task-1"},
            "provider_call_allowance": {"provider_call_count": 1},
        }
    )
    monkeypatch.setattr(h3_studio, "get_h3_studio_ticket_evidence", evidence_mock)

    response = studio_client.get(
        "/api/v1/projects/demo/reference-videos/studio/evidence/h3rt_one"
    )

    assert response.status_code == 200
    assert response.json()["ticket_id"] == "h3rt_one"
    assert "execution_checkpoint_json" not in response.text
    evidence_mock.assert_awaited_once_with(
        project_name="demo",
        ticket_id="h3rt_one",
    )


def test_studio_request_validation_rejects_invalid_batch_and_cap(
    studio_client: TestClient,
) -> None:
    empty_batch = studio_client.post(
        "/api/v1/projects/demo/reference-videos/studio/batch/preview",
        json={"action": "approve", "ticket_ids": []},
    )
    zero_cap = studio_client.put(
        "/api/v1/projects/demo/reference-videos/studio/control/running-cap",
        json={"max_running_tasks": 0},
    )

    assert empty_batch.status_code == 422
    assert zero_cap.status_code == 422
