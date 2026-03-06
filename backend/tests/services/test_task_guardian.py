import importlib


def _reload_task_guardian(monkeypatch, tmp_path):
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))
    import app.services.guardian.task_guardian as task_guardian

    return importlib.reload(task_guardian)


def test_task_guardian_schedule_and_list(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    scheduled = task_guardian.schedule_task(
        name="Inbox digest",
        tool_name="gmail_fetch_inbox",
        tool_args={"max_emails": 3, "unread_only": True},
        schedule="every:3600",
        room_id="room-123",
        user_id="user-123",
    )

    tasks = task_guardian.list_tasks(room_id="room-123")
    assert scheduled["id"]
    assert len(tasks) == 1
    assert tasks[0].id == scheduled["id"]
    assert tasks[0].tool_name == "gmail_fetch_inbox"


def test_task_guardian_rejects_non_allowlisted_tool(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    try:
        task_guardian.schedule_task(
            name="Unsafe write",
            tool_name="gmail_send",
            tool_args={"to": "x@example.com"},
            schedule="every:3600",
            room_id="room-123",
            user_id="user-123",
        )
    except ValueError as exc:
        assert "approved read-only tools" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-allowlisted task tool")
