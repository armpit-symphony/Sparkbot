from app.services.guardian.verifier import (
    format_verifier_note,
    should_verify_interactive_tool_run,
    verify_interactive_tool_run,
    verify_task_run,
)


def test_verifier_marks_read_task_as_verified_when_evidence_exists() -> None:
    result = verify_task_run(
        task_name="Inbox digest",
        tool_name="gmail_fetch_inbox",
        output="Unread inbox (2)\n- Alice: Status update\n- Bob: Infra check",
        execution_status="success",
    )

    assert result.status == "verified"
    assert result.confidence >= 0.85
    assert result.evidence


def test_verifier_marks_denied_task_as_blocked() -> None:
    result = verify_task_run(
        task_name="Send update",
        tool_name="gmail_send",
        output="Scheduled tasks cannot run confirm-required tools without pre-authorization.",
        execution_status="denied",
    )

    assert result.status == "blocked"
    assert result.recommended_next_action


def test_verifier_requires_explicit_confirmation_for_write_tools() -> None:
    result = verify_task_run(
        task_name="Create event",
        tool_name="calendar_create_event",
        output="Queued request for event update",
        execution_status="success",
    )

    assert result.status == "unverified"
    assert result.recommended_next_action


def test_verifier_recognizes_explicit_write_success() -> None:
    result = verify_task_run(
        task_name="Create event",
        tool_name="calendar_create_event",
        output="Event created: 'Standup' on 2026-03-10 15:00 UTC",
        execution_status="success",
    )

    assert result.status == "verified"
    assert result.confidence >= 0.9


def test_interactive_verifier_marks_high_risk_write_without_confirmation_as_unverified() -> None:
    result = verify_interactive_tool_run(
        tool_name="github_create_issue",
        output="Queued request to create issue",
        execution_status="success",
    )

    assert result.status == "unverified"
    assert "explicit confirmation" in result.summary.lower()


def test_interactive_verifier_gate_and_note_format() -> None:
    assert should_verify_interactive_tool_run(action_type="write_external", high_risk=True) is True

    result = verify_interactive_tool_run(
        tool_name="server_manage_service",
        output="Service status: active: running",
        execution_status="success",
    )

    note = format_verifier_note(result)
    assert result.status == "verified"
    assert "Verifier status: VERIFIED" in note
