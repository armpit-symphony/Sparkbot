from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import ChatUser, UserType
from tests.utils.utils import random_lower_string


def _chat_headers() -> dict[str, str]:
    with Session(engine) as db:
        user = ChatUser(
            username=f"mcp-{random_lower_string()[:10]}",
            type=UserType.HUMAN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    token = create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


def test_mcp_registry_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get(f"{settings.API_V1_STR}/chat/mcp/registry")
    assert response.status_code in {401, 403}


def test_mcp_registry_returns_policy_manifests(client: TestClient) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/chat/mcp/registry",
        headers=_chat_headers(),
    )
    assert response.status_code == 200
    payload = response.json()

    manifests = {entry["id"]: entry for entry in payload["manifests"]}
    assert "sparkbot.shell_run" in manifests
    assert "lima.navigate" in manifests

    lima_nav = manifests["lima.navigate"]
    assert lima_nav["runtime"] == "lima-robo-os"
    assert "robot-motion" in lima_nav["policy"]
    assert lima_nav["riskLevel"] == "critical"
    assert lima_nav["approvalRequired"] is True
    assert lima_nav["explainPlanRequired"] is True
    assert lima_nav["status"]["state"] in {"configured", "bridge-needed"}

    assert payload["runTimeline"][0] == "User request"
    assert payload["health"]["sparkbotApiLive"] is True


def test_mcp_explain_plan_returns_policy_dry_run(client: TestClient) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/explain-plan",
        headers=_chat_headers(),
        json={
            "manifest_id": "lima.navigate",
            "user_request": "Send the demo robot through a patrol route.",
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["simulationOnly"] is True
    assert payload["runId"]
    assert payload["runStatus"] in {"awaiting_approval", "blocked"}
    assert payload["manifest"]["id"] == "lima.navigate"
    assert payload["policyToolName"] == "lima.navigate"
    assert payload["dryRunRequired"] is True
    assert payload["approvalRequired"] is True
    assert payload["canExecuteNow"] is False
    assert payload["policy"]["decision"]["action"] in {"privileged", "deny"}
    assert payload["timeline"][0]["step"] == "User request"
    assert "route" in payload["toolArgs"]

    runs_response = client.get(
        f"{settings.API_V1_STR}/chat/mcp/runs",
        headers=_chat_headers(),
    )
    assert runs_response.status_code == 200


def test_mcp_runs_list_includes_created_plan(client: TestClient) -> None:
    headers = _chat_headers()
    plan_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/explain-plan",
        headers=headers,
        json={"manifest_id": "lima.replay_simulation", "user_request": "Preview robot replay."},
    )
    assert plan_response.status_code == 200
    run_id = plan_response.json()["runId"]

    runs_response = client.get(f"{settings.API_V1_STR}/chat/mcp/runs", headers=headers)
    assert runs_response.status_code == 200
    runs = runs_response.json()["runs"]
    assert any(run["id"] == run_id for run in runs)

    detail_response = client.get(f"{settings.API_V1_STR}/chat/mcp/runs/{run_id}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == run_id
    assert detail["manifestId"] == "lima.replay_simulation"
    assert detail["plan"]["simulationOnly"] is True


def test_mcp_run_approval_lifecycle_is_non_executing(client: TestClient) -> None:
    headers = _chat_headers()
    plan_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/explain-plan",
        headers=headers,
        json={"manifest_id": "lima.replay_simulation", "user_request": "Approve replay preview."},
    )
    assert plan_response.status_code == 200
    run_id = plan_response.json()["runId"]

    request_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/runs/{run_id}/request-approval",
        headers=headers,
    )
    assert request_response.status_code == 200
    requested = request_response.json()
    assert requested["status"] == "awaiting_approval"
    assert requested["approvalId"]

    approve_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/runs/{run_id}/approve",
        headers=headers,
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "ready"
    assert approved["approvedAt"]
    assert "No tool has been executed" in approved["statusMessage"]

    approve_again_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/runs/{run_id}/approve",
        headers=headers,
    )
    assert approve_again_response.status_code == 409

    deny_plan_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/explain-plan",
        headers=headers,
        json={"manifest_id": "lima.replay_simulation", "user_request": "Deny replay preview."},
    )
    assert deny_plan_response.status_code == 200
    deny_run_id = deny_plan_response.json()["runId"]
    deny_request_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/runs/{deny_run_id}/request-approval",
        headers=headers,
    )
    assert deny_request_response.status_code == 200

    deny_response = client.post(
        f"{settings.API_V1_STR}/chat/mcp/runs/{deny_run_id}/deny",
        headers=headers,
        json={"reason": "Operator changed course."},
    )
    assert deny_response.status_code == 200
    denied = deny_response.json()
    assert denied["status"] == "blocked"
    assert denied["statusMessage"] == "Operator changed course."
