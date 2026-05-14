import pytest

from app.services.guardian.policy import decide_tool_use, simulate_tool_policy

# ── Personal mode (default, SPARKBOT_GUARDIAN_POLICY_ENABLED unset / false) ──

def test_security_off_allows_reads_and_confirms_high_risk_tools_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Computer Control allows routine work while high-risk writes still confirm."""
    monkeypatch.delenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", raising=False)
    read_decision = decide_tool_use("server_read_command", {}, room_execution_allowed=False)
    assert read_decision.action == "allow"

    for tool in ("browser_click", "gmail_send", "slack_send_message", "server_manage_service"):
        decision = decide_tool_use(tool, {}, room_execution_allowed=True)
        assert decision.action == "confirm", f"{tool} should still confirm when Computer Control is on"


def test_custom_security_guardrail_denies_matching_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_CUSTOM_GUARDRAILS", '["tool:gmail_send"]')

    decision = decide_tool_use("gmail_send", {"to": "person@example.com"}, room_execution_allowed=True)

    assert decision.action == "deny"
    assert "Custom Security guardrail" in decision.reason


def test_custom_security_guardrail_ignored_when_security_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "false")
    monkeypatch.setenv("SPARKBOT_CUSTOM_GUARDRAILS", '["tool:gmail_send"]')

    decision = decide_tool_use("gmail_send", {"to": "person@example.com"}, room_execution_allowed=True)

    assert decision.action == "confirm"


def test_unknown_tools_stay_denied_when_security_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "false")

    decision = decide_tool_use("not_a_real_tool", {}, room_execution_allowed=False)

    assert decision.action == "deny"


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


def test_breakglass_bypasses_execution_gate_for_gated_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Active break-glass session must allow gated read commands.

    Regression for the v1.6.73 bug where the requires_execution_gate branch
    short-circuited before the is_privileged check, so server_read_command,
    ssh_read_command, and other gated tools stayed locked even with break-
    glass active. The user's reported symptom: "Live diagnostics are
    policy-blocked in this environment; all PowerShell checks were rejected"
    when running a self-diagnostic with break-glass on.
    """
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "server_read_command",
        {"command": "service_status", "service": "self"},
        room_execution_allowed=False,
        is_operator=True,
        is_privileged=True,
    )
    assert decision.action == "allow"
    assert "break-glass" in decision.reason.lower()


def test_breakglass_bypasses_gate_for_other_gated_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same behaviour applies to every requires_execution_gate=True tool."""
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    for tool in ("ssh_read_command", "server_manage_service", "browser_click"):
        decision = decide_tool_use(
            tool,
            {"command": "ls"} if "ssh" in tool or "server" in tool else {"session_id": "abc", "target": "x"},
            room_execution_allowed=False,
            is_operator=True,
            is_privileged=True,
        )
        assert decision.action == "allow", f"{tool} should be allowed with break-glass active"


def test_inactive_breakglass_still_prompts_for_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an active break-glass session the existing prompt path remains."""
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "server_read_command",
        {"command": "service_status"},
        room_execution_allowed=False,
        is_operator=True,
        is_privileged=False,
    )
    assert decision.action == "privileged"
    assert "/breakglass" in decision.reason


def test_non_operator_without_breakglass_still_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    decision = decide_tool_use(
        "server_read_command",
        {"command": "service_status"},
        room_execution_allowed=False,
        is_operator=False,
        is_privileged=False,
    )
    assert decision.action == "deny"


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
