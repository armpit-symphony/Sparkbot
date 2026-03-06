from pathlib import Path

from app.services.guardian import memory


def _reset_memory_guardian(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_DATA_DIR", str(tmp_path / "memory_guardian"))
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS", "1200")
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT", "6")
    memory._guardian.cache_clear()


def test_memory_guardian_builds_context_and_clears_user_events(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    assert memory.remember_fact(user_id="user-1", fact="User prefers boring progressive growth.", memory_id="mem-1")
    assert memory.remember_chat_message(
        user_id="user-1",
        room_id="room-1",
        role="user",
        content="Please keep me focused on steady infrastructure growth.",
    )
    assert memory.remember_tool_event(
        user_id="user-1",
        room_id="room-1",
        tool_name="web_search",
        args={"query": "steady infrastructure growth"},
        result="No sensitive data here.",
    )

    context = memory.build_memory_context(
        user_id="user-1",
        room_id="room-1",
        query="What is the user focused on?",
    )

    assert "Durable Memory" in context
    assert "Relevant Room Memory" in context

    cleared = memory.clear_user_memory_events(user_id="user-1")
    assert cleared >= 2

    empty_context = memory.build_memory_context(
        user_id="user-1",
        room_id="room-1",
        query="What is the user focused on?",
    )
    assert empty_context == ""


def test_delete_fact_memory_removes_only_matching_fact(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    memory.remember_fact(user_id="user-1", fact="User prefers Python.", memory_id="mem-1")
    memory.remember_fact(user_id="user-1", fact="User prefers calm workflows.", memory_id="mem-2")

    removed = memory.delete_fact_memory(user_id="user-1", memory_id="mem-1")
    assert removed == 1

    context = memory.build_memory_context(
        user_id="user-1",
        room_id="room-1",
        query="What preferences does the user have?",
    )
    assert "Python" not in context
    assert "calm workflows" in context
