from pathlib import Path

from app.services.guardian import memory
from app.services.guardian import improvement


def _reset_memory_guardian(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_DATA_DIR", str(tmp_path / "memory_guardian"))
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS", "1200")
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT", "6")
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_DATA_DIR", str(tmp_path / "improvement_loop"))
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


def test_memory_guardian_builds_learned_profile_and_workflow_summary(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    assert memory.remember_chat_message(
        user_id="user-1",
        room_id="room-1",
        role="user",
        content="Call me Phil. I prefer Python over JavaScript.",
    )
    assert memory.remember_chat_message(
        user_id="user-1",
        room_id="room-1",
        role="user",
        content="I'm working on Sparkbot memory quality this week.",
    )
    assert memory.remember_tool_event(
        user_id="user-1",
        room_id="room-1",
        tool_name="github_get_pr",
        args={"repo": "sparkpitlabs/sparkbot", "pr_number": 42},
        result="Reviewed PR 42 successfully.",
    )

    context = memory.build_memory_context(
        user_id="user-1",
        room_id="room-1",
        query="How should I help this user right now?",
    )

    assert "Learned User Profile" in context
    assert "User goes by Phil" in context
    assert "User prefers Python over JavaScript" in context
    assert "Active Workflow Memory" in context
    assert "GitHub PR review x1" in context
    assert "Sparkbot memory quality this week" in context


def test_memory_guardian_redacts_sensitive_content_from_context(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    sensitive_message = (
        "My phone number is 631-383-0368 and my email is phil@example.com. "
        "My api key is sk-1234567890abcdefghijklmnop."
    )
    assert memory.remember_chat_message(
        user_id="user-1",
        room_id="room-1",
        role="user",
        content=sensitive_message,
    )

    context = memory.build_memory_context(
        user_id="user-1",
        room_id="room-1",
        query="What contact details did the user share?",
    )

    assert "631-383-0368" not in context
    assert "phil@example.com" not in context
    assert "sk-1234567890abcdefghijklmnop" not in context
    assert "[REDACTED_PHONE]" in context
    assert "[REDACTED_EMAIL]" in context
    assert "[REDACTED_TOKEN]" in context


def test_memory_guardian_includes_promoted_workflow_patterns(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    improvement.record_outcome(
        user_id="user-1",
        room_id="room-1",
        route_payload={
            "classification": "coding",
            "applied_model": "ollama/qwen2:latest",
            "fallback_triggered": False,
        },
        output_text="Implemented a durable parser and verified the result.",
        tool_usage_counts={"github_get_pr": 1},
        success=True,
        agent_name="sparkbot",
    )

    context = memory.build_memory_context(
        user_id="user-1",
        room_id="room-1",
        query="How should I handle coding work here?",
    )

    assert "Promoted Workflow Patterns" in context
    assert "ollama/qwen2:latest" in context
    assert "github get pr" in context.lower()
