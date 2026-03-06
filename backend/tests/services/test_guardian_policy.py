from app.services.guardian.policy import decide_tool_use


def test_policy_denies_execution_when_room_gate_is_off() -> None:
    decision = decide_tool_use(
        "server_read_command",
        {"command": "memory"},
        room_execution_allowed=False,
    )
    assert decision.action == "deny"
    assert "Execution is disabled" in decision.reason


def test_policy_treats_service_status_as_read_only() -> None:
    decision = decide_tool_use(
        "server_manage_service",
        {"action": "status", "service": "sparkbot-v2"},
        room_execution_allowed=False,
    )
    assert decision.action == "allow"
    assert decision.scope == "read"
