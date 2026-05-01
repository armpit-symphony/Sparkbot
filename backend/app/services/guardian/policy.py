from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Literal


def _policy_enabled() -> bool:
    """Return True when Computer Control / PIN policy restrictions are enabled."""
    return os.getenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true").lower() not in ("false", "0", "no", "off")


GLOBAL_COMPUTER_CONTROL_TTL_SECONDS = 24 * 60 * 60


def global_bypass_status() -> dict[str, Any]:
    """Return the app-wide Computer Control state with expiry metadata."""
    enabled = os.getenv("SPARKBOT_GLOBAL_COMPUTER_CONTROL", "false").lower() in ("1", "true", "yes", "on")
    raw_expires = os.getenv("SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT", "").strip()
    expires_at = 0.0
    if raw_expires:
        try:
            expires_at = float(raw_expires)
        except ValueError:
            expires_at = 0.0
    ttl_remaining = max(0, int(expires_at - time.time())) if expires_at else 0
    active = bool(enabled and ttl_remaining > 0)
    return {
        "active": active,
        "expires_at": expires_at if active else None,
        "ttl_remaining": ttl_remaining if active else 0,
    }


def global_bypass_enabled() -> bool:
    """True when app-wide Computer Control is active and unexpired."""
    return bool(global_bypass_status()["active"])


PolicyAction = Literal["allow", "confirm", "deny", "privileged", "privileged_reveal"]
PolicyScope = Literal["read", "write", "execute", "admin"]


@dataclass(frozen=True)
class ToolPolicy:
    tool_name: str
    scope: PolicyScope
    resource: str
    default_action: PolicyAction
    action_type: str
    high_risk: bool = False
    requires_execution_gate: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    tool_name: str
    scope: PolicyScope
    resource: str
    action: PolicyAction
    action_type: str
    high_risk: bool
    reason: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "tool_name": self.tool_name,
                "scope": self.scope,
                "resource": self.resource,
                "action": self.action,
                "action_type": self.action_type,
                "high_risk": self.high_risk,
                "reason": self.reason,
            }
        )


def _build_policy_registry() -> dict[str, ToolPolicy]:
    registry: dict[str, ToolPolicy] = {}

    def add(
        tool_name: str,
        *,
        scope: PolicyScope,
        resource: str,
        default_action: PolicyAction,
        action_type: str,
        high_risk: bool = False,
        requires_execution_gate: bool = False,
    ) -> None:
        registry[tool_name] = ToolPolicy(
            tool_name=tool_name,
            scope=scope,
            resource=resource,
            default_action=default_action,
            action_type=action_type,
            high_risk=high_risk,
            requires_execution_gate=requires_execution_gate,
        )

    for tool_name in (
        "web_search",
        "fetch_url",
        "browser_open",
        "browser_navigate",
        "browser_snapshot",
        "browser_close",
        "browser_list_sessions",
        "get_datetime",
        "calculate",
        "list_tasks",
        "github_list_prs",
        "github_get_pr",
        "github_get_ci_status",
        "slack_list_channels",
        "slack_get_channel_history",
        "notion_search",
        "notion_get_page",
        "confluence_search",
        "confluence_get_page",
        "gmail_fetch_inbox",
        "gmail_search",
        "gmail_get_message",
        "drive_search",
        "drive_get_file",
        "email_fetch_inbox",
        "email_search",
        "list_reminders",
        "calendar_list_events",
        "guardian_list_tasks",
        "guardian_list_runs",
        "guardian_list_improvements",
        "guardian_simulate_policy",
    ):
        add(
            tool_name,
            scope="read",
            resource="workspace",
            default_action="allow",
            action_type="read",
        )

    for tool_name, resource in (
        ("remember_fact", "memory"),
        ("forget_fact", "memory"),
        ("create_task", "room_task"),
        ("complete_task", "room_task"),
        ("set_reminder", "reminder"),
        ("cancel_reminder", "reminder"),
        ("guardian_run_task", "guardian_task"),
        ("guardian_pause_task", "guardian_task"),
        ("guardian_propose_improvement", "guardian_improvement"),
    ):
        add(
            tool_name,
            scope="write",
            resource=resource,
            default_action="allow",
            action_type="room_write",
        )

    for tool_name, resource in (
        ("browser_fill_field", "web"),
        ("browser_click", "web"),
        ("browser_save_session", "web"),
        ("browser_restore_session", "web"),
        ("gmail_send", "gmail"),
        ("email_send", "email"),
        ("slack_send_message", "slack"),
        ("github_create_issue", "github"),
        ("notion_create_page", "notion"),
        ("confluence_create_page", "confluence"),
        ("calendar_create_event", "calendar"),
        ("drive_create_folder", "drive"),
        ("guardian_schedule_task", "guardian_task"),
    ):
        add(
            tool_name,
            scope="write",
            resource=resource,
            default_action="confirm",
            action_type="write_external",
            high_risk=True,
        )

    add(
        "terminal_list_sessions",
        scope="execute",
        resource="local_machine",
        default_action="allow",
        action_type="command_exec",
        high_risk=False,
        requires_execution_gate=False,
    )
    add(
        "terminal_send",
        scope="execute",
        resource="local_machine",
        default_action="allow",
        action_type="command_exec",
        high_risk=True,
        requires_execution_gate=True,
    )

    add(
        "memory_recall",
        scope="read",
        resource="memory",
        default_action="allow",
        action_type="read",
    )
    add(
        "memory_reindex",
        scope="write",
        resource="memory",
        default_action="confirm",
        action_type="memory_write",
        high_risk=True,
    )
    add(
        "memory_compact",
        scope="write",
        resource="memory",
        default_action="confirm",
        action_type="memory_write",
        high_risk=True,
    )

    add(
        "lima.navigate",
        scope="execute",
        resource="robot",
        default_action="privileged",
        action_type="robot_motion",
        high_risk=True,
        requires_execution_gate=True,
    )
    add(
        "lima.inspect",
        scope="read",
        resource="robot",
        default_action="allow",
        action_type="robot_read",
        high_risk=False,
    )
    add(
        "lima.stop",
        scope="execute",
        resource="robot",
        default_action="privileged",
        action_type="robot_motion",
        high_risk=True,
        requires_execution_gate=True,
    )
    add(
        "lima.replay_simulation",
        scope="read",
        resource="robot_simulation",
        default_action="allow",
        action_type="robot_simulation",
        high_risk=False,
    )

    for tool_name in ("telegram_send_message", "discord_send_message", "whatsapp_send_message"):
        add(
            tool_name,
            scope="write",
            resource="comms",
            default_action="confirm",
            action_type="write_external",
            high_risk=True,
            requires_execution_gate=False,
        )

    add(
        "server_read_command",
        scope="execute",
        resource="server",
        default_action="allow",
        action_type="command_exec",
        high_risk=True,
        requires_execution_gate=True,
    )
    add(
        "ssh_read_command",
        scope="execute",
        resource="ssh",
        default_action="allow",
        action_type="ssh_exec",
        high_risk=True,
        requires_execution_gate=True,
    )
    add(
        "server_manage_service",
        scope="execute",
        resource="service",
        default_action="confirm",
        action_type="service_control",
        high_risk=True,
        requires_execution_gate=True,
    )

    # Vault tools — safe mode allows listing and internal use; writes + reveal require break-glass
    add(
        "vault_list_secrets",
        scope="read",
        resource="vault",
        default_action="allow",
        action_type="read",
    )
    add(
        "vault_use_secret",
        scope="read",
        resource="vault",
        default_action="allow",
        action_type="read",
    )
    add(
        "vault_add_secret",
        scope="write",
        resource="vault",
        default_action="privileged",
        action_type="vault_write",
        high_risk=True,
    )
    add(
        "vault_update_secret",
        scope="write",
        resource="vault",
        default_action="privileged",
        action_type="vault_write",
        high_risk=True,
    )
    add(
        "vault_reveal_secret",
        scope="read",
        resource="vault",
        default_action="privileged_reveal",
        action_type="vault_reveal",
        high_risk=True,
    )
    add(
        "vault_delete_secret",
        scope="write",
        resource="vault",
        default_action="privileged_reveal",
        action_type="vault_reveal",
        high_risk=True,
    )

    return registry


TOOL_POLICIES = _build_policy_registry()
READ_ONLY_SERVICE_ACTIONS = {"status", "service_status", "show_status", "logs", "log", "service_logs", "show_logs"}
_SHELL_WRITE_RE = re.compile(
    r"(^|[;&|]\s*)("
    r"git\s+(add|commit|push|pull|merge|rebase|checkout|switch|reset|restore|tag)|"
    r"(rm|del|erase|rmdir|Remove-Item|mv|move|ren|rename|cp|copy|chmod|chown|Set-Content|Add-Content|New-Item)\b|"
    r"(npm|pnpm|yarn|pip|uv|poetry|cargo|go|docker)\s+(install|add|remove|update|upgrade|build|compose|run)|"
    r"(python|python3|node|bash|sh|pwsh|powershell)\b.*\b(apply|write|migrate|seed|build)\b|"
    r">\s*[^&|;]+|>>\s*[^&|;]+"
    r")",
    re.IGNORECASE,
)


def _shell_command_is_write_like(args: dict[str, Any] | None) -> bool:
    command = str((args or {}).get("command") or "").strip()
    if not command:
        return False
    return bool(_SHELL_WRITE_RE.search(command))


def get_tool_policy(tool_name: str, args: dict[str, Any] | None = None) -> ToolPolicy:
    args = args or {}
    if tool_name == "shell_run":
        if _shell_command_is_write_like(args):
            return ToolPolicy(
                tool_name=tool_name,
                scope="execute",
                resource="local_machine",
                default_action="confirm",
                action_type="command_exec",
                high_risk=True,
            )
        return ToolPolicy(
            tool_name=tool_name,
            scope="read",
            resource="local_machine",
            default_action="allow",
            action_type="read",
            high_risk=False,
        )
    if tool_name == "server_manage_service":
        action = str(args.get("action", "")).strip().lower()
        if action in READ_ONLY_SERVICE_ACTIONS:
            return ToolPolicy(
                tool_name=tool_name,
                scope="read",
                resource="service",
                default_action="allow",
                action_type="read",
                high_risk=False,
            )
    # Check skill-provided policies before unknown→deny fallback
    from app.services.skills import (
        _registry as _skill_registry,  # lazy import avoids circular
    )
    skill_pol = _skill_registry.policies.get(tool_name)
    if skill_pol:
        return ToolPolicy(tool_name=tool_name, **skill_pol)
    return TOOL_POLICIES.get(
        tool_name,
        ToolPolicy(
            tool_name=tool_name,
            scope="admin",
            resource="unknown",
            default_action="deny",
            action_type="deny",
        ),
    )


def decide_tool_use(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    room_execution_allowed: bool | None = None,
    is_operator: bool = False,
    is_privileged: bool = False,
) -> PolicyDecision:
    policy = get_tool_policy(tool_name, args)

    # Vault tools always require operator identity regardless of policy mode.
    if tool_name.startswith("vault_") and not is_operator:
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="deny",
            action_type=policy.action_type,
            high_risk=True,
            reason="Vault tools are restricted to configured Sparkbot operators.",
        )

    # Global Computer Control bypass: routine non-vault diagnostics and actions
    # run across all rooms. High-risk edits/deletes/sends still require the
    # standard yes/no confirmation, and vault remains governed below.
    if global_bypass_enabled() and not tool_name.startswith("vault_"):
        action: PolicyAction = "confirm" if policy.default_action == "confirm" else "allow"
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action=action,
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=(
                "Global Computer Control is on for all rooms; routine non-vault actions are allowed. "
                "Edits, deletes, sends, and critical changes still require yes/no confirmation."
            ),
        )

    # Personal mode (default): no gates, no confirms, no denials — everything runs freely.
    # Switch to office mode by setting SPARKBOT_GUARDIAN_POLICY_ENABLED=true.
    if not _policy_enabled():
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="allow",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason="Guardian policy restrictions disabled by environment.",
        )

    if tool_name == "shell_run" and policy.default_action == "confirm":
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="confirm",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason="Write-like shell command requires explicit confirmation before execution.",
        )

    if room_execution_allowed and not tool_name.startswith("vault_"):
        action: PolicyAction = "confirm" if policy.default_action == "confirm" else "allow"
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action=action,
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=(
                "Computer Control is on for this room; routine non-vault actions are allowed. "
                "Edits, deletes, sends, and critical changes still require yes/no confirmation."
            ),
        )

    if policy.default_action == "deny":
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="deny",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=f"Tool '{tool_name}' is not approved by Sparkbot policy.",
        )

    if policy.requires_execution_gate and not room_execution_allowed:
        if is_operator:
            return PolicyDecision(
                tool_name=tool_name,
                scope=policy.scope,
                resource=policy.resource,
                action="privileged",
                action_type=policy.action_type,
                high_risk=policy.high_risk,
                reason=(
                    "Computer Control is off for this room. Enter your operator PIN with /breakglass "
                    "to authorize this local machine action."
                ),
            )
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="deny",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=(
                "Computer Control is disabled for this room. Only a configured Sparkbot operator "
                "can authorize local machine actions with break-glass PIN."
            ),
        )

    if (
        not room_execution_allowed
        and policy.high_risk
        and policy.scope in {"write", "execute"}
        and not tool_name.startswith("vault_")
    ):
        if is_privileged:
            return PolicyDecision(
                tool_name=tool_name,
                scope=policy.scope,
                resource=policy.resource,
                action="allow",
                action_type=policy.action_type,
                high_risk=policy.high_risk,
                reason="Break-glass PIN session is active; high-risk action is allowed while Computer Control is off.",
            )
        if is_operator:
            return PolicyDecision(
                tool_name=tool_name,
                scope=policy.scope,
                resource=policy.resource,
                action="privileged",
                action_type=policy.action_type,
                high_risk=policy.high_risk,
                reason=(
                    "Computer Control is off for this room. Enter your operator PIN with /breakglass "
                    "to authorize this command, edit, browser write, or comms action."
                ),
            )
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="deny",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason="High-risk commands, edits, browser writes, and comms sends require a Sparkbot operator PIN.",
        )

    if policy.default_action == "confirm":
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="confirm",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=f"{policy.scope.title()} access to {policy.resource} requires confirmation.",
        )

    # Privileged-only tools: require break-glass session
    if policy.default_action == "privileged":
        if is_privileged:
            return PolicyDecision(
                tool_name=tool_name,
                scope=policy.scope,
                resource=policy.resource,
                action="allow",
                action_type=policy.action_type,
                high_risk=policy.high_risk,
                reason=f"Privileged access to {policy.resource} is allowed (break-glass active).",
            )
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="privileged",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=f"'{tool_name}' requires break-glass privileged mode. Use /breakglass to authenticate.",
        )

    # Privileged-reveal tools: require break-glass AND explicit confirm
    if policy.default_action == "privileged_reveal":
        if is_privileged:
            return PolicyDecision(
                tool_name=tool_name,
                scope=policy.scope,
                resource=policy.resource,
                action="confirm",
                action_type=policy.action_type,
                high_risk=policy.high_risk,
                reason=f"Destructive vault operation on {policy.resource} requires explicit confirmation.",
            )
        return PolicyDecision(
            tool_name=tool_name,
            scope=policy.scope,
            resource=policy.resource,
            action="privileged_reveal",
            action_type=policy.action_type,
            high_risk=policy.high_risk,
            reason=f"'{tool_name}' requires break-glass privileged mode. Use /breakglass to authenticate.",
        )

    return PolicyDecision(
        tool_name=tool_name,
        scope=policy.scope,
        resource=policy.resource,
        action="allow",
        action_type=policy.action_type,
        high_risk=policy.high_risk,
        reason=f"{policy.scope.title()} access to {policy.resource} is allowed.",
    )


def simulate_tool_policy(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    room_execution_allowed: bool | None = None,
    is_operator: bool = False,
    is_privileged: bool = False,
) -> dict[str, Any]:
    """Return a structured what-if policy decision without executing the tool."""
    policy = get_tool_policy(tool_name, args)
    decision = decide_tool_use(
        tool_name,
        args or {},
        room_execution_allowed=room_execution_allowed,
        is_operator=is_operator,
        is_privileged=is_privileged,
    )
    return {
        "simulation_only": True,
        "policy_enabled": _policy_enabled(),
        "tool_name": decision.tool_name,
        "tool_args_keys": sorted(str(key) for key in (args or {}).keys()),
        "classification": {
            "scope": policy.scope,
            "resource": policy.resource,
            "default_action": policy.default_action,
            "action_type": policy.action_type,
            "high_risk": policy.high_risk,
            "requires_execution_gate": policy.requires_execution_gate,
        },
        "context": {
            "room_execution_allowed": room_execution_allowed,
            "is_operator": is_operator,
            "is_privileged": is_privileged,
        },
        "decision": {
            "action": decision.action,
            "scope": decision.scope,
            "resource": decision.resource,
            "action_type": decision.action_type,
            "high_risk": decision.high_risk,
            "reason": decision.reason,
        },
    }
