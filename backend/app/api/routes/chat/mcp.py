from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import create_audit_log, get_chat_room_by_id, get_chat_room_member
from app.services.guardian import get_guardian_suite
from app.services.mcp_registry import build_mcp_explain_plan, get_mcp_registry
from app.services.mcp_runs import (
    approve_mcp_run,
    create_mcp_run,
    deny_mcp_run,
    get_mcp_run,
    list_mcp_runs,
    request_mcp_run_approval,
)

router = APIRouter(tags=["chat-mcp"])


class McpExplainPlanRequest(BaseModel):
    manifest_id: str = Field(..., min_length=1, max_length=120)
    tool_args: dict[str, Any] = Field(default_factory=dict)
    user_request: str = Field("", max_length=1000)
    room_id: str | None = Field(default=None, max_length=64)


class McpDenyRunRequest(BaseModel):
    reason: str = Field("", max_length=500)


def _resolve_room_scope(
    *,
    session: SessionDep,
    current_user: CurrentChatUser,
    room_id: str | None,
) -> tuple[uuid.UUID | None, bool | None]:
    if not room_id:
        return None, None
    try:
        room_uuid = uuid.UUID(room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room_id")
    room = get_chat_room_by_id(session, room_uuid)
    membership = get_chat_room_member(session, room_uuid, current_user.id)
    if not room or not membership:
        raise HTTPException(status_code=404, detail="Room not found")
    return room_uuid, bool(room.execution_allowed)


def _require_operator(current_user: CurrentChatUser) -> None:
    if not get_guardian_suite().auth.is_operator_identity(
        username=current_user.username,
        user_type=current_user.type,
    ):
        raise HTTPException(status_code=403, detail="MCP run approval requires Guardian operator access.")


def _audit_mcp_run_action(
    *,
    session: SessionDep,
    current_user: CurrentChatUser,
    action: str,
    run: dict[str, Any],
) -> None:
    room_uuid = None
    if run.get("roomId"):
        try:
            room_uuid = uuid.UUID(str(run.get("roomId")))
        except Exception:
            room_uuid = None
    create_audit_log(
        session,
        tool_name=f"mcp_run_{action}",
        tool_input=json.dumps(
            {
                "run_id": run["id"],
                "manifest_id": run["manifestId"],
                "policy_action": run["policyAction"],
            },
            sort_keys=True,
        ),
        tool_result=json.dumps(
            {
                "status": run["status"],
                "approval_id": run.get("approvalId"),
                "status_message": run.get("statusMessage"),
            },
            sort_keys=True,
        ),
        user_id=current_user.id,
        room_id=room_uuid,
        agent_name="mcp_registry",
    )


@router.get("/mcp/registry")
def mcp_registry(current_user: CurrentChatUser) -> dict[str, Any]:
    """Return the unified Sparkbot + LIMA MCP registry and live health metadata."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_mcp_registry()


@router.post("/mcp/explain-plan")
def mcp_explain_plan(
    body: McpExplainPlanRequest,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Return a no-execution policy and dry-run plan for an MCP registry tool."""
    room_uuid, room_execution_allowed = _resolve_room_scope(
        session=session,
        current_user=current_user,
        room_id=body.room_id,
    )

    guardian = get_guardian_suite()
    is_operator = guardian.auth.is_operator_identity(
        username=current_user.username,
        user_type=current_user.type,
    )
    is_privileged = bool(guardian.auth.is_operator_privileged(str(current_user.id)))
    try:
        plan = build_mcp_explain_plan(
            body.manifest_id,
            tool_args=body.tool_args,
            user_request=body.user_request,
            room_execution_allowed=room_execution_allowed,
            is_operator=is_operator,
            is_privileged=is_privileged,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown MCP manifest")

    run = create_mcp_run(
        user_id=str(current_user.id),
        room_id=str(room_uuid) if room_uuid else None,
        manifest_id=body.manifest_id,
        user_request=body.user_request,
        plan=plan,
    )
    plan = {
        **plan,
        "runId": run["id"],
        "runStatus": run["status"],
        "createdAt": run["createdAt"],
    }

    create_audit_log(
        session,
        tool_name="mcp_explain_plan",
        tool_input=json.dumps(
            {
                "run_id": run["id"],
                "manifest_id": body.manifest_id,
                "tool_args_keys": sorted(str(key) for key in body.tool_args.keys()),
                "room_id": body.room_id,
            },
            sort_keys=True,
        ),
        tool_result=json.dumps(
            {
                "policy_action": plan["policy"]["decision"]["action"],
                "approval_required": plan["approvalRequired"],
                "can_execute_now": plan["canExecuteNow"],
            },
            sort_keys=True,
        ),
        user_id=current_user.id,
        room_id=room_uuid,
        agent_name="mcp_registry",
    )
    return plan


@router.get("/mcp/runs")
def mcp_runs(
    current_user: CurrentChatUser,
    session: SessionDep,
    room_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Return recent durable MCP explain-plan/run records for the current user."""
    room_uuid, _room_execution_allowed = _resolve_room_scope(
        session=session,
        current_user=current_user,
        room_id=room_id,
    )
    runs = list_mcp_runs(
        user_id=str(current_user.id),
        room_id=str(room_uuid) if room_uuid else None,
        limit=limit,
    )
    return {"runs": runs, "count": len(runs)}


@router.get("/mcp/runs/{run_id}")
def mcp_run_detail(run_id: str, current_user: CurrentChatUser) -> dict[str, Any]:
    """Return one MCP run record and its persisted explain-plan payload."""
    run = get_mcp_run(run_id, user_id=str(current_user.id))
    if not run:
        raise HTTPException(status_code=404, detail="MCP run not found")
    return run


@router.post("/mcp/runs/{run_id}/request-approval")
def mcp_run_request_approval(
    run_id: str,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Mark an MCP run as awaiting approval without executing anything."""
    try:
        run = request_mcp_run_approval(run_id, user_id=str(current_user.id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not run:
        raise HTTPException(status_code=404, detail="MCP run not found")
    _audit_mcp_run_action(
        session=session,
        current_user=current_user,
        action="approval_requested",
        run=run,
    )
    return run


@router.post("/mcp/runs/{run_id}/approve")
def mcp_run_approve(
    run_id: str,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Approve an MCP run for future execution handoff; no tool is executed here."""
    _require_operator(current_user)
    try:
        run = approve_mcp_run(
            run_id,
            user_id=str(current_user.id),
            approver_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not run:
        raise HTTPException(status_code=404, detail="MCP run not found")
    _audit_mcp_run_action(
        session=session,
        current_user=current_user,
        action="approved",
        run=run,
    )
    return run


@router.post("/mcp/runs/{run_id}/deny")
def mcp_run_deny(
    run_id: str,
    body: McpDenyRunRequest,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Deny an MCP run and keep it blocked; no tool is executed here."""
    _require_operator(current_user)
    try:
        run = deny_mcp_run(
            run_id,
            user_id=str(current_user.id),
            denier_id=str(current_user.id),
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not run:
        raise HTTPException(status_code=404, detail="MCP run not found")
    _audit_mcp_run_action(
        session=session,
        current_user=current_user,
        action="denied",
        run=run,
    )
    return run
