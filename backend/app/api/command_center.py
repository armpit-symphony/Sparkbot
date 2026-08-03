from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.core.command_center import (
    CommandCenterAction,
    CommandCenterAuditEvent,
    command_center_safety_engine,
)

router = APIRouter(prefix="/operator")


class CommandCenterActionPayload(BaseModel):
    action_id: str
    action_name: str
    action_class: str
    feature: str
    tenant_id: str = "default"
    user_id: str = "default"
    operator_confirmation: bool = False
    policy_token: str | None = None
    break_glass: bool = False
    connector: str | None = None
    simulate_fault: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_action(self) -> CommandCenterAction:
        return CommandCenterAction(**self.model_dump())


def _require_operator_token(token: str | None = Header(default=None, alias="x-policy-token")) -> None:
    if token != command_center_safety_engine.policy_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid operator policy token",
        )


def _as_payload(event: CommandCenterAuditEvent) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "timestamp": event.timestamp,
        "tenant_id": event.tenant_id,
        "user_id": event.user_id,
        "action_id": event.action_id,
        "action_name": event.action_name,
        "action_class": event.action_class,
        "feature": event.feature,
        "decision_code": event.decision_code,
        "message": event.message,
        "requires_confirmation": event.requires_confirmation,
        "break_glass": event.break_glass,
        "policy_health": event.policy_health,
        "queue_depth": event.queue_depth,
        "chain_hash": event.chain_hash,
    }


def _decision_response(decision) -> JSONResponse:
    return JSONResponse(
        status_code=decision.http_status,
        content={
            "decision": decision.code,
            "allowed": decision.allowed,
            "requires_confirmation": decision.requires_confirmation,
            "message": decision.message,
            "decision_id": decision.decision_id,
        },
    )


@router.get("/command-center/state", dependencies=[Depends(_require_operator_token)])
def command_center_state() -> dict[str, Any]:
    return command_center_safety_engine.dump_state()


@router.get("/command-center/audit", dependencies=[Depends(_require_operator_token)])
def command_center_audit(limit: int = 100, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    events = command_center_safety_engine.get_audit_events(
        tenant_id=tenant_id,
        user_id=user_id,
        limit=limit,
    )
    return {"events": [_as_payload(event) for event in events], "count": len(events)}


@router.post("/command-center/actions")
def run_command_center_action(payload: CommandCenterActionPayload = Body(...)) -> JSONResponse:
    decision = command_center_safety_engine.evaluate_action(payload.to_action())
    return _decision_response(decision)


@router.post("/command-center/features", dependencies=[Depends(_require_operator_token)])
@router.patch("/command-center/features", dependencies=[Depends(_require_operator_token)])
def set_feature_flags(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    for feature_name, enabled in payload.items():
        if feature_name not in command_center_safety_engine.feature_flags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown feature '{feature_name}'",
            )
        if not isinstance(enabled, bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"feature value for '{feature_name}' must be boolean",
            )
        command_center_safety_engine.set_feature_flag(feature_name, enabled)
    return command_center_safety_engine.dump_state()


@router.post("/command-center/safe-mode", dependencies=[Depends(_require_operator_token)])
def set_safe_mode(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    safe_mode = payload.get("safe_mode")
    if not isinstance(safe_mode, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="safe_mode must be a boolean",
        )
    command_center_safety_engine.safe_mode = safe_mode
    return command_center_safety_engine.dump_state()


@router.post("/command-center/emergency-stop", dependencies=[Depends(_require_operator_token)])
def set_emergency_stop(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="enabled must be a boolean",
        )
    command_center_safety_engine.set_emergency_stop(enabled)
    return {"enabled": command_center_safety_engine.global_kill_switch}


@router.post("/command-center/rollback", dependencies=[Depends(_require_operator_token)])
def set_rollback_mode(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="enabled must be a boolean",
        )
    command_center_safety_engine.set_rollback_mode(enabled)
    return command_center_safety_engine.dump_state()


@router.post("/command-center/policy-health", dependencies=[Depends(_require_operator_token)])
def set_policy_health(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    status = payload.get("status")
    if status not in {"healthy", "degraded", "down"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be healthy, degraded, or down",
        )
    command_center_safety_engine.set_policy_health(status)
    return {"policy_health": command_center_safety_engine.policy_health}


@router.post("/command-center/connectors", dependencies=[Depends(_require_operator_token)])
def set_connector_state(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    connector = payload.get("connector")
    allowed = payload.get("allowed")
    if not isinstance(connector, str) or not connector.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connector must be a non-empty string",
        )
    if not isinstance(allowed, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="allowed must be boolean",
        )
    command_center_safety_engine.configure_connector_policy(connector.strip(), allowed=allowed)
    return command_center_safety_engine.dump_state()


@router.post("/command-center/limits", dependencies=[Depends(_require_operator_token)])
def set_limits(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    command_center_safety_engine.set_limits(
        tenant_rate_limit_per_minute=_extract_positive_int(payload, "tenant_rate_limit_per_minute"),
        tenant_anomaly_cap_per_minute=_extract_positive_int(payload, "tenant_anomaly_cap_per_minute"),
        queue_backlog_limit=_extract_positive_int(payload, "queue_backlog_limit"),
    )
    return command_center_safety_engine.dump_state()


def _extract_positive_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{key} must be a positive integer",
        )
    return value
