from __future__ import annotations

import importlib.metadata
import json
import socket
import threading
from typing import Any

import pytest
from lima.runtime import run_governed_request

from app.services.lima_decision_preview import (
    PUBLIC_PREVIEW_NOTE,
    preview_lima_decision,
)

LIMA_VERSION = "0.1.0rc1"
LIMA_COMMIT = "4e7c648349f0a5a19694ac5f0c57b5cb14dc2b17"


def _request(
    request_id: str,
    requested_action: str,
    action_category: str,
    tool_name: str,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "normalized_request": {"message": requested_action},
        "requested_action": requested_action,
        "action_category": action_category,
        "tool_name": tool_name,
        "evidence_refs": [f"evidence://sparkbot/lima-rc1/{request_id}"],
    }


def test_installed_lima_rc1_uses_exact_commit_and_public_api() -> None:
    distribution = importlib.metadata.distribution("lima-runtime")
    assert distribution.version == LIMA_VERSION
    assert callable(run_governed_request)
    assert distribution.requires is None

    direct_url_text = distribution.read_text("direct_url.json")
    assert direct_url_text is not None
    direct_url = json.loads(direct_url_text)
    assert direct_url["url"] == ("https://github.com/armpit-symphony/LIMA-AI-OS.git")
    assert direct_url["vcs_info"]["commit_id"] == LIMA_COMMIT
    assert direct_url["vcs_info"]["requested_revision"] == LIMA_COMMIT


@pytest.mark.parametrize(
    ("preview_request", "expected_status"),
    [
        (
            _request(
                "sparkbot-rc1-safe",
                "preview status",
                "informational",
                "sparkbot_decision_preview",
            ),
            "allowed_dry_run",
        ),
        (
            _request(
                "sparkbot-rc1-write",
                "send external message",
                "external_write",
                "send_email",
            ),
            "confirm_required",
        ),
        (
            _request(
                "sparkbot-rc1-shell",
                "run shell command",
                "shell",
                "terminal_send",
            ),
            "denied",
        ),
        (
            _request(
                "sparkbot-rc1-credential",
                "reveal credential",
                "credential_access",
                "vault_reveal",
            ),
            "privileged_required",
        ),
        (
            _request(
                "sparkbot-rc1-unknown",
                "perform unknown action",
                "unknown",
                "unknown_sparkbot_action",
            ),
            "denied",
        ),
    ],
)
def test_real_lima_rc1_preview_is_non_executing(
    monkeypatch: pytest.MonkeyPatch,
    preview_request: dict[str, Any],
    expected_status: str,
) -> None:
    counters = {"network": 0, "background": 0}

    def block_network(*_args: object, **_kwargs: object) -> None:
        counters["network"] += 1
        raise AssertionError("LIMA preview attempted network access")

    def block_thread(
        _self: threading.Thread, *_args: object, **_kwargs: object
    ) -> None:
        counters["background"] += 1
        raise AssertionError("LIMA preview attempted a background job")

    monkeypatch.setattr(socket.socket, "connect", block_network)
    monkeypatch.setattr(socket.socket, "connect_ex", block_network)
    monkeypatch.setattr(socket, "create_connection", block_network)
    monkeypatch.setattr(socket, "getaddrinfo", block_network)
    monkeypatch.setattr(threading.Thread, "start", block_thread)

    payload = preview_lima_decision(preview_request)

    assert payload["status"] == "preview"
    assert payload["lima_available"] is True
    assert payload["decision_status"] == expected_status
    assert payload["runtime_authority_blocked"] is True
    assert payload["executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False
    assert PUBLIC_PREVIEW_NOTE in payload["notes"]
    assert counters == {"network": 0, "background": 0}


def test_real_lima_rc1_malformed_request_fails_closed() -> None:
    payload = preview_lima_decision(
        {
            "request_id": "sparkbot-rc1-malformed",
            "requested_action": "missing normalized request",
            "action_category": "unknown",
        }
    )

    assert payload["status"] == "invalid"
    assert payload["lima_available"] is False
    assert payload["decision_status"] == "invalid_request"
    assert payload["runtime_authority_blocked"] is True
    assert payload["executable"] is False
    assert payload["execution_allowed"] is False
    assert payload["side_effects_allowed"] is False
