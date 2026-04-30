import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, delete, select

from app import crud
from app.models import AuditLog, UserMemory
from app.services.guardian import improvement, memory
from app.services.guardian.memory_hygiene import run_memory_hygiene
from app.services.guardian.memory_taxonomy import (
    classify_memory_type,
    should_index_memory_candidate,
)


def _reset_memory_guardian(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_DATA_DIR", str(tmp_path / "memory_guardian"))
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS", "1200")
    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT", "6")
    monkeypatch.delenv("SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS", raising=False)
    monkeypatch.delenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVER", raising=False)
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_DATA_DIR", str(tmp_path / "improvement_loop"))
    memory._guardian.cache_clear()
    memory._SNAPSHOT_STATE.clear()


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

    events = list(memory._guardian().ledger.iter_events())
    assert events[-1].metadata["candidate_reason"] == "secret_blocked"
    assert "[REDACTED_PHONE]" in events[-1].content
    assert "[REDACTED_EMAIL]" in events[-1].content
    assert "[REDACTED_TOKEN]" in events[-1].content
    assert "631-383-0368" not in context
    assert "phil@example.com" not in context
    assert "sk-1234567890abcdefghijklmnop" not in context
    assert context == ""


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


def test_memory_guardian_defaults_to_bm25_and_requires_embedding_flag(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    assert memory._embeddings_enabled() is False
    assert memory._retriever_mode() == "fts"

    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVER", "hybrid")
    assert memory._retriever_mode() == "fts"

    monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS", "true")
    assert memory._embeddings_enabled() is True
    assert memory._retriever_mode() == "hybrid"


def test_low_confidence_fact_creates_pending_approval(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)
    calls = []

    def _fake_store_pending_approval(**kwargs):
        calls.append(kwargs)

    import app.services.guardian.pending_approvals as pending_approvals

    monkeypatch.setattr(pending_approvals, "store_pending_approval", _fake_store_pending_approval)

    stored = memory.remember_fact(
        user_id="user-1",
        fact="Maybe the user prefers release notes on Fridays.",
        confidence=0.4,
        source="fact.inferred",
    )

    assert stored is False
    assert calls
    assert calls[0]["tool_name"] == "memory_fact_promotion"
    assert calls[0]["tool_args"]["verification_state"] == "unverified"


def test_memory_candidate_filtering_keeps_ack_out_of_indexes(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    assert memory.remember_chat_message(user_id="user-1", room_id="room-1", role="user", content="ok")
    guardian = memory._guardian()
    events = list(guardian.ledger.iter_events(session_id=memory._room_session("user-1", "room-1")))

    assert events
    assert events[-1].content == "ok"
    assert events[-1].metadata["candidate_indexed"] is False
    assert guardian.fts.search("ok", session_id=memory._room_session("user-1", "room-1")) == []
    assert should_index_memory_candidate({"role": "user", "content": "thanks", "metadata": {}}) == (
        False,
        "do_not_store",
    )


def test_memory_type_classifier_core_cases() -> None:
    assert classify_memory_type("Remember that I prefer copy-paste Codex work orders") == "preference"
    assert classify_memory_type("My API key is sk-1234567890abcdefghijklmnop") == "secret_blocked"
    assert classify_memory_type("Port 3001 is already in use") == "debug_state"
    assert classify_memory_type("We decided Sparky handles server actions") == "project_decision"


def test_secret_fact_is_blocked_from_durable_memory(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    stored = memory.remember_fact(
        user_id="user-1",
        fact="My API key is sk-1234567890abcdefghijklmnop",
        memory_id="mem-secret",
    )

    assert stored is False
    assert not any("FACT:" in event.content for event in memory._guardian().ledger.iter_events())


def test_archived_ledger_memory_excluded_from_context(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)

    assert memory._append_event(
        event_type=memory.EventType.SYSTEM,
        role="system",
        content="FACT: User prefers active memory.",
        session_id=memory._user_session("user-1"),
        metadata={"user_id": "user-1", "memory_id": "active", "lifecycle_state": "active"},
        source="fact.user_authored",
        confidence=0.95,
        verification_state="verified",
    )
    assert memory._append_event(
        event_type=memory.EventType.SYSTEM,
        role="system",
        content="FACT: User prefers archived memory.",
        session_id=memory._user_session("user-1"),
        metadata={"user_id": "user-1", "memory_id": "archived", "lifecycle_state": "archived"},
        source="fact.user_authored",
        confidence=0.95,
        verification_state="verified",
    )

    context = memory.build_memory_context(user_id="user-1", room_id="room-1", query="memory preference")

    assert "active memory" in context
    assert "archived memory" not in context


def test_snapshot_rebuild_is_throttled(monkeypatch, tmp_path: Path) -> None:
    _reset_memory_guardian(monkeypatch, tmp_path)
    monkeypatch.setenv("SPARKBOT_MEMORY_SNAPSHOT_REBUILD_EVERY_N", "10")
    monkeypatch.setenv("SPARKBOT_MEMORY_SNAPSHOT_REBUILD_MIN_SECONDS", "999999")

    assert memory.remember_chat_message(
        user_id="user-1",
        room_id="room-1",
        role="user",
        content="I prefer copy-paste Codex work orders 1.",
    )
    assert not memory._snapshot_path("user-1", "room-1").exists()

    for idx in range(2, 11):
        assert memory.remember_chat_message(
            user_id="user-1",
            room_id="room-1",
            role="user",
            content=f"I prefer copy-paste Codex work orders {idx}.",
        )

    assert memory._snapshot_path("user-1", "room-1").exists()


def test_hygiene_lifecycle_and_pinned_protection(db: Session) -> None:
    db.exec(delete(AuditLog))
    db.exec(delete(UserMemory))
    db.commit()
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    debug = crud.add_user_memory(db, user_id, "Port 3001 is already in use")
    debug.created_at = now - timedelta(days=20)
    debug.updated_at = now - timedelta(days=20)
    pinned = crud.add_user_memory(db, user_id, "Temporary context that should stay pinned")
    pinned.memory_type = "temporary_context"
    pinned.created_at = now - timedelta(days=200)
    pinned.updated_at = now - timedelta(days=200)
    pinned.pinned = True
    identity = crud.add_user_memory(db, user_id, "My name is Sparky")
    identity.memory_type = "identity"
    identity.created_at = now - timedelta(days=400)
    identity.updated_at = now - timedelta(days=400)
    db.add(debug)
    db.add(pinned)
    db.add(identity)
    db.commit()

    report = run_memory_hygiene(db, now=now)
    db.refresh(debug)
    db.refresh(pinned)
    db.refresh(identity)

    assert report.scanned_count == 3
    assert debug.lifecycle_state == "archived"
    assert pinned.lifecycle_state == "active"
    assert identity.lifecycle_state == "active"
    assert report.skipped_pinned_count == 1
    assert report.skipped_protected_count == 1


def test_deletion_approval_is_soft_delete_and_audited(db: Session) -> None:
    db.exec(delete(AuditLog))
    db.exec(delete(UserMemory))
    db.commit()
    user_id = uuid.uuid4()
    mem = crud.add_user_memory(db, user_id, "Remember that I prefer governed memory cleanup")

    assert crud.propose_delete_memory(db, mem.id, "unused test memory", operator_id="operator")
    db.refresh(mem)
    assert mem.lifecycle_state == "delete_proposed"
    assert crud.approve_delete_memory(db, mem.id, operator_id="operator")
    db.refresh(mem)
    assert mem.lifecycle_state == "soft_deleted"
    assert mem.soft_deleted_at is not None
    assert crud.get_user_memories(db, user_id) == []
    assert crud.restore_soft_deleted_memory(db, mem.id, operator_id="operator")
    db.refresh(mem)
    assert mem.lifecycle_state == "archived"

    audit_names = [row.tool_name for row in db.exec(select(AuditLog)).all()]
    assert "memory_delete_proposed" in audit_names
    assert "memory_soft_delete" in audit_names
    assert "memory_restore" in audit_names


def test_memory_usage_counts_increment_only_on_injection(db: Session) -> None:
    db.exec(delete(UserMemory))
    db.commit()
    user_id = uuid.uuid4()
    mem = crud.add_user_memory(db, user_id, "Remember that I prefer retrieval accounting")

    assert crud.mark_memory_retrieved(db, mem.id, user_id=user_id)
    db.refresh(mem)
    assert mem.last_retrieved_at is not None
    assert mem.use_count == 0

    assert crud.mark_memory_injected(db, mem.id, user_id=user_id)
    db.refresh(mem)
    assert mem.last_injected_at is not None
    assert mem.last_used_at is not None
    assert mem.use_count == 1
