import pytest

from app.services.guardian.policy import decide_tool_use, simulate_tool_policy

# ── Personal mode (default, SPARKBOT_GUARDIAN_POLICY_ENABLED unset / false) ──

def test_computer_control_on_allows_reads_and_confirms_high_risk_tools_by_default() -> None:
    """Computer Control allows routine work while high-risk writes still confirm."""
    read_decision = decide_tool_use("server_read_command", {}, room_execution_allowed=True)
    assert read_decision.action == "allow"

    for tool in ("browser_click", "gmail_send", "slack_send_message"):
        decision = decide_tool_use(tool, {}, room_execution_allowed=True)
        assert decision.action == "confirm", f"{tool} should still confirm when Computer Control is on"


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


def test_policy_simulator_returns_structured_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    payload = simulate_tool_policy(
        "gmail_send",
        {"to": "person@example.com", "subject": "Update"},
        room_execution_allowed=False,
        is_operator=True,
    )
    assert payload["simulation_only"] is True
    assert payload["tool_args_keys"] == ["subject", "to"]
    assert "tool_args" not in payload
    assert payload["classification"]["scope"] == "write"
    assert payload["classification"]["high_risk"] is True
    assert payload["decision"]["action"] == "privileged"
    assert "Computer Control is off" in payload["decision"]["reason"]


def test_policy_simulator_never_executes_unknown_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    payload = simulate_tool_policy("made_up_tool", {}, room_execution_allowed=False)
    assert payload["simulation_only"] is True
    assert payload["classification"]["default_action"] == "deny"
    assert payload["decision"]["action"] == "deny"
