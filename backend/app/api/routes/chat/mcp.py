from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import create_audit_log, get_chat_room_by_id, get_chat_room_member
from app.services.guardian import get_guardian_suite
from app.services.mcp_registry import build_mcp_explain_plan, get_mcp_registry

router = APIRouter(tags=["chat-mcp"])


class McpExplainPlanRequest(BaseModel):
    manifest_id: str = Field(..., min_length=1, max_length=120)
    tool_args: dict[str, Any] = Field(default_factory=dict)
    user_request: str = Field("", max_length=1000)
    room_id: str | None = Field(default=None, max_length=64)


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
    room_execution_allowed: bool | None = None
    room_uuid: uuid.UUID | None = None
    if body.room_id:
        try:
            room_uuid = uuid.UUID(body.room_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid room_id")
        room = get_chat_room_by_id(session, room_uuid)
        membership = get_chat_room_member(session, room_uuid, current_user.id)
        if not room or not membership:
            raise HTTPException(status_code=404, detail="Room not found")
        room_execution_allowed = bool(room.execution_allowed)

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

    create_audit_log(
        session,
        tool_name="mcp_explain_plan",
        tool_input=json.dumps(
            {
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
