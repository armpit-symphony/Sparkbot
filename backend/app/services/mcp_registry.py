from __future__ import annotations

import os
from typing import Any, Literal, TypedDict

from app.services.guardian import get_guardian_suite
from app.services.guardian import task_guardian as tg

McpPolicyTag = Literal[
    "read-only",
    "write",
    "destructive",
    "external-send",
    "robot-motion",
    "secret-use",
]
McpRiskLevel = Literal["low", "medium", "high", "critical"]
McpRuntime = Literal["sparkbot", "lima-robo-os"]
McpHealthSource = Literal["sparkbot-api", "task-guardian", "guardian-vault", "external-mcp"]
McpDryRunSupport = Literal["native", "explain-plan", "required-before-motion"]


class McpToolManifest(TypedDict):
    id: str
    name: str
    owner: str
    runtime: McpRuntime
    description: str
    policy: list[McpPolicyTag]
    riskLevel: McpRiskLevel
    requiredSecrets: list[str]
    healthSource: McpHealthSource
    dryRunSupport: McpDryRunSupport


MCP_TOOL_MANIFESTS: list[McpToolManifest] = [
    {
        "id": "sparkbot.shell_run",
        "name": "shell_run",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Run PowerShell or bash commands on the Sparkbot host with persisted working directory.",
        "policy": ["write", "destructive"],
        "riskLevel": "high",
        "requiredSecrets": [],
        "healthSource": "sparkbot-api",
        "dryRunSupport": "explain-plan",
    },
    {
        "id": "sparkbot.terminal_send",
        "name": "terminal_send",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Send commands into an attached live Workstation terminal session.",
        "policy": ["write", "destructive"],
        "riskLevel": "high",
        "requiredSecrets": [],
        "healthSource": "sparkbot-api",
        "dryRunSupport": "explain-plan",
    },
    {
        "id": "sparkbot.browser_control",
        "name": "browser_open / click / fill",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Open Chromium, read pages, click controls, and fill forms.",
        "policy": ["read-only", "write", "external-send"],
        "riskLevel": "medium",
        "requiredSecrets": [],
        "healthSource": "sparkbot-api",
        "dryRunSupport": "explain-plan",
    },
    {
        "id": "sparkbot.google_calendar",
        "name": "calendar_list_events / calendar_create_event",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Read Google Calendar events and create meetings through the Google API.",
        "policy": ["read-only", "write", "external-send", "secret-use"],
        "riskLevel": "medium",
        "requiredSecrets": ["google_client_id", "google_client_secret", "google_refresh_token"],
        "healthSource": "guardian-vault",
        "dryRunSupport": "explain-plan",
    },
    {
        "id": "sparkbot.task_guardian",
        "name": "Task Guardian jobs",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Run scheduled tool workflows with verifier checks, retries, run history, and notifications.",
        "policy": ["read-only", "write", "external-send"],
        "riskLevel": "high",
        "requiredSecrets": [],
        "healthSource": "task-guardian",
        "dryRunSupport": "native",
    },
    {
        "id": "sparkbot.guardian_vault",
        "name": "vault_use_secret / vault_add_secret",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Store and use encrypted secrets with break-glass PIN and redacted audit logs.",
        "policy": ["secret-use", "write", "destructive"],
        "riskLevel": "critical",
        "requiredSecrets": ["SPARKBOT_VAULT_KEY"],
        "healthSource": "guardian-vault",
        "dryRunSupport": "explain-plan",
    },
    {
        "id": "sparkbot.memory_recall",
        "name": "memory_recall / memory_reindex",
        "owner": "Sparkbot",
        "runtime": "sparkbot",
        "description": "Search and maintain the source-grounded Guardian Memory ledger.",
        "policy": ["read-only", "write"],
        "riskLevel": "medium",
        "requiredSecrets": [],
        "healthSource": "sparkbot-api",
        "dryRunSupport": "native",
    },
    {
        "id": "lima.navigate",
        "name": "navigate / follow_route / return_home",
        "owner": "LIMA Robotics OS",
        "runtime": "lima-robo-os",
        "description": "Move a robot through a route or send it home through LIMA MCP skills.",
        "policy": ["robot-motion", "write"],
        "riskLevel": "critical",
        "requiredSecrets": ["LIMA_MCP_URL or local LIMA daemon"],
        "healthSource": "external-mcp",
        "dryRunSupport": "required-before-motion",
    },
    {
        "id": "lima.inspect",
        "name": "inspect / detect_object / report_status",
        "owner": "LIMA Robotics OS",
        "runtime": "lima-robo-os",
        "description": "Read robot state, perception streams, object detections, and inspection reports.",
        "policy": ["read-only"],
        "riskLevel": "medium",
        "requiredSecrets": ["LIMA_MCP_URL or local LIMA daemon"],
        "healthSource": "external-mcp",
        "dryRunSupport": "native",
    },
    {
        "id": "lima.stop",
        "name": "stop",
        "owner": "LIMA Robotics OS",
        "runtime": "lima-robo-os",
        "description": "Stop active robot motion or an active blueprint immediately.",
        "policy": ["robot-motion", "write"],
        "riskLevel": "critical",
        "requiredSecrets": ["LIMA_MCP_URL or local LIMA daemon"],
        "healthSource": "external-mcp",
        "dryRunSupport": "required-before-motion",
    },
    {
        "id": "lima.replay_simulation",
        "name": "replay / simulation blueprints",
        "owner": "LIMA Robotics OS",
        "runtime": "lima-robo-os",
        "description": "Run no-hardware robot demos through replay data or MuJoCo simulation.",
        "policy": ["read-only"],
        "riskLevel": "low",
        "requiredSecrets": [],
        "healthSource": "external-mcp",
        "dryRunSupport": "native",
    },
]

MCP_RUN_TIMELINE = [
    "User request",
    "Parsed intent and context pack",
    "Tool manifests matched",
    "Policy tags and risk evaluated",
    "Dry run or explain plan",
    "Operator approval when required",
    "Execution",
    "Audit evidence and run summary",
]


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _vault_has(alias: str) -> bool:
    try:
        return get_guardian_suite().vault.vault_get_metadata(alias) is not None
    except Exception:
        return False


def _env_or_vault_has(env_var: str, alias: str) -> bool:
    return bool(os.getenv(env_var, "").strip()) or _vault_has(alias)


def _manifest_status(manifest: McpToolManifest) -> dict[str, Any]:
    if manifest["healthSource"] == "external-mcp":
        bridge_configured = bool(os.getenv("LIMA_MCP_URL", "").strip()) or bool(
            os.getenv("LIMA_DAEMON_URL", "").strip()
        )
        if manifest["id"] == "lima.replay_simulation":
            return {
                "state": "demo-ready",
                "label": "Demo-ready",
                "configured": True,
                "details": "Replay and simulation commands do not require robot hardware.",
            }
        return {
            "state": "configured" if bridge_configured else "bridge-needed",
            "label": "Bridge configured" if bridge_configured else "Bridge needed",
            "configured": bridge_configured,
            "details": "Set LIMA_MCP_URL or LIMA_DAEMON_URL when the LIMA MCP bridge is available.",
        }

    if manifest["id"] == "sparkbot.google_calendar":
        configured = (
            _env_or_vault_has("GOOGLE_CLIENT_ID", "google_client_id")
            and _env_or_vault_has("GOOGLE_CLIENT_SECRET", "google_client_secret")
            and _env_or_vault_has("GOOGLE_REFRESH_TOKEN", "google_refresh_token")
        )
        return {
            "state": "configured" if configured else "missing-secrets",
            "label": "Google ready" if configured else "Google secrets missing",
            "configured": configured,
            "details": "Uses Google OAuth values from env or Guardian Vault.",
        }

    if manifest["healthSource"] == "guardian-vault":
        configured = bool(os.getenv("SPARKBOT_VAULT_KEY", "").strip())
        return {
            "state": "configured" if configured else "missing-vault-key",
            "label": "Vault live" if configured else "Vault key missing",
            "configured": configured,
            "details": "Requires SPARKBOT_VAULT_KEY for encrypted secret storage.",
        }

    if manifest["healthSource"] == "task-guardian":
        configured = _truthy_env("SPARKBOT_TASK_GUARDIAN_ENABLED", True)
        return {
            "state": "configured" if configured else "disabled",
            "label": "Scheduler live" if configured else "Disabled",
            "configured": configured,
            "details": "Task Guardian is controlled by SPARKBOT_TASK_GUARDIAN_ENABLED.",
        }

    return {
        "state": "configured",
        "label": "API live",
        "configured": True,
        "details": "Built into the Sparkbot backend.",
    }


def _requires_approval(manifest: McpToolManifest) -> bool:
    return bool(
        {"write", "destructive", "external-send", "robot-motion", "secret-use"}.intersection(
            manifest["policy"]
        )
    )


def get_mcp_registry() -> dict[str, Any]:
    manifests = [
        {
            **manifest,
            "status": _manifest_status(manifest),
            "approvalRequired": _requires_approval(manifest),
            "explainPlanRequired": manifest["dryRunSupport"] in {"explain-plan", "required-before-motion"}
            or _requires_approval(manifest),
        }
        for manifest in MCP_TOOL_MANIFESTS
    ]
    return {
        "manifests": manifests,
        "runTimeline": MCP_RUN_TIMELINE,
        "health": {
            "sparkbotApiLive": True,
            "vaultConfigured": bool(os.getenv("SPARKBOT_VAULT_KEY", "").strip()),
            "taskGuardianEnabled": _truthy_env("SPARKBOT_TASK_GUARDIAN_ENABLED", True),
            "taskGuardianWriteEnabled": tg.TASK_GUARDIAN_WRITE_ENABLED,
            "limaBridgeConfigured": bool(os.getenv("LIMA_MCP_URL", "").strip())
            or bool(os.getenv("LIMA_DAEMON_URL", "").strip()),
        },
    }

