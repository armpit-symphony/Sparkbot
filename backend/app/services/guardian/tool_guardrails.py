from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_SECRET_KEY_RE = re.compile(r"(token|secret|password|credential|api[_-]?key|private[_-]?key)", re.IGNORECASE)


@dataclass(frozen=True)
class ToolGuardrailResult:
    allowed: bool
    phase: str
    tool_name: str
    behavior: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "phase": self.phase,
            "tool_name": self.tool_name,
            "behavior": self.behavior,
            "reason": self.reason,
        }


def _reject(tool_name: str, phase: str, reason: str) -> ToolGuardrailResult:
    return ToolGuardrailResult(
        allowed=False,
        phase=phase,
        tool_name=tool_name,
        behavior="rejectContent",
        reason=reason,
    )


def _allow(tool_name: str, phase: str, reason: str = "Guardrail checks passed.") -> ToolGuardrailResult:
    return ToolGuardrailResult(
        allowed=True,
        phase=phase,
        tool_name=tool_name,
        behavior="allow",
        reason=reason,
    )


def validate_tool_input(tool_name: str, args: dict[str, Any] | None) -> ToolGuardrailResult:
    """Run per-tool preflight checks before execution.

    These checks are intentionally narrow and deterministic. Policy decides who
    may run a tool; guardrails validate the specific payload shape and prevent
    obviously unsafe accidental payloads from reaching tools.
    """
    args = args or {}
    if not isinstance(args, dict):
        return _reject(tool_name, "input", "Tool arguments must be a JSON object.")

    for key in args:
        if _SECRET_KEY_RE.search(str(key)) and tool_name not in {"vault_add_secret", "vault_update_secret"}:
            return _reject(
                tool_name,
                "input",
                f"Argument '{key}' looks like a secret. Store secrets in Guardian Vault instead of passing them to tools.",
            )

    if tool_name == "shell_run" and not str(args.get("command") or "").strip():
        return _reject(tool_name, "input", "shell_run requires a non-empty command.")
    if tool_name in {"gmail_send", "email_send"}:
        if not str(args.get("to") or "").strip():
            return _reject(tool_name, "input", f"{tool_name} requires a recipient.")
        if not str(args.get("body") or "").strip():
            return _reject(tool_name, "input", f"{tool_name} requires a non-empty body.")
    if tool_name in {"slack_send_message", "telegram_send_message", "discord_send_message", "whatsapp_send_message"}:
        if not str(args.get("message") or args.get("text") or "").strip():
            return _reject(tool_name, "input", f"{tool_name} requires a non-empty message.")
    if tool_name in {"calendar_create_event", "outlook_calendar_create"}:
        if not str(args.get("title") or args.get("summary") or "").strip():
            return _reject(tool_name, "input", f"{tool_name} requires a title.")
        if not (args.get("start") or args.get("start_time")):
            return _reject(tool_name, "input", f"{tool_name} requires a start time.")
    return _allow(tool_name, "input")


def validate_tool_output(tool_name: str, output: str, *, high_risk: bool = False) -> ToolGuardrailResult:
    """Run deterministic checks on tool output before it is shown or stored."""
    text = str(output or "")
    if _SECRET_KEY_RE.search(text) and high_risk:
        return _reject(tool_name, "output", "High-risk tool output appears to contain secret-like material.")
    if len(text) > 60_000:
        return _reject(tool_name, "output", "Tool output is unexpectedly large and should be summarized before use.")
    return _allow(tool_name, "output")
