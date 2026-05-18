import importlib
import asyncio
import uuid
from datetime import datetime, timezone


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


def test_task_guardian_allows_meeting_heartbeat(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    scheduled = task_guardian.schedule_task(
        name="Roundtable heartbeat",
        tool_name="meeting_heartbeat",
        tool_args={},
        schedule="every:3600",
        room_id="room-123",
        user_id="user-123",
    )

    task = task_guardian.get_task(scheduled["id"])
    assert task is not None
    assert task.tool_name == "meeting_heartbeat"


def test_task_guardian_allows_memory_guardian_nightly(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    scheduled = task_guardian.schedule_task(
        name="Nightly memory verification",
        tool_name="memory_guardian_nightly",
        tool_args={},
        schedule="daily:03:10",
        room_id="room-123",
        user_id="user-123",
    )

    task = task_guardian.get_task(scheduled["id"])
    assert task is not None
    assert task.tool_name == "memory_guardian_nightly"


def test_task_guardian_exposes_health_check_templates(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    templates = task_guardian.list_builtin_templates()
    by_id = {template["id"]: template for template in templates}

    assert set(by_id) == {"pc_health_check", "server_health_check"}
    assert by_id["pc_health_check"]["tool_name"] == "sparkbot_health_check"
    assert by_id["server_health_check"]["tool_name"] == "sparkbot_health_check"
    assert by_id["pc_health_check"]["schedule"] == "daily-local:06:00"
    assert by_id["server_health_check"]["enabled"] is False
    assert by_id["pc_health_check"]["tool_args"]["delivery_channels"] == ["app"]


def test_task_guardian_allows_disabled_health_check_template(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    scheduled = task_guardian.schedule_task(
        name="PC Health Check",
        tool_name="sparkbot_health_check",
        tool_args={"mode": "pc", "delivery_channels": ["app"]},
        schedule="daily-local:06:00",
        room_id="room-123",
        user_id="user-123",
        enabled=False,
    )

    task = task_guardian.get_task(scheduled["id"])
    assert task is not None
    assert task.tool_name == "sparkbot_health_check"
    assert bool(task.enabled) is False
    assert scheduled["enabled"] is False


def test_task_guardian_daily_schedule_calculates_next_utc_run(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    base = datetime(2026, 4, 24, 12, 30, tzinfo=timezone.utc)

    assert task_guardian._next_run_at("daily:13:00", base=base) == "2026-04-24T13:00:00+00:00"
    assert task_guardian._next_run_at("daily:09:00", base=base) == "2026-04-25T09:00:00+00:00"


def test_task_guardian_daily_local_schedule_calculates_utc_run(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    base = datetime(2026, 4, 24, 12, 30, tzinfo=timezone.utc)
    next_run = datetime.fromisoformat(task_guardian._next_run_at("daily-local:06:00", base=base))

    assert next_run.tzinfo is not None
    assert next_run > base


def test_task_guardian_at_schedule_accepts_zulu_timestamp(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    assert task_guardian._next_run_at("at:2026-04-24T14:00:00Z") == "2026-04-24T14:00:00+00:00"


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


def test_task_guardian_health_run_writes_source_labeled_memory(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    room_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    scheduled = task_guardian.schedule_task(
        name="PC Health Check",
        tool_name="sparkbot_health_check",
        tool_args={"mode": "pc", "delivery_channels": ["app"]},
        schedule="daily-local:06:00",
        room_id=room_id,
        user_id=user_id,
    )
    task = task_guardian.get_task(scheduled["id"])
    assert task is not None

    async def _fake_health(args, **kwargs):
        return {
            "report": "Sparkbot Health Report - now\n\nSEV-1 Assessment:\nNONE\n\nSystem Status:\nNominal (PC)\n\nNo action required.",
            "status": "Nominal",
            "source_label": "task_guardian.health.pc",
        }

    class _FakeBot:
        id = "bot-user"

    remembered: list[dict] = []
    monkeypatch.setattr(task_guardian, "run_health_check", _fake_health)
    monkeypatch.setattr(task_guardian, "_find_or_create_bot_user", lambda _session: _FakeBot())
    monkeypatch.setattr(task_guardian, "create_chat_message", lambda **kwargs: type("Msg", (), {"id": "msg-1"})())
    monkeypatch.setattr(task_guardian, "create_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(task_guardian, "remember_tool_event", lambda **kwargs: remembered.append(kwargs))

    async def _noop(*args, **kwargs):
        return None

    async def _no_delivery(*args, **kwargs):
        return []

    monkeypatch.setattr(task_guardian, "_broadcast_task_message", _noop)
    monkeypatch.setattr(task_guardian, "_deliver_task_notifications", _no_delivery)

    result = asyncio.run(task_guardian.run_task_once(task, object()))

    assert result["status"] == "verified"
    assert remembered
    assert remembered[0]["tool_name"] == "task_guardian.health.pc"


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


def test_task_guardian_disables_terminal_meeting_heartbeat(monkeypatch, tmp_path) -> None:
    task_guardian = _reload_task_guardian(monkeypatch, tmp_path)

    room_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    scheduled = task_guardian.schedule_task(
        name="Roundtable heartbeat",
        tool_name="meeting_heartbeat",
        tool_args={},
        schedule="every:3600",
        room_id=room_id,
        user_id=user_id,
    )
    task = task_guardian.get_task(scheduled["id"])
    assert task is not None

    async def _fake_execute(_task, _session):
        return "success", (
            '{"tool":"meeting_heartbeat","heartbeat_status":"recommendation_ready",'
            '"summary":"Heartbeat reached a recommendation.","terminal":true}'
        )

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
    refreshed = task_guardian.get_task(task.id)

    assert result["status"] == "recommendation_ready"
    assert result["verification_status"] == "verified"
    assert result["enabled"] is False
    assert result["next_run_at"] is None
    assert refreshed is not None
    assert bool(refreshed.enabled) is False
    assert refreshed.next_run_at is None
