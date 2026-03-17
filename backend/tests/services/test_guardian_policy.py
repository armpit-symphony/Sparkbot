import pytest
from app.services.guardian.policy import decide_tool_use


# ── Personal mode (default, SPARKBOT_GUARDIAN_POLICY_ENABLED unset / false) ──

def test_personal_mode_allows_everything_by_default() -> None:
    """In personal mode all tools execute freely — no gates, no confirms."""
    for tool in ("browser_click", "gmail_send", "server_read_command", "slack_send_message"):
        decision = decide_tool_use(tool, {}, room_execution_allowed=False)
        assert decision.action == "allow", f"{tool} should be allowed in personal mode"


# ── Office mode (SPARKBOT_GUARDIAN_POLICY_ENABLED=true) ──

def test_policy_denies_execution_when_room_gate_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "server_read_command",
        {"command": "memory"},
        room_execution_allowed=False,
    )
    assert decision.action == "deny"
    assert "Execution is disabled" in decision.reason


def test_policy_treats_service_status_as_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "server_manage_service",
        {"action": "status", "service": "sparkbot-v2"},
        room_execution_allowed=False,
    )
    assert decision.action == "allow"
    assert decision.scope == "read"


def test_policy_allows_browser_open_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "browser_open",
        {"url": "https://example.com"},
    )
    assert decision.action == "allow"
    assert decision.scope == "read"


def test_policy_requires_confirmation_for_browser_click(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "browser_click",
        {"session_id": "abc123", "target": "Sign up"},
    )
    assert decision.action == "confirm"
    assert decision.scope == "write"
