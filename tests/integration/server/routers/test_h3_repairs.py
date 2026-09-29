from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.reference_video.h3_repair_ticket_store import H3RepairTicketLifecycleState
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import h3_repairs


@pytest.fixture
def h3_repairs_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(h3_repairs.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="u1", sub="alice", role="admin")
    return TestClient(app)


def test_pending_repairs_uses_awaiting_approval_filter(
    h3_repairs_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_mock = AsyncMock(return_value=[{"ticket_id": "h3rt_one", "unit_id": "E13U03"}])
    monkeypatch.setattr(h3_repairs, "list_h3_repair_tickets", list_mock)

    response = h3_repairs_client.get(
        "/api/v1/projects/demo/reference-videos/repairs/pending",
        params={"unit_id": "E13U03"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"ticket_id": "h3rt_one", "unit_id": "E13U03"}],
        "count": 1,
    }
    list_mock.assert_awaited_once_with(
        project_name="demo",
        lifecycle_state=H3RepairTicketLifecycleState.AWAITING_APPROVAL,
        unit_id="E13U03",
        limit=100,
    )


def test_approve_endpoint_runs_binding_and_queue_admission(
    h3_repairs_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approve_mock = AsyncMock(
        return_value={
            "ticket": {"ticket_id": "h3rt_one", "lifecycle": {"state": "queued"}},
            "approval": {"approved_by": "operator:alice"},
            "queue": {"task_id": "task-1", "task_status": "queued"},
        }
    )
    monkeypatch.setattr(h3_repairs, "approve_and_enqueue_h3_repair", approve_mock)

    response = h3_repairs_client.post(
        "/api/v1/projects/demo/reference-videos/repairs/h3rt_one/approve",
        json={"max_provider_calls": 1},
    )

    assert response.status_code == 200
    assert response.json()["ticket"]["lifecycle"]["state"] == "queued"
    approve_mock.assert_awaited_once_with(
        project_name="demo",
        ticket_id="h3rt_one",
        approved_by="u1",
        max_provider_calls=1,
    )


def test_approve_endpoint_rejects_more_than_one_provider_call(
    h3_repairs_client: TestClient,
) -> None:
    response = h3_repairs_client.post(
        "/api/v1/projects/demo/reference-videos/repairs/h3rt_one/approve",
        json={"max_provider_calls": 2},
    )
    assert response.status_code == 422


def test_detail_execution_and_result_routes(
    h3_repairs_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        h3_repairs,
        "get_h3_repair_ticket",
        AsyncMock(return_value={"ticket_id": "h3rt_one", "failure_class": "large_semantic_failure"}),
    )
    monkeypatch.setattr(
        h3_repairs,
        "get_h3_repair_execution_status",
        AsyncMock(return_value={"ticket_id": "h3rt_one", "lifecycle_state": "running"}),
    )
    monkeypatch.setattr(
        h3_repairs,
        "get_h3_repair_result",
        AsyncMock(return_value={"ticket_id": "h3rt_one", "reqa_outcome": "PASS"}),
    )

    detail = h3_repairs_client.get("/api/v1/projects/demo/reference-videos/repairs/h3rt_one")
    execution = h3_repairs_client.get("/api/v1/projects/demo/reference-videos/repairs/h3rt_one/execution")
    result = h3_repairs_client.get("/api/v1/projects/demo/reference-videos/repairs/h3rt_one/result")

    assert detail.status_code == 200
    assert detail.json()["failure_class"] == "large_semantic_failure"
    assert execution.status_code == 200
    assert execution.json()["lifecycle_state"] == "running"
    assert result.status_code == 200
    assert result.json()["reqa_outcome"] == "PASS"


def test_reject_and_cancel_routes_delegate_existing_lifecycle_services(
    h3_repairs_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reject_mock = AsyncMock(return_value={"ticket_id": "h3rt_one", "lifecycle": {"state": "rejected"}})
    cancel_mock = AsyncMock(
        return_value={
            "ticket": {"ticket_id": "h3rt_two", "lifecycle": {"state": "cancelled"}},
            "task_cancel": None,
        }
    )
    monkeypatch.setattr(h3_repairs, "reject_h3_repair", reject_mock)
    monkeypatch.setattr(h3_repairs, "cancel_h3_repair", cancel_mock)

    rejected = h3_repairs_client.post(
        "/api/v1/projects/demo/reference-videos/repairs/h3rt_one/reject",
        json={"reason": "not approved"},
    )
    cancelled = h3_repairs_client.post(
        "/api/v1/projects/demo/reference-videos/repairs/h3rt_two/cancel",
        json={},
    )

    assert rejected.status_code == 200
    assert rejected.json()["lifecycle"]["state"] == "rejected"
    assert cancelled.status_code == 200
    assert cancelled.json()["ticket"]["lifecycle"]["state"] == "cancelled"
    reject_mock.assert_awaited_once_with(
        project_name="demo",
        ticket_id="h3rt_one",
        rejected_by="u1",
        reason="not approved",
    )
    cancel_mock.assert_awaited_once_with(
        project_name="demo",
        ticket_id="h3rt_two",
        cancelled_by="u1",
        reason=None,
    )
