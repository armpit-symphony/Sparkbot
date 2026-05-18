import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import ChatUser, UserType
from app.services.lima_robotics_bridge import (
    LimaBridgeError,
    classify_robot_command,
    emergency_stop,
    execute_robot_command,
    list_lima_tools,
    resolve_robot_command,
)
from tests.utils.utils import random_lower_string


def _chat_headers() -> dict[str, str]:
    with Session(engine) as db:
        user = ChatUser(
            username=f"robotics-{random_lower_string()[:10]}",
            type=UserType.HUMAN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    token = create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


def test_robot_command_parser_maps_small_motion() -> None:
    resolved = resolve_robot_command("move forward 0.5 meters")
    assert resolved["toolName"] == "relative_move"
    assert resolved["arguments"] == {"forward": 0.5, "left": 0.0, "degrees": 0.0}


def test_real_hardware_motion_blocks_by_default() -> None:
    decision = classify_robot_command(
        environment="real_hardware",
        tool_name="relative_move",
        arguments={"forward": 0.5},
    )
    assert decision["riskLevel"] == "high"
    assert decision["approvalRequired"] is True
    assert "blocked" in decision["reason"].lower()


def test_robotics_status_reports_unconfigured_bridge(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("LIMA_MCP_URL", raising=False)
    monkeypatch.delenv("SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED", raising=False)
    response = client.get(
        f"{settings.API_V1_STR}/chat/robotics/status",
        headers=_chat_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["mcpUrlConfigured"] is False
    assert payload["teaser_only"] is True
    assert payload["previewOnly"] is True


def test_robotics_command_dry_run_does_not_need_bridge(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("LIMA_MCP_URL", raising=False)
    monkeypatch.delenv("SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED", raising=False)
    response = client.post(
        f"{settings.API_V1_STR}/chat/robotics/command",
        headers=_chat_headers(),
        json={
            "requested_action": "move forward 0.5 meters",
            "environment": "simulation",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["executed"] is False
    assert payload["blocked"] is True
    assert payload["preview_only"] is True
    assert payload["contract"]["mcp_tool_name"] == "relative_move"
    assert payload["contract"]["risk_level"] == "blocked"
    assert payload["contract"]["guardian_decision"] == "preview_only"


def test_public_robo_tools_route_is_teaser_only(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("SPARKBOT_ROBO_TEASER_ONLY", raising=False)
    monkeypatch.setenv("LIMA_MCP_URL", "http://127.0.0.1:9990/mcp")
    monkeypatch.delenv("SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED", raising=False)
    response = client.get(
        f"{settings.API_V1_STR}/chat/robotics/tools",
        headers=_chat_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools"] == []
    assert payload["count"] == 0
    assert payload["teaser_only"] is True
    assert payload["bridge"]["privateBridgeEnabled"] is False


def test_public_robo_teaser_blocks_live_command_paths(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("SPARKBOT_ROBO_TEASER_ONLY", raising=False)
    monkeypatch.delenv("SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED", raising=False)
    response = client.post(
        f"{settings.API_V1_STR}/chat/robotics/command",
        headers=_chat_headers(),
        json={
            "requested_action": "move forward 0.5 meters",
            "environment": "simulation",
            "dry_run": False,
        },
    )

    assert response.status_code == 403
    assert "Robo Preview" in response.json()["detail"]


def test_public_robo_teaser_blocks_emergency_stop(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("SPARKBOT_ROBO_TEASER_ONLY", raising=False)
    monkeypatch.delenv("SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED", raising=False)
    response = client.post(
        f"{settings.API_V1_STR}/chat/robotics/emergency-stop",
        headers=_chat_headers(),
        json={"robot_id": "default"},
    )

    assert response.status_code == 403
    assert "Robo Preview" in response.json()["detail"]


def test_public_robo_service_stays_non_executing_without_private_gate(monkeypatch) -> None:
    monkeypatch.setenv("LIMA_MCP_URL", "http://127.0.0.1:9990/mcp")
    monkeypatch.delenv("SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED", raising=False)

    payload = asyncio.run(
        execute_robot_command(
            source_user="test",
            requested_action="move forward 0.5 meters",
            environment="simulation",
            dry_run=True,
        )
    )

    assert payload["executed"] is False
    assert payload["blocked"] is True
    assert payload["preview_only"] is True
    assert payload["bridge"]["privateBridgeEnabled"] is False
    assert asyncio.run(list_lima_tools()) == []
    try:
        asyncio.run(emergency_stop(source_user="test"))
    except LimaBridgeError as exc:
        assert "Robo Preview" in str(exc)
    else:
        raise AssertionError("emergency_stop should not run without the private Robo bridge gate")
