from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

RobotEnvironment = Literal["replay", "simulation", "real_hardware"]
RobotRiskLevel = Literal["read_only", "low", "medium", "high", "blocked"]

READ_ONLY_TOOLS = {"server_status", "list_modules", "observe"}
STOP_TOOL_CANDIDATES = ("stop_navigation", "stop", "agent_send")
MOTION_TOOL_NAMES = {
    "relative_move",
    "navigate_with_text",
    "follow_person",
    "set_gps_travel_points",
    "execute_sport_command",
    "agent_send",
}


class LimaBridgeError(RuntimeError):
    """Raised when a configured LIMA bridge cannot satisfy a request."""


def configured_mcp_url() -> str:
    return os.getenv("LIMA_MCP_URL", "").strip()


def bridge_status() -> dict[str, Any]:
    url = configured_mcp_url()
    parsed = urlparse(url) if url else None
    safe_target = ""
    if parsed and parsed.scheme and parsed.netloc:
        safe_target = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return {
        "configured": bool(url),
        "mcpUrlConfigured": bool(url),
        "safeTarget": safe_target,
        "mode": "mcp" if url else "offline",
        "message": (
            "LIMA MCP bridge configured."
            if url
            else "Set LIMA_MCP_URL to a running LIMA MCP endpoint, for example http://127.0.0.1:9990/mcp."
        ),
    }


def _jsonrpc_payload(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


async def _mcp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = configured_mcp_url()
    if not url:
        raise LimaBridgeError("LIMA_MCP_URL is not configured.")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=_jsonrpc_payload(method, params))
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise LimaBridgeError(f"LIMA MCP bridge request failed: {exc}") from exc
    except ValueError as exc:
        raise LimaBridgeError("LIMA MCP bridge returned non-JSON response.") from exc
    if "error" in data:
        err = data["error"]
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise LimaBridgeError(f"LIMA MCP error: {message}")
    result = data.get("result")
    return result if isinstance(result, dict) else {"value": result}


async def list_lima_tools() -> list[dict[str, Any]]:
    await _mcp_call("initialize")
    result = await _mcp_call("tools/list")
    tools = result.get("tools", [])
    return tools if isinstance(tools, list) else []


def _extract_number(text: str, default: float = 0.0) -> float:
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if not match:
        return default
    return float(match.group(1))


def _bounded_motion_args(action: str) -> dict[str, float]:
    text = action.lower()
    distance = _extract_number(text, 0.5)
    degrees = _extract_number(text, 90.0)
    if any(word in text for word in ("turn", "rotate", "spin")):
        sign = -1.0 if "right" in text else 1.0
        return {"forward": 0.0, "left": 0.0, "degrees": sign * min(abs(degrees), 90.0)}
    if "back" in text or "backward" in text:
        return {"forward": -min(abs(distance), 0.5), "left": 0.0, "degrees": 0.0}
    if "left" in text:
        return {"forward": 0.0, "left": min(abs(distance), 0.5), "degrees": 0.0}
    if "right" in text:
        return {"forward": 0.0, "left": -min(abs(distance), 0.5), "degrees": 0.0}
    return {"forward": min(abs(distance), 0.5), "left": 0.0, "degrees": 0.0}


def resolve_robot_command(
    requested_action: str,
    *,
    mcp_tool_name: str = "",
    mcp_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = (requested_action or "").strip()
    tool = (mcp_tool_name or "").strip()
    args = dict(mcp_args or {})
    text = action.lower()

    if tool:
        return {"toolName": tool, "arguments": args, "parsedIntent": "explicit_tool"}

    if any(word in text for word in ("status", "state", "modules")):
        return {"toolName": "server_status", "arguments": {}, "parsedIntent": "status"}
    if any(word in text for word in ("camera", "see", "look", "observe", "inspect", "describe")):
        return {"toolName": "observe", "arguments": {}, "parsedIntent": "inspect"}
    if any(word in text for word in ("stop", "halt", "freeze", "emergency")):
        return {"toolName": "stop_navigation", "arguments": {}, "parsedIntent": "stop"}
    if any(word in text for word in ("move", "walk", "forward", "back", "backward", "left", "right", "turn", "rotate")):
        return {
            "toolName": "relative_move",
            "arguments": _bounded_motion_args(action),
            "parsedIntent": "relative_motion",
        }
    if any(word in text for word in ("go to", "navigate", "find", "explore", "patrol", "follow")):
        return {
            "toolName": "agent_send",
            "arguments": {"message": action},
            "parsedIntent": "agent_instruction",
        }
    return {
        "toolName": "agent_send",
        "arguments": {"message": action},
        "parsedIntent": "agent_instruction",
    }


def classify_robot_command(
    *,
    environment: RobotEnvironment,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name in READ_ONLY_TOOLS:
        return {
            "riskLevel": "read_only",
            "approvalRequired": False,
            "guardianDecision": "N/A",
            "reason": "Read-only robot inspection/status command.",
        }
    if tool_name in STOP_TOOL_CANDIDATES and environment == "real_hardware":
        return {
            "riskLevel": "high",
            "approvalRequired": False,
            "guardianDecision": "emergency_stop_bypass",
            "reason": "Emergency stop is always available and audited.",
        }
    if environment in {"replay", "simulation"}:
        if tool_name == "relative_move":
            forward = abs(float(arguments.get("forward") or 0.0))
            left = abs(float(arguments.get("left") or 0.0))
            degrees = abs(float(arguments.get("degrees") or 0.0))
            low = forward <= 0.5 and left <= 0.5 and degrees <= 90.0
            return {
                "riskLevel": "low" if low else "medium",
                "approvalRequired": not low,
                "guardianDecision": "N/A" if low else "pending",
                "reason": "Small simulation/replay movement is allowed; larger moves need approval.",
            }
        return {
            "riskLevel": "low",
            "approvalRequired": False,
            "guardianDecision": "N/A",
            "reason": "Replay/simulation robot command.",
        }
    if tool_name in MOTION_TOOL_NAMES or tool_name not in READ_ONLY_TOOLS:
        return {
            "riskLevel": "high",
            "approvalRequired": True,
            "guardianDecision": "pending",
            "reason": "Real-hardware robot motion is blocked until Guardian approval handoff is implemented.",
        }
    return {
        "riskLevel": "blocked",
        "approvalRequired": True,
        "guardianDecision": "blocked",
        "reason": "Unknown robot command.",
    }


def command_contract(
    *,
    source_user: str,
    robot_id: str,
    environment: RobotEnvironment,
    requested_action: str,
    resolved: dict[str, Any],
    classification: dict[str, Any],
    result: dict[str, Any] | None = None,
    telemetry_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "command_id": str(uuid.uuid4()),
        "source_user": source_user,
        "robot_id": robot_id,
        "environment": environment,
        "requested_action": requested_action,
        "risk_level": classification["riskLevel"],
        "approval_required": classification["approvalRequired"],
        "guardian_decision": classification["guardianDecision"],
        "mcp_tool_name": resolved["toolName"],
        "mcp_args": resolved["arguments"],
        "result": result or {},
        "telemetry_snapshot": telemetry_snapshot or {},
        "audit_timestamp": now,
        "parsed_intent": resolved.get("parsedIntent", ""),
        "safety_reason": classification["reason"],
    }


async def execute_robot_command(
    *,
    source_user: str,
    requested_action: str,
    robot_id: str = "default",
    environment: RobotEnvironment = "simulation",
    mcp_tool_name: str = "",
    mcp_args: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved = resolve_robot_command(
        requested_action,
        mcp_tool_name=mcp_tool_name,
        mcp_args=mcp_args,
    )
    classification = classify_robot_command(
        environment=environment,
        tool_name=resolved["toolName"],
        arguments=resolved["arguments"],
    )
    contract = command_contract(
        source_user=source_user,
        robot_id=robot_id,
        environment=environment,
        requested_action=requested_action,
        resolved=resolved,
        classification=classification,
    )
    if dry_run:
        return {"executed": False, "contract": contract, "bridge": bridge_status()}
    if classification["approvalRequired"]:
        return {
            "executed": False,
            "blocked": True,
            "contract": contract,
            "bridge": bridge_status(),
            "message": classification["reason"],
        }
    result = await _mcp_call(
        "tools/call",
        {"name": resolved["toolName"], "arguments": resolved["arguments"]},
    )
    final_contract = {
        **contract,
        "result": result,
        "telemetry_snapshot": {"source": "lima_mcp", "captured_at": datetime.now(timezone.utc).isoformat()},
    }
    return {"executed": True, "contract": final_contract, "bridge": bridge_status()}


async def emergency_stop(*, source_user: str, robot_id: str = "default") -> dict[str, Any]:
    tools = await list_lima_tools()
    names = {str(tool.get("name") or "") for tool in tools if isinstance(tool, dict)}
    tool_name = next((candidate for candidate in STOP_TOOL_CANDIDATES if candidate in names), "agent_send")
    args = {"message": "stop immediately"} if tool_name == "agent_send" else {}
    resolved = {"toolName": tool_name, "arguments": args, "parsedIntent": "emergency_stop"}
    classification = {
        "riskLevel": "high",
        "approvalRequired": False,
        "guardianDecision": "emergency_stop_bypass",
        "reason": "Emergency stop bypasses approval and is audited.",
    }
    result = await _mcp_call("tools/call", {"name": tool_name, "arguments": args})
    contract = command_contract(
        source_user=source_user,
        robot_id=robot_id,
        environment="real_hardware",
        requested_action="emergency_stop",
        resolved=resolved,
        classification=classification,
        result=result,
        telemetry_snapshot={"source": "lima_mcp", "captured_at": datetime.now(timezone.utc).isoformat()},
    )
    return {"executed": True, "contract": contract, "bridge": bridge_status()}
