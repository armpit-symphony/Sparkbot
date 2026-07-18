from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services import lima_decision_preview as preview


@dataclass(frozen=True)
class FakeDecision:
    status: str = "allowed_dry_run"
    allowed: bool = True
    requires_approval: bool = False
    decision_id: str = "decision:endpoint"
    source_policy: str = "guardian_core.policy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "status": self.status,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "source_policy": self.source_policy,
            "executable": False,
            "execution_allowed": False,
            "side_effects_allowed": False,
        }


def test_lima_status_endpoint_returns_preview_only_language(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(preview, "_load_lima_runner", lambda: (lambda request: request))

    response = client.get(f"{settings.API_V1_STR}/lima/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "lima_decision_preview"
    assert payload["mode"] == "preview"
    assert payload["capabilities"]["lima_decision_preview"] == "preview"
    assert payload["capabilities"]["guardian_enforcement"] == "not-implemented"
    assert payload["public_copy"] == preview.PUBLIC_PREVIEW_NOTE
    assert preview.PUBLIC_PREVIEW_NOTE in payload["notes"]
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False


def test_lima_decision_preview_endpoint_returns_preview_only_decision(
    client: TestClient,
    monkeypatch,
) -> None:
    def fake_runner(request: dict[str, Any]) -> FakeDecision:
        assert request["consumer"] == "sparkbot"
        assert request["surface"] == "sparkbot_public_preview"
        return FakeDecision()

    monkeypatch.setattr(preview, "_load_lima_runner", lambda: fake_runner)

    response = client.post(
        f"{settings.API_V1_STR}/lima/decision-preview",
        json={
            "request_id": "endpoint-preview-1",
            "normalized_request": {"message": "preview status"},
            "requested_action": "preview_status",
            "action_category": "informational",
            "tool_name": "sparkbot_decision_preview",
            "guardian_enforcement": "active",
            "execution_allowed": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "preview"
    assert payload["lima_available"] is True
    assert payload["decision_status"] == "allowed_dry_run"
    assert payload["decision_id"] == "decision:endpoint"
    assert payload["source_policy"] == "guardian_core.policy"
    assert payload["public_copy"] == preview.PUBLIC_PREVIEW_NOTE
    assert preview.PUBLIC_PREVIEW_NOTE in payload["notes"]
    assert any("authority claims ignored" in note for note in payload["notes"])
    assert payload["runtime_authority_blocked"] is True
    assert payload["executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False
