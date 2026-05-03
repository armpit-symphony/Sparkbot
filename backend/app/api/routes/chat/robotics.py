from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import create_audit_log
from app.services.lima_robotics_bridge import (
    LimaBridgeError,
    bridge_status,
    emergency_stop,
    execute_robot_command,
    list_lima_tools,
)

router = APIRouter(prefix="/robotics", tags=["chat-robotics"])


class RobotCommandRequest(BaseModel):
    requested_action: str = Field(..., min_length=1, max_length=1000)
    robot_id: str = Field("default", min_length=1, max_length=120)
    environment: Literal["replay", "simulation", "real_hardware"] = "simulation"
    mcp_tool_name: str = Field("", max_length=120)
    mcp_args: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class EmergencyStopRequest(BaseModel):
    robot_id: str = Field("default", min_length=1, max_length=120)


def _audit_robotics(
    *,
    session: SessionDep,
    current_user: CurrentChatUser,
    action: str,
    payload: dict[str, Any],
) -> None:
    contract = payload.get("contract") if isinstance(payload, dict) else None
    contract = contract if isinstance(contract, dict) else {}
    create_audit_log(
        session,
        tool_name=f"lima_robotics_{action}",
        tool_input=json.dumps(
            {
                "command_id": contract.get("command_id"),
                "robot_id": contract.get("robot_id"),
                "environment": contract.get("environment"),
                "mcp_tool_name": contract.get("mcp_tool_name"),
                "risk_level": contract.get("risk_level"),
                "approval_required": contract.get("approval_required"),
            },
            sort_keys=True,
        ),
        tool_result=json.dumps(
            {
                "executed": payload.get("executed"),
                "blocked": payload.get("blocked", False),
                "guardian_decision": contract.get("guardian_decision"),
                "safety_reason": contract.get("safety_reason"),
            },
            sort_keys=True,
        ),
        user_id=current_user.id,
        room_id=None,
        agent_name="lima_robotics_bridge",
    )


@router.get("/status")
def robotics_status(current_user: CurrentChatUser) -> dict[str, Any]:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return bridge_status()


@router.get("/tools")
async def robotics_tools(current_user: CurrentChatUser) -> dict[str, Any]:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        tools = await list_lima_tools()
    except LimaBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"tools": tools, "count": len(tools), "bridge": bridge_status()}


@router.post("/command")
async def robotics_command(
    body: RobotCommandRequest,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        result = await execute_robot_command(
            source_user=current_user.username or str(current_user.id),
            requested_action=body.requested_action,
            robot_id=body.robot_id,
            environment=body.environment,
            mcp_tool_name=body.mcp_tool_name,
            mcp_args=body.mcp_args,
            dry_run=body.dry_run,
        )
    except LimaBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit_robotics(session=session, current_user=current_user, action="command", payload=result)
    return result


@router.post("/emergency-stop")
async def robotics_emergency_stop(
    body: EmergencyStopRequest,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        result = await emergency_stop(
            source_user=current_user.username or str(current_user.id),
            robot_id=body.robot_id,
        )
    except LimaBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit_robotics(
        session=session,
        current_user=current_user,
        action="emergency_stop",
        payload=result,
    )
    return result
