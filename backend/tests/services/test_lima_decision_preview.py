from __future__ import annotations

import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import lima_decision_preview as preview


@dataclass(frozen=True)
class FakeDecision:
    status: str
    allowed: bool
    requires_approval: bool
    decision_id: str = "decision:test"
    source_policy: str = "guardian_core.policy"
    executable: bool = False
    execution_allowed: bool = False
    side_effects_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "status": self.status,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "source_policy": self.source_policy,
            "executable": self.executable,
            "execution_allowed": self.execution_allowed,
            "side_effects_allowed": self.side_effects_allowed,
        }


def _request(**overrides: Any) -> dict[str, Any]:
    payload = {
        "request_id": "sparkbot-preview-1",
        "normalized_request": {"message": "show status"},
        "requested_action": "preview_status",
        "action_category": "informational",
        "tool_name": "sparkbot_decision_preview",
        "evidence_refs": ["evidence://sparkbot/preview/1"],
    }
    payload.update(overrides)
    return payload


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch, decision: FakeDecision, calls: list[dict[str, Any]]
) -> None:
    def fake_runner(request: dict[str, Any]) -> FakeDecision:
        calls.append(request)
        return decision

    monkeypatch.setattr(preview, "_load_lima_runner", lambda: fake_runner)


def test_lima_unavailable_path_fails_closed_without_leaking_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "No module named 'lima' at C:/private/runtime/site-packages"

    def unavailable() -> object:
        raise ModuleNotFoundError(private_detail)

    monkeypatch.setattr(preview, "_load_lima_runner", unavailable)

    with caplog.at_level(logging.ERROR, logger=preview.__name__):
        payload = preview.preview_lima_decision(_request())

    assert payload["status"] == "unavailable"
    assert payload["lima_available"] is False
    assert payload["decision_status"] == "unavailable"
    assert payload["runtime_authority_blocked"] is True
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False
    assert preview.PUBLIC_PREVIEW_NOTE in payload["notes"]
    assert private_detail not in repr(payload)
    assert "Import error:" not in repr(payload)
    assert "LIMA decision preview runtime import failed" in caplog.text
    assert private_detail in caplog.text


def test_lima_available_path_returns_decision_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patch_runner(
        monkeypatch,
        FakeDecision(status="allowed_dry_run", allowed=True, requires_approval=False),
        calls,
    )

    payload = preview.preview_lima_decision(_request())

    assert payload["service"] == "lima_decision_preview"
    assert payload["mode"] == "preview"
    assert payload["status"] == "preview"
    assert payload["lima_available"] is True
    assert payload["decision_status"] == "allowed_dry_run"
    assert payload["decision_id"] == "decision:test"
    assert payload["source_policy"] == "guardian_core.policy"
    assert payload["allowed"] is True
    assert payload["requires_approval"] is False
    assert calls[0]["consumer"] == "sparkbot"
    assert calls[0]["surface"] == "sparkbot_public_preview"
    assert calls[0]["actor_id"] == "local_operator"
    assert calls[0]["trust_context"] == {"public_preview": True, "dry_run_only": True}


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (
            FakeDecision(
                status="allowed_dry_run", allowed=True, requires_approval=False
            ),
            "allowed_dry_run",
        ),
        (
            FakeDecision(
                status="confirm_required", allowed=False, requires_approval=True
            ),
            "confirm_required",
        ),
        (
            FakeDecision(status="denied", allowed=False, requires_approval=False),
            "denied",
        ),
    ],
)
def test_decision_preview_never_exposes_execution_flags(
    monkeypatch: pytest.MonkeyPatch,
    decision: FakeDecision,
    expected_status: str,
) -> None:
    calls: list[dict[str, Any]] = []
    _patch_runner(monkeypatch, decision, calls)

    payload = preview.preview_lima_decision(_request())

    assert payload["decision_status"] == expected_status
    assert payload["runtime_authority_blocked"] is True
    assert payload["executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False


def test_client_authority_claims_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    _patch_runner(
        monkeypatch,
        FakeDecision(
            status="allowed_dry_run",
            allowed=True,
            requires_approval=False,
            executable=True,
            execution_allowed=True,
            side_effects_allowed=True,
        ),
        calls,
    )

    payload = preview.preview_lima_decision(
        _request(
            executable=True,
            execution_allowed=True,
            side_effects_allowed=True,
            approval_token="claimed-token",
            guardian_enforcement="active",
            credential_access=True,
            raw_prompt_authority=True,
            consumer="attacker",
            actor_id="attacker",
            trust_context={"dry_run_only": False, "public_preview": False},
            normalized_request={
                "message": "show status",
                "raw_prompt_authority": True,
                "guardian_enforcement": "active",
            },
        )
    )

    assert payload["runtime_authority_blocked"] is True
    assert payload["executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False
    assert any("authority claims ignored" in note for note in payload["notes"])
    assert calls[0]["consumer"] == "sparkbot"
    assert calls[0]["actor_id"] == "local_operator"
    assert calls[0]["trust_context"] == {"public_preview": True, "dry_run_only": True}
    assert (
        calls[0]["normalized_request"]["raw_prompt_authority"]
        == "ignored_public_preview_claim"
    )
    assert (
        calls[0]["normalized_request"]["guardian_enforcement"]
        == "ignored_public_preview_claim"
    )


def test_client_classification_is_non_authoritative_and_cannot_enable_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patch_runner(
        monkeypatch,
        FakeDecision(status="allowed_dry_run", allowed=True, requires_approval=False),
        calls,
    )

    payload = preview.preview_lima_decision(
        _request(
            normalized_request={"message": "send an external email"},
            requested_action="show status",
            action_category="informational",
            tool_name="sparkbot_decision_preview",
        )
    )

    assert payload["classification_authority"] == ("client_supplied_non_authoritative")
    assert payload["runtime_authority_blocked"] is True
    assert payload["executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False
    assert calls[0]["requested_action"] == "show status"
    assert calls[0]["action_category"] == "informational"
    assert calls[0]["tool_name"] == "sparkbot_decision_preview"


def test_status_capabilities_do_not_claim_guardian_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preview, "_load_lima_runner", lambda: (lambda request: request))

    payload = preview.lima_decision_preview_status()

    assert payload["capabilities"] == {
        "lima_decision_preview": "preview",
        "guardian_enforcement": "not-implemented",
    }
    assert payload["runtime_authority_blocked"] is True
    assert payload["execution_allowed"] is False
    assert preview.PUBLIC_PREVIEW_NOTE in payload["notes"]


def test_non_object_preview_request_is_rejected() -> None:
    payload = preview.preview_lima_decision(["not", "an", "object"])  # type: ignore[arg-type]

    assert payload["status"] == "invalid"
    assert payload["decision_status"] == "invalid_request"
    assert payload["runtime_authority_blocked"] is True
    assert "Preview request must be a JSON object." in payload["notes"]


def test_missing_normalized_request_is_rejected() -> None:
    payload = preview.preview_lima_decision(_request(normalized_request=None))

    assert payload["status"] == "invalid"
    assert payload["decision_status"] == "invalid_request"
    assert "normalized_request is required" in payload["notes"]


def test_lima_runtime_error_fails_closed_without_leaking_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "failed request sparkbot-preview-1 in C:/private/runtime.py"

    def failing_runner(_request: dict[str, Any]) -> None:
        raise RuntimeError(private_detail)

    monkeypatch.setattr(preview, "_load_lima_runner", lambda: failing_runner)

    with caplog.at_level(logging.ERROR, logger=preview.__name__):
        payload = preview.preview_lima_decision(_request())

    assert payload["status"] == "unavailable"
    assert payload["lima_available"] is False
    assert payload["execution_allowed"] is False
    assert private_detail not in repr(payload)
    assert "Runtime error:" not in repr(payload)
    assert "LIMA decision preview runtime call failed" in caplog.text
    assert private_detail in caplog.text


def test_unavailable_status_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable() -> object:
        raise ModuleNotFoundError("No module named 'lima'")

    monkeypatch.setattr(preview, "_load_lima_runner", unavailable)

    payload = preview.lima_decision_preview_status()

    assert payload["status"] == "unavailable"
    assert payload["lima_available"] is False
    assert payload["runtime_authority_blocked"] is True


def test_preview_normalizes_optional_public_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _patch_runner(
        monkeypatch,
        FakeDecision(status="allowed_dry_run", allowed=True, requires_approval=False),
        calls,
    )

    payload = preview.preview_lima_decision(
        _request(
            action_category="write",
            tool_name=42,
            evidence_refs=" evidence://single ",
            normalized_request={"items": [{"message": "status"}], "flags": ("public",)},
        )
    )

    assert payload["status"] == "preview"
    assert calls[0]["tool_name"] is None
    assert calls[0]["evidence_refs"] == ("evidence://single",)
    assert calls[0]["normalized_request"] == {
        "items": [{"message": "status"}],
        "flags": ("public",),
    }


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ({"status": "mapping"}, "mapping"),
        (SimpleNamespace(status="object"), "object"),
        (object(), "unknown"),
    ],
)
def test_preview_accepts_supported_decision_shapes(
    monkeypatch: pytest.MonkeyPatch,
    decision: object,
    expected_status: str,
) -> None:
    monkeypatch.setattr(preview, "_load_lima_runner", lambda: lambda request: decision)

    payload = preview.preview_lima_decision(_request())

    assert payload["decision_status"] == expected_status
    assert payload["execution_allowed"] is False
