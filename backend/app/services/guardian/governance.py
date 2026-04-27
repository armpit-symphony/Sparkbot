from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.api.routes.chat.agents import agent_is_enabled, get_all_agents
from app.services.guardian import policy, tool_guardrails


def _configured(*names: str) -> bool:
    return any(os.getenv(name, "").strip() for name in names)


def _shell_enabled() -> bool:
    return os.getenv("SPARKBOT_SHELL_DISABLE", "").strip().lower() not in {"1", "true", "yes", "on"}


def connector_health() -> list[dict[str, Any]]:
    """Return connector quality metadata without exposing secret values."""
    connectors = [
        {
            "id": "gmail",
            "label": "Gmail",
            "configured": _configured("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
            "read_scopes": ["gmail_fetch_inbox", "gmail_search", "gmail_get_message"],
            "write_scopes": ["gmail_send"],
            "audit_metadata": ["tool_name", "room_id", "user_id", "policy_decision", "redacted_args"],
        },
        {
            "id": "google_calendar",
            "label": "Google Calendar",
            "configured": _configured("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
            "read_scopes": ["calendar_list_events"],
            "write_scopes": ["calendar_create_event"],
            "audit_metadata": ["tool_name", "room_id", "user_id", "policy_decision", "redacted_args"],
        },
        {
            "id": "google_drive",
            "label": "Google Drive",
            "configured": _configured("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
            "read_scopes": ["drive_search", "drive_get_file"],
            "write_scopes": ["drive_create_folder"],
            "audit_metadata": ["tool_name", "room_id", "user_id", "policy_decision", "redacted_args"],
        },
        {
            "id": "github",
            "label": "GitHub",
            "configured": _configured("GITHUB_TOKEN"),
            "read_scopes": ["github_list_prs", "github_get_pr", "github_get_ci_status"],
            "write_scopes": ["github_create_issue"],
            "audit_metadata": ["tool_name", "repo", "room_id", "user_id", "policy_decision"],
        },
        {
            "id": "slack",
            "label": "Slack",
            "configured": _configured("SLACK_BOT_TOKEN"),
            "read_scopes": ["slack_list_channels", "slack_get_channel_history"],
            "write_scopes": ["slack_send_message"],
            "audit_metadata": ["tool_name", "channel", "room_id", "user_id", "policy_decision"],
        },
        {
            "id": "local_filesystem",
            "label": "Local filesystem",
            "configured": _shell_enabled(),
            "read_scopes": ["shell_run read-only commands"],
            "write_scopes": ["shell_run write-like commands"],
            "audit_metadata": ["tool_name", "command_classification", "room_id", "user_id", "policy_decision"],
        },
    ]
    for connector in connectors:
        connector["health"] = "configured" if connector["configured"] else "needs_setup"
        connector["setup_test"] = "available" if connector["read_scopes"] else "not_applicable"
    return connectors


def workflow_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": "morning_brief",
            "name": "Morning Brief",
            "trigger": "daily:13:00",
            "conditions": ["connector:gmail optional", "connector:calendar optional"],
            "steps": ["morning_briefing"],
            "approval_gate": "none for read-only; required for write follow-ups",
            "notification": "room + Telegram/Discord if linked",
            "audit_export": "Task Guardian run + audit log",
        },
        {
            "id": "pr_monitor",
            "name": "PR Monitor",
            "trigger": "every:3600",
            "conditions": ["connector:github configured", "repo allowlisted"],
            "steps": ["github_list_prs", "github_get_ci_status"],
            "approval_gate": "required before issue/comment creation",
            "notification": "room + linked comms bridge",
            "audit_export": "Task Guardian run + GitHub tool audit",
        },
        {
            "id": "deploy_checklist",
            "name": "Deploy Checklist",
            "trigger": "manual",
            "conditions": ["Computer Control on or break-glass active"],
            "steps": ["policy simulation", "server diagnostics", "CI status", "approval gate"],
            "approval_gate": "required for service control or write-like shell",
            "notification": "room summary",
            "audit_export": "Executive Guardian decision + audit log",
        },
        {
            "id": "inbox_triage",
            "name": "Inbox Triage",
            "trigger": "every:1800",
            "conditions": ["mail connector configured"],
            "steps": ["gmail_fetch_inbox or email_fetch_inbox", "summarize urgent items"],
            "approval_gate": "required before sending replies",
            "notification": "room + mobile bridge",
            "audit_export": "Task Guardian run + mail tool audit",
        },
        {
            "id": "incident_response",
            "name": "Incident Response",
            "trigger": "manual or alert webhook",
            "conditions": ["operator present", "Computer Control context explicit"],
            "steps": ["Round Table", "server diagnostics", "policy simulation", "approval gate", "postmortem notes"],
            "approval_gate": "required for remediation commands",
            "notification": "room + comms bridge",
            "audit_export": "meeting artifact + Executive Guardian journal",
        },
    ]


def evaluation_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    shell = policy.simulate_tool_policy("shell_run", {"command": "git commit -m update"})
    cases.append(
        {
            "id": "write_shell_requires_confirmation",
            "expected": "confirm",
            "actual": shell["decision"]["action"],
            "passed": shell["decision"]["action"] == "confirm",
        }
    )
    unknown = policy.simulate_tool_policy("unknown_tool", {})
    cases.append(
        {
            "id": "unknown_tool_denied",
            "expected": "deny",
            "actual": unknown["decision"]["action"],
            "passed": unknown["decision"]["action"] == "deny",
        }
    )
    guardrail = tool_guardrails.validate_tool_input("gmail_send", {"to": "a@example.com", "body": ""})
    cases.append(
        {
            "id": "empty_email_body_rejected",
            "expected": "rejectContent",
            "actual": guardrail.behavior,
            "passed": not guardrail.allowed,
        }
    )
    agents = get_all_agents()
    cases.append(
        {
            "id": "built_in_researcher_enabled",
            "expected": "enabled",
            "actual": "enabled" if agent_is_enabled("researcher") else "disabled",
            "passed": "researcher" in agents and agent_is_enabled("researcher"),
        }
    )
    return cases


def evaluation_summary() -> dict[str, Any]:
    cases = evaluation_cases()
    passed = sum(1 for case in cases if case["passed"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
    }
