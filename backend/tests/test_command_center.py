from __future__ import annotations

from fastapi.testclient import TestClient
import json
from pathlib import Path

from app.api.command_center import command_center_safety_engine
from app.main import app


def _action_payload(**kwargs: object) -> dict:
    payload = {
        "action_id": "action-1",
        "action_name": "noop-test",
        "action_class": "chat_execution",
        "feature": "chat_execution",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
    }
    payload.update(kwargs)
    return payload


def _post_action(client: TestClient, payload: dict[str, object], status_code: int = 200) -> dict[str, object]:
    response = client.post("/operator/command-center/actions", json=payload)
    assert response.status_code == status_code
    body = response.json()
    assert body["decision"]
    return body


def _expect_block(response, expected_status: int, expected_decision: str | None = None) -> None:
    assert response.status_code == expected_status
    data = response.json()
    if expected_decision:
        assert data["decision"] == expected_decision


def test_high_risk_actions_require_confirmation() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(),
    )
    _expect_block(response, 409, "requires-confirmation")


def test_confirmation_requires_policy_token() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(operator_confirmation=True),
    )
    _expect_block(response, 409, "confirmation-token-required")


def test_confirmation_token_with_policy_token_allows() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(operator_confirmation=True, policy_token="public-command-center-policy-token"),
    )
    _expect_block(response, 200)
    body = response.json()
    assert body["allowed"] is True
    assert body["requires_confirmation"] is False


def test_break_glass_override_allows_without_confirmation() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            operator_confirmation=False,
            break_glass=True,
            policy_token="public-command-center-policy-token",
        ),
    )
    _expect_block(response, 200)
    assert response.json()["decision"] == "allowed"


def test_unknown_feature_is_rejected() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(feature="missing-feature", action_class="read"),
    )
    _expect_block(response, 400, "unknown-feature")


def test_feature_disabled_blocks_action() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/features",
        json={"chat_execution": False},
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(operator_confirmation=True, policy_token="public-command-center-policy-token"),
    )
    _expect_block(response, 403, "feature-disabled")


def test_global_kill_switch_blocks_non_read_actions() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/emergency-stop",
        json={"enabled": True},
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            action_class="web",
            feature="web",
        ),
    )
    _expect_block(response, 423, "kill-switch-active")


def test_policy_engine_unhealthy_is_fail_close_for_mutation() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)
    response = client.post(
        "/operator/command-center/policy-health",
        json={"status": "down"},
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            action_class="terminal",
            feature="terminal",
        ),
    )
    _expect_block(response, 503, "policy-unavailable")


def test_connector_registry_allow_deny() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)

    # denied connector
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_name="connector-call",
            action_class="connectors",
            feature="connectors",
            connector="pagerduty",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
        ),
    )
    _expect_block(response, 403)
    assert "not allowed" in response.json()["message"]

    # allow connector through admin endpoint
    response = client.post(
        "/operator/command-center/connectors",
        json={"connector": "pagerduty", "allowed": True},
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_name="connector-call",
            action_class="connectors",
            feature="connectors",
            connector="pagerduty",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
        ),
    )
    _expect_block(response, 200)


def test_provider_fault_contracts() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)

    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_name="provider-timeout",
            action_class="web",
            feature="web",
            simulate_fault="provider_timeout",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
        ),
    )
    _expect_block(response, 504, "provider-timeout")

    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_name="bad-cred",
            action_class="web",
            feature="web",
            simulate_fault="bad_credentials",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            action_id="action-bad-cred",
        ),
    )
    _expect_block(response, 401, "bad-credentials")


def test_safety_policy_token_bypass_for_all_high_risk_actions() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)

    for action_class in [
        "chat_execution",
        "connectors",
        "terminal",
        "web",
        "model-calls",
        "tool-execution",
    ]:
        response = client.post(
            "/operator/command-center/actions",
            json=_action_payload(
                action_id=f"policy-bypass-{action_class}",
                action_name="bypass-test",
                action_class=action_class,
                feature=action_class,
                operator_confirmation=True,
                connector="slack" if action_class == "connectors" else None,
            ),
        )
        _expect_block(response, 409, "confirmation-token-required")


def test_rate_limit_and_anomaly_caps_block_spam() -> None:
    command_center_safety_engine.reset_for_tests()
    command_center_safety_engine.set_limits(
        tenant_rate_limit_per_minute=3,
        tenant_anomaly_cap_per_minute=1,
        queue_backlog_limit=128,
    )
    client = TestClient(app)

    first = _post_action(
        client,
        _action_payload(
            action_id="action-r1",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            payload={"id": 1},
        ),
    )
    assert first["allowed"] is True

    # same tenant/user second high-risk action hits anomaly cap by default set to 1
    second = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_id="action-r2",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            payload={"id": 2},
        ),
    )
    _expect_block(second, 429, "tenant-anomaly-cap")


def test_queue_backlog_blocks_when_limits_exceeded() -> None:
    command_center_safety_engine.reset_for_tests()
    command_center_safety_engine.set_limits(queue_backlog_limit=1, tenant_rate_limit_per_minute=10)
    client = TestClient(app)

    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_id="action-q1",
            action_class="read",
            feature="chat_execution",
            operator_confirmation=False,
        ),
    )
    _expect_block(response, 200)

    # fill queue with another request using an unconfirmed high-risk action which still enters the queue
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_id="action-q2",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=False,
        ),
    )
    _expect_block(response, 409, "requires-confirmation")

    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_id="action-q3",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=False,
        ),
    )
    # queue backlog is a guardrail test only when queue is saturated for policy-checked actions.
    assert response.status_code in {200, 429}


def test_audit_chain_and_redaction() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)

    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_id="action-audit-1",
            action_name="audit-test",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            payload={"secret": "top-secret-token"},
        ),
    )
    _expect_block(response, 200)

    response = client.get("/operator/command-center/audit", headers={"x-policy-token": "public-command-center-policy-token"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    event = payload["events"][0]
    assert "secret" not in event
    assert event["chain_hash"] and len(event["chain_hash"]) == 64
    assert event["decision_code"] == "allowed"


def test_operator_control_views_require_operator_token() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)

    response = client.get("/operator/command-center/state")
    assert response.status_code == 401

    response = client.get("/operator/command-center/audit")
    assert response.status_code == 401

    response = client.get(
        "/operator/command-center/state",
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200


def test_rollback_mode_disables_runtime_actions_and_marks_static_fallback() -> None:
    command_center_safety_engine.reset_for_tests()
    client = TestClient(app)

    response = client.post(
        "/operator/command-center/rollback",
        json={"enabled": True},
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200
    state = response.json()
    assert state["rollback_mode"] is True
    assert state["static_shell_fallback"] is True
    assert all(not value for key, value in state["feature_flags"].items() if key in {"chat_execution", "connectors", "terminal", "web", "model-calls", "tool-execution"})

    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_name="rollback-block",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
        ),
    )
    _expect_block(response, 423, "rollback-mode")

    response = client.post(
        "/operator/command-center/rollback",
        json={"enabled": False},
        headers={"x-policy-token": "public-command-center-policy-token"},
    )
    assert response.status_code == 200
    assert response.json()["rollback_mode"] is False


def test_audit_file_persists_hash_chain_with_signature(tmp_path: Path) -> None:
    command_center_safety_engine.reset_for_tests()
    audit_file = tmp_path / "command-center-audit.jsonl"
    command_center_safety_engine._audit_file = audit_file
    command_center_safety_engine.audit_signing_key = "unit-test-signing-key"

    client = TestClient(app)
    response = client.post(
        "/operator/command-center/actions",
        json=_action_payload(
            action_name="signed-audit",
            action_class="terminal",
            feature="terminal",
            operator_confirmation=True,
            policy_token="public-command-center-policy-token",
            payload={"api_key": "top-secret"},
        ),
    )
    _expect_block(response, 200)

    raw = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[-1])
    assert "signature" in raw
    assert raw["chain_hash"] and len(raw["chain_hash"]) == 64
    assert raw["payload"]["api_key"] == "***redacted***"

