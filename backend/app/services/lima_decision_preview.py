"""Public-safe LIMA decision preview service.

This module optionally imports LIMA's governed dry-run runtime and converts a
small Sparkbot preview request into a LIMA ``GovernedRequest`` mapping. It is a
preview surface only: it does not enforce Guardian policy, execute tools, route
models, call providers, call connectors, send messages, mutate files, schedule
jobs, read credentials, or touch robotics/IoT/physical-world paths.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

PUBLIC_PREVIEW_NOTE = (
    "LIMA decision preview is non-executing and does not represent active Guardian enforcement."
)
SERVICE_NAME = "lima_decision_preview"
MODE = "preview"

_ALLOWED_REQUEST_FIELDS = {
    "request_id",
    "normalized_request",
    "requested_action",
    "action_category",
    "tool_name",
    "evidence_refs",
}
_FORBIDDEN_AUTHORITY_KEYS = {
    "approval",
    "approval_token",
    "approved",
    "approver",
    "breakglass",
    "connector_call",
    "connector_calls",
    "credential",
    "credential_access",
    "credentials",
    "enforcement",
    "executable",
    "execution",
    "execution_allowed",
    "external_send",
    "file_mutation_authority",
    "guardian_enforcement",
    "pin",
    "provider_call",
    "provider_credentials",
    "raw_prompt_authority",
    "scheduler",
    "secret",
    "side_effects_allowed",
    "tool_call_authority",
}


def preview_lima_decision(request: dict[str, Any]) -> dict[str, Any]:
    """Return a LIMA governed decision preview or a fail-closed unavailable payload."""

    if not isinstance(request, dict):
        return _base_response(
            status="invalid",
            lima_available=False,
            decision_status="invalid_request",
            notes=["Preview request must be a JSON object."],
        )

    forbidden_claims = _find_forbidden_claims(request)
    try:
        lima_request = _build_lima_request(request)
    except ValueError as exc:
        return _base_response(
            status="invalid",
            lima_available=False,
            decision_status="invalid_request",
            notes=[str(exc), _authority_note(forbidden_claims)],
        )

    try:
        run_governed_request = _load_lima_runner()
    except Exception as exc:
        return _base_response(
            status="unavailable",
            lima_available=False,
            decision_status="unavailable",
            notes=[
                "Local LIMA runtime import is unavailable; preview failed closed.",
                f"Import error: {exc}",
                _authority_note(forbidden_claims),
            ],
        )

    try:
        decision = run_governed_request(lima_request)
    except Exception as exc:
        return _base_response(
            status="unavailable",
            lima_available=False,
            decision_status="unavailable",
            notes=[
                "Local LIMA runtime returned an error; preview failed closed.",
                f"Runtime error: {exc}",
                _authority_note(forbidden_claims),
            ],
        )

    decision_payload = _decision_to_mapping(decision)
    return _base_response(
        status="preview",
        lima_available=True,
        decision_status=str(decision_payload.get("status") or "unknown"),
        decision_id=str(decision_payload.get("decision_id") or ""),
        source_policy=str(decision_payload.get("source_policy") or ""),
        requires_approval=bool(decision_payload.get("requires_approval", False)),
        allowed=bool(decision_payload.get("allowed", False)),
        notes=[_authority_note(forbidden_claims)],
    )


def lima_decision_preview_status() -> dict[str, Any]:
    """Return public-safe availability and capability status for the preview seam."""

    try:
        _load_lima_runner()
        available = True
        status = "available"
    except Exception:
        available = False
        status = "unavailable"
    payload = _base_response(
        status=status,
        lima_available=available,
        decision_status=status,
        notes=[],
    )
    payload["capabilities"] = {
        "lima_decision_preview": "preview",
        "guardian_enforcement": "not-implemented",
    }
    return payload


def _load_lima_runner() -> Callable[[dict[str, Any]], Any]:
    from lima.runtime import run_governed_request

    return run_governed_request


def _build_lima_request(request: Mapping[str, Any]) -> dict[str, Any]:
    request_id = _required_text(request.get("request_id"), "request_id")
    normalized_request = request.get("normalized_request")
    if normalized_request is None:
        raise ValueError("normalized_request is required")
    requested_action = _required_text(request.get("requested_action"), "requested_action")
    action_category = _required_text(request.get("action_category"), "action_category")
    tool_name = _optional_text(request.get("tool_name")) or _default_tool_name(action_category)
    evidence_refs = _evidence_refs(request.get("evidence_refs"))

    return {
        "request_id": request_id,
        "consumer": "sparkbot",
        "surface": "sparkbot_public_preview",
        "actor_id": "local_operator",
        "normalized_request": _sanitize_public_value(normalized_request),
        "requested_action": requested_action,
        "action_category": action_category,
        "tool_name": tool_name,
        "tool_args": {},
        "trust_context": {
            "public_preview": True,
            "dry_run_only": True,
        },
        "evidence_refs": evidence_refs,
    }


def _base_response(
    *,
    status: str,
    lima_available: bool,
    decision_status: str,
    decision_id: str = "",
    source_policy: str = "",
    requires_approval: bool = False,
    allowed: bool = False,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    merged_notes = [PUBLIC_PREVIEW_NOTE]
    merged_notes.extend(note for note in notes if note)
    return {
        "service": SERVICE_NAME,
        "mode": MODE,
        "status": status,
        "lima_available": lima_available,
        "decision_status": decision_status,
        "decision_id": decision_id,
        "source_policy": source_policy,
        "requires_approval": requires_approval,
        "allowed": allowed,
        "runtime_authority_blocked": True,
        "executable": False,
        "execution_allowed": False,
        "side_effects_allowed": False,
        "notes": merged_notes,
    }


def _decision_to_mapping(decision: Any) -> dict[str, Any]:
    if hasattr(decision, "to_dict"):
        mapped = decision.to_dict()
        return dict(mapped) if isinstance(mapped, Mapping) else {}
    if isinstance(decision, Mapping):
        return dict(decision)
    if hasattr(decision, "__dict__"):
        return dict(decision.__dict__)
    return {}


def _default_tool_name(action_category: str) -> str | None:
    category = action_category.strip().lower()
    if category in {"read", "status", "informational", "planning", "drafting", "preview"}:
        return "sparkbot_decision_preview"
    return None


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _evidence_refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, Sequence):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _find_forbidden_claims(value: Any) -> tuple[str, ...]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                key_text = str(key).strip().lower()
                if key_text in _FORBIDDEN_AUTHORITY_KEYS and key_text not in _ALLOWED_REQUEST_FIELDS:
                    found.add(key_text)
                walk(child)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for child in node:
                walk(child)

    walk(value)
    return tuple(sorted(found))


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if key_text.strip().lower() in _FORBIDDEN_AUTHORITY_KEYS:
                sanitized[key_text] = "ignored_public_preview_claim"
            else:
                sanitized[key_text] = _sanitize_public_value(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_public_value(item) for item in value)
    return value


def _authority_note(forbidden_claims: Sequence[str]) -> str:
    if not forbidden_claims:
        return "Client-supplied authority fields are not accepted by this preview surface."
    return "Client-supplied authority claims ignored: " + ", ".join(forbidden_claims)
