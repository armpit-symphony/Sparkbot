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
