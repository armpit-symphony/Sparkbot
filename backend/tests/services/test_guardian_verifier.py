from app.services.guardian.verifier import verify_task_run


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
