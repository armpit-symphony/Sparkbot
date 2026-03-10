import importlib
import asyncio
import uuid


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
        assert "Task Guardian does not allow 'gmail_send'" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-allowlisted task tool")


def test_task_guardian_records_verified_run(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    room_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    scheduled = task_guardian.schedule_task(
        name="PR digest",
        tool_name="github_list_prs",
        tool_args={"repo": "sparkpitlabs/sparkbot", "state": "open"},
        schedule="every:3600",
        room_id=room_id,
        user_id=user_id,
    )
    task = task_guardian.get_task(scheduled["id"])
    assert task is not None

    async def _fake_execute(_task, _session):
        return "success", "Open PRs\n- #42 Improve memory verifier\n- #43 Fix release docs"

    class _FakeBot:
        id = "bot-user"

    monkeypatch.setattr(task_guardian, "_execute_internal_tool", _fake_execute)
    monkeypatch.setattr(task_guardian, "_find_or_create_bot_user", lambda _session: _FakeBot())
    monkeypatch.setattr(task_guardian, "create_chat_message", lambda **kwargs: type("Msg", (), {"id": "msg-1"})())
    monkeypatch.setattr(task_guardian, "create_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(task_guardian, "remember_tool_event", lambda **kwargs: None)

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(task_guardian, "_broadcast_task_message", _noop)

    result = asyncio.run(task_guardian.run_task_once(task, object()))
    runs = task_guardian.list_runs(room_id=room_id)
    refreshed = task_guardian.get_task(task.id)

    assert result["status"] == "verified"
    assert result["verification_status"] == "verified"
    assert runs[0].verification_status == "verified"
    assert runs[0].confidence is not None
    assert refreshed is not None
    assert refreshed.last_status == "verified"
    assert refreshed.last_verification_status == "verified"


def test_task_guardian_retries_then_escalates_unverified_runs(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SPARKBOT_TASK_GUARDIAN_MAX_RETRIES", "2")
    monkeypatch.setenv("SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED", "true")
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    room_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    scheduled = task_guardian.schedule_task(
        name="Send summary",
        tool_name="gmail_send",
        tool_args={"to": "ops@example.com"},
        schedule="every:3600",
        room_id=room_id,
        user_id=user_id,
    )
    task = task_guardian.get_task(scheduled["id"])
    assert task is not None

    async def _fake_execute(_task, _session):
        return "success", "Queued request for outbound email"

    class _FakeBot:
        id = "bot-user"

    monkeypatch.setattr(task_guardian, "_execute_internal_tool", _fake_execute)
    monkeypatch.setattr(task_guardian, "_find_or_create_bot_user", lambda _session: _FakeBot())
    monkeypatch.setattr(task_guardian, "create_chat_message", lambda **kwargs: type("Msg", (), {"id": "msg-1"})())
    monkeypatch.setattr(task_guardian, "create_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(task_guardian, "remember_tool_event", lambda **kwargs: None)

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(task_guardian, "_broadcast_task_message", _noop)

    first = asyncio.run(task_guardian.run_task_once(task, object()))
    after_first = task_guardian.get_task(task.id)
    assert first["status"] == "unverified"
    assert first["escalated"] is False
    assert first["next_run_at"] is not None
    assert after_first is not None
    assert after_first.consecutive_failures == 1
    assert bool(after_first.enabled) is True

    second = asyncio.run(task_guardian.run_task_once(after_first, object()))
    after_second = task_guardian.get_task(task.id)
    assert second["status"] == "unverified"
    assert second["escalated"] is True
    assert second["next_run_at"] is None
    assert after_second is not None
    assert after_second.consecutive_failures == 2
    assert bool(after_second.enabled) is False
    assert after_second.escalated_at is not None
