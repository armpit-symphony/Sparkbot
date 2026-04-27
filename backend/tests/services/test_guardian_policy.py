import pytest

from app.services.guardian.policy import decide_tool_use

# ── Personal mode (default, SPARKBOT_GUARDIAN_POLICY_ENABLED unset / false) ──

def test_computer_control_on_allows_high_risk_tools_by_default() -> None:
    """In personal mode all tools execute freely — no gates, no confirms."""
    for tool in ("browser_click", "gmail_send", "server_read_command", "slack_send_message"):
        decision = decide_tool_use(tool, {}, room_execution_allowed=True)
        assert decision.action == "allow", f"{tool} should be allowed when Computer Control is on"


# ── Office mode (SPARKBOT_GUARDIAN_POLICY_ENABLED=true) ──

def test_policy_requires_pin_when_computer_control_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "server_read_command",
        {"command": "memory"},
        room_execution_allowed=False,
        is_operator=True,
    )
    assert decision.action == "privileged"
    assert "Computer Control is off" in decision.reason


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
        room_execution_allowed=False,
        is_operator=True,
    )
    assert decision.action == "privileged"
    assert decision.scope == "write"


def test_policy_confirms_write_like_shell_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "shell_run",
        {"command": "git add backend/app/services/guardian/improvement.py && git commit -m update"},
    )
    assert decision.action == "confirm"
    assert decision.scope == "execute"


def test_policy_allows_read_only_shell_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "shell_run",
        {"command": "git status -sb"},
    )
    assert decision.action == "allow"
    assert decision.scope == "read"
