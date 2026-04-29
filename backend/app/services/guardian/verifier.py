from __future__ import annotations

import re
from dataclasses import dataclass

_FAILURE_MARKERS = (
    "failed:",
    "error:",
    "unknown tool:",
    "not configured",
    "not allowed",
    "missing required field",
    "timed out",
    "command failed",
    "access denied",
    "invalid ",
)
_NO_RESULT_MARKERS = (
    "no results",
    "no open",
    "no pending",
    "no reminders",
    "no tasks",
    "no emails",
    "no messages",
    "no upcoming",
    "no matching",
    "0 unread",
)
_WRITE_SUCCESS_MARKERS: dict[str, tuple[str, ...]] = {
    "browser_click": ("clicked", "now at:", "navigation"),
    "gmail_send": ("sent", "email sent"),
    "slack_send_message": ("posted", "message sent", "sent to"),
    "calendar_create_event": ("event created", "created:"),
    "email_send": ("sent", "email sent"),
    "github_create_issue": ("issue created", "created issue", "opened issue"),
    "notion_create_page": ("page created", "created page"),
    "confluence_create_page": ("page created", "created page"),
    "drive_create_folder": ("folder created", "created folder"),
    "server_manage_service": ("started", "stopped", "restarted", "active:", "status:", "logs for"),
}
_STRICT_READ_TOOLS = {
    "web_search",
    "gmail_fetch_inbox",
    "gmail_search",
    "drive_search",
    "calendar_list_events",
    "github_list_prs",
    "github_get_pr",
    "github_get_ci_status",
    "notion_search",
    "confluence_search",
    "server_read_command",
    "ssh_read_command",
    "list_tasks",
    "list_reminders",
    "morning_briefing",
    "retrieval_eval",
    "memory_guardian_nightly",
}
_INTERACTIVE_VERIFY_ACTION_TYPES = {
    "write_external",
    "service_control",
    "command_exec",
    "ssh_exec",
    "vault_write",
    "vault_reveal",
}
_SECRET_EVIDENCE_TOOLS = {
    "vault_use_secret",
    "vault_reveal_secret",
    "vault_add_secret",
    "vault_update_secret",
    "vault_delete_secret",
}
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_SECRET_FACT_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|credential|private[_-]?key|passphrase)",
    re.IGNORECASE,
)
_FACT_UNCERTAINTY_RE = re.compile(
    r"\b(maybe|possibly|probably|i think|not sure|might|could be|guess)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VerificationResult:
    status: str
    confidence: float
    summary: str
    evidence: list[dict[str, str]]
    recommended_next_action: str | None = None


def _clean_lines(output: str, limit: int = 3) -> list[str]:
    lines: list[str] = []
    for line in (output or "").splitlines():
        cleaned = " ".join(line.split()).strip()
        if not cleaned:
            continue
        if cleaned not in lines:
            lines.append(cleaned[:220])
        if len(lines) >= limit:
            break
    return lines


def _evidence_from_output(output: str, limit: int = 3) -> list[dict[str, str]]:
    return [{"type": "tool_output", "detail": line} for line in _clean_lines(output, limit=limit)]


def should_verify_interactive_tool_run(*, action_type: str, high_risk: bool) -> bool:
    return bool(high_risk or action_type in _INTERACTIVE_VERIFY_ACTION_TYPES)


def format_verifier_note(verification: VerificationResult) -> str:
    note = (
        f"Verifier status: {verification.status.upper()} "
        f"(confidence {verification.confidence:.2f}). {verification.summary}"
    )
    if verification.recommended_next_action:
        note += f" Next action: {verification.recommended_next_action}"
    return note


def _verify_run(
    *,
    subject_label: str,
    tool_name: str,
    output: str,
    execution_status: str,
    allow_output_evidence: bool = True,
) -> VerificationResult:
    text = (output or "").strip()
    lowered = text.lower()
    evidence = _evidence_from_output(text) if allow_output_evidence else []

    if execution_status == "denied":
        return VerificationResult(
            status="blocked",
            confidence=1.0,
            summary=f"{subject_label} was blocked before execution.",
            evidence=evidence or [{"type": "policy", "detail": text[:220] or "Execution denied"}],
            recommended_next_action="Review Guardian policy or pre-authorize the task before retrying.",
        )

    if not text:
        return VerificationResult(
            status="unverified",
            confidence=0.2,
            summary=f"{subject_label} produced no verifiable output.",
            evidence=[],
            recommended_next_action="Add a stronger verifier or inspect the target system directly before trusting this task.",
        )

    if any(marker in lowered for marker in _FAILURE_MARKERS):
        return VerificationResult(
            status="failed",
            confidence=0.98,
            summary=f"{subject_label} failed according to tool output.",
            evidence=evidence,
            recommended_next_action="Inspect the error output, correct the configuration or command, and rerun.",
        )

    if tool_name in _WRITE_SUCCESS_MARKERS:
        markers = _WRITE_SUCCESS_MARKERS[tool_name]
        if any(marker in lowered for marker in markers):
            return VerificationResult(
                status="verified",
                confidence=0.93,
                summary=f"{subject_label} completed with explicit write confirmation.",
                evidence=evidence,
            )
        return VerificationResult(
            status="unverified",
            confidence=0.45,
            summary=f"{subject_label} ran, but the write result lacked explicit confirmation.",
            evidence=evidence,
            recommended_next_action="Verify the external system changed state before treating this as complete.",
        )

    if tool_name == "web_search":
        has_provider = "search provider:" in lowered
        has_link = bool(_URL_RE.search(text))
        if has_provider and (has_link or len(evidence) >= 2):
            return VerificationResult(
                status="verified",
                confidence=0.91,
                summary=f"{subject_label} returned live search evidence.",
                evidence=evidence,
            )
        return VerificationResult(
            status="unverified",
            confidence=0.4,
            summary=f"{subject_label} ran, but search evidence was too weak to trust automatically.",
            evidence=evidence,
            recommended_next_action="Inspect the search output manually or tighten the search query/verifier.",
        )

    if tool_name in _STRICT_READ_TOOLS:
        if evidence:
            return VerificationResult(
                status="verified",
                confidence=0.87 if any(marker in lowered for marker in _NO_RESULT_MARKERS) else 0.9,
                summary=f"{subject_label} returned readable evidence from `{tool_name}`.",
                evidence=evidence,
            )
        return VerificationResult(
            status="unverified",
            confidence=0.35,
            summary=f"{subject_label} ran, but no readable evidence was captured.",
            evidence=[],
            recommended_next_action="Strengthen the verifier or collect an explicit status check after the tool call.",
        )

    return VerificationResult(
        status="unverified",
        confidence=0.3,
        summary=f"{subject_label} ran, but `{tool_name}` has no verifier profile yet.",
        evidence=evidence,
        recommended_next_action="Add a verifier profile for this tool before trusting autonomous completion.",
    )


def verify_task_run(
    *,
    task_name: str,
    tool_name: str,
    output: str,
    execution_status: str,
) -> VerificationResult:
    return _verify_run(
        subject_label=f"Task '{task_name}'",
        tool_name=tool_name,
        output=output,
        execution_status=execution_status,
        allow_output_evidence=tool_name not in _SECRET_EVIDENCE_TOOLS,
    )


def verify_fact(
    *,
    fact: str,
    source: str = "memory",
    confidence: float = 0.5,
) -> VerificationResult:
    """Verify whether a proposed durable memory fact is safe to promote."""
    cleaned = " ".join((fact or "").split()).strip()
    if not cleaned:
        return VerificationResult(
            status="failed",
            confidence=1.0,
            summary="Fact promotion rejected because the fact was empty.",
            evidence=[],
            recommended_next_action="Do not store empty facts.",
        )
    if len(cleaned) > 500:
        return VerificationResult(
            status="failed",
            confidence=0.95,
            summary="Fact promotion rejected because the fact was too long for durable memory.",
            evidence=[{"type": "memory_source", "detail": source}],
            recommended_next_action="Store a shorter, user-approved summary instead.",
        )
    if _SECRET_FACT_RE.search(cleaned):
        return VerificationResult(
            status="blocked",
            confidence=0.98,
            summary="Fact promotion blocked because the text appears to contain secret material.",
            evidence=[{"type": "memory_source", "detail": source}],
            recommended_next_action="Do not promote secrets into long-term memory.",
        )
    if confidence < 0.75 or _FACT_UNCERTAINTY_RE.search(cleaned):
        return VerificationResult(
            status="unverified",
            confidence=max(0.2, min(float(confidence), 0.74)),
            summary="Fact promotion needs human approval before it becomes durable memory.",
            evidence=[{"type": "memory_source", "detail": source}],
            recommended_next_action="Create a pending approval and only promote after confirmation.",
        )
    return VerificationResult(
        status="verified",
        confidence=max(0.75, min(float(confidence), 1.0)),
        summary="Fact is safe to promote to durable memory.",
        evidence=[{"type": "memory_source", "detail": source}],
    )


def verify_interactive_tool_run(
    *,
    tool_name: str,
    output: str,
    execution_status: str,
) -> VerificationResult:
    return _verify_run(
        subject_label=f"Interactive action `{tool_name}`",
        tool_name=tool_name,
        output=output,
        execution_status=execution_status,
        allow_output_evidence=tool_name not in _SECRET_EVIDENCE_TOOLS,
    )
