"""Security tests for Guardian subsystem — extraction gate requirement.

These tests verify that secret-like data is redacted before persistence,
authorization gates reject unauthorized access, and write-mode controls
function correctly. All tests must pass before LIMA extraction proceeds.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── RISK-1: Pending approvals redact tool_args in Spine event payloads ────────


class TestPendingApprovalSpineRedaction:
    def test_store_redacts_secret_keys_in_spine_event(self, monkeypatch, tmp_path):
        """Verify _redact_tool_args_for_event redacts secret-keyed args before Spine emission."""
        from app.services.guardian.pending_approvals import _redact_tool_args_for_event

        tool_args = {"alias": "smtp", "password": "hunter2", "api_key": "sk-live-xxx"}
        redacted = _redact_tool_args_for_event(tool_args)

        assert redacted["alias"] == "smtp"
        assert redacted["password"] == "[REDACTED]"
        assert redacted["api_key"] == "[REDACTED]"

    def test_consume_redacts_secret_keys_in_spine_event(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))

        captured_payloads: list[dict] = []

        def _capture_emit(**kwargs):
            captured_payloads.append(kwargs)

        monkeypatch.setattr(
            "app.services.guardian.spine.emit_approval_event",
            _capture_emit,
        )

        import app.services.guardian.pending_approvals as pa

        pa.store_pending_approval(
            confirm_id="test-2",
            tool_name="some_tool",
            tool_args={"password": "s3cret", "host": "db.example.com"},
            user_id="user-1",
            room_id="room-1",
        )
        captured_payloads.clear()

        pa.consume_pending_approval("test-2")

        assert captured_payloads
        event_tool_args = captured_payloads[0]["payload"]["tool_args"]
        assert event_tool_args["host"] == "db.example.com"
        assert event_tool_args["password"] == "[REDACTED]"

    def test_discard_redacts_secret_keys_in_spine_event(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))

        captured_payloads: list[dict] = []

        def _capture_emit(**kwargs):
            captured_payloads.append(kwargs)

        monkeypatch.setattr(
            "app.services.guardian.spine.emit_approval_event",
            _capture_emit,
        )

        import app.services.guardian.pending_approvals as pa

        pa.store_pending_approval(
            confirm_id="test-3",
            tool_name="some_tool",
            tool_args={"token": "abc123", "url": "https://example.com"},
            user_id="user-1",
            room_id="room-1",
        )
        captured_payloads.clear()

        pa.discard_pending_approval("test-3")

        assert captured_payloads
        event_tool_args = captured_payloads[0]["payload"]["tool_args"]
        assert event_tool_args["url"] == "https://example.com"
        assert event_tool_args["token"] == "[REDACTED]"

    def test_redact_preserves_non_secret_keys(self):
        from app.services.guardian.pending_approvals import _redact_tool_args_for_event

        args = {"to": "user@example.com", "subject": "Hello", "body": "world"}
        redacted = _redact_tool_args_for_event(args)
        assert redacted == args

    def test_redact_handles_none_and_empty(self):
        from app.services.guardian.pending_approvals import _redact_tool_args_for_event

        assert _redact_tool_args_for_event(None) == {}
        assert _redact_tool_args_for_event({}) == {}


# ── RISK-2: Executive JSONL redacts metadata and result_excerpt ───────────────


class TestExecutiveJSONLRedaction:
    def test_metadata_secrets_redacted_in_jsonl(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED", "true")
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))
        import app.services.guardian.executive as executive

        executive = importlib.reload(executive)

        result = asyncio.run(
            executive.exec_with_guard(
                tool_name="shell_run",
                action_type="command_exec",
                expected_outcome="Run command",
                perform_fn=lambda: "password=hunter2 done",
                metadata={"api_key": "sk-live-xxx", "host": "db.example.com"},
            )
        )

        assert result == "password=hunter2 done"

        log_dir = tmp_path / "guardian" / "executive" / "decisions"
        jsonl_files = list(log_dir.glob("*.jsonl"))
        assert jsonl_files
        entry = json.loads(jsonl_files[0].read_text().strip().split("\n")[-1])

        assert entry["metadata"]["api_key"] == "[REDACTED]"
        assert entry["metadata"]["host"] == "db.example.com"
        assert "hunter2" not in entry["result_excerpt"]
        assert "[REDACTED]" in entry["result_excerpt"]

    def test_exception_redacted_in_validation_note(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED", "true")
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))
        import app.services.guardian.executive as executive

        executive = importlib.reload(executive)

        def _boom():
            raise RuntimeError("Connection failed: password=s3cret host=db")

        with pytest.raises(RuntimeError):
            asyncio.run(
                executive.exec_with_guard(
                    tool_name="ssh_exec",
                    action_type="ssh_exec",
                    expected_outcome="SSH command",
                    perform_fn=_boom,
                )
            )

        log_dir = tmp_path / "guardian" / "executive" / "decisions"
        jsonl_files = list(log_dir.glob("*.jsonl"))
        assert jsonl_files
        entry = json.loads(jsonl_files[0].read_text().strip().split("\n")[-1])

        assert "s3cret" not in entry["validation_note"]
        assert "[REDACTED]" in entry["validation_note"]


# ── RISK-3: Pending approvals TTL expiry ──────────────────────────────────────


class TestPendingApprovalTTLExpiry:
    def test_expired_approvals_are_pruned(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))

        import app.services.guardian.pending_approvals as pa

        monkeypatch.setattr(pa, "_PENDING_TTL_SECONDS", 0)

        pa.store_pending_approval(
            confirm_id="expire-1",
            tool_name="test_tool",
            tool_args={"key": "val"},
            user_id="user-1",
            room_id="room-1",
        )

        time.sleep(0.05)

        result = pa.get_pending_approval("expire-1")
        assert result is None


# ── RISK-4: Computer Control bypass TTL enforcement ──────────────────────────


class TestComputerControlBypassExpiry:
    def test_expired_bypass_returns_disabled(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_GLOBAL_COMPUTER_CONTROL", "true")
        monkeypatch.setenv(
            "SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT",
            str(time.time() - 100),
        )
        from app.services.guardian.policy import global_bypass_enabled

        assert global_bypass_enabled() is False

    def test_active_bypass_returns_enabled(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_GLOBAL_COMPUTER_CONTROL", "true")
        monkeypatch.setenv(
            "SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT",
            str(time.time() + 3600),
        )
        from app.services.guardian.policy import global_bypass_enabled

        assert global_bypass_enabled() is True

    def test_bypass_without_expiry_is_disabled(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_GLOBAL_COMPUTER_CONTROL", "true")
        monkeypatch.delenv("SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT", raising=False)
        from app.services.guardian.policy import global_bypass_enabled

        assert global_bypass_enabled() is False


# ── RISK-5: Vault route unauthorized access denial ───────────────────────────


class TestVaultRouteAuthDenial:
    def test_vault_policy_denies_non_operator(self):
        from app.services.guardian.policy import decide_tool_use

        for tool in ("vault_list_secrets", "vault_add_secret", "vault_reveal_secret"):
            decision = decide_tool_use(tool, {}, is_operator=False)
            assert decision.action == "deny", f"{tool} should deny non-operator"
            assert "operators" in decision.reason.lower()

    def test_vault_write_requires_privileged_session(self):
        from app.services.guardian.policy import decide_tool_use

        for tool in ("vault_add_secret", "vault_update_secret", "vault_delete_secret"):
            decision = decide_tool_use(tool, {}, is_operator=True, is_privileged=False)
            assert decision.action in ("privileged", "privileged_reveal"), (
                f"{tool} should require privileged session, got {decision.action}"
            )

    def test_vault_reveal_requires_privileged_reveal_when_not_privileged(self):
        from app.services.guardian.policy import decide_tool_use

        decision = decide_tool_use("vault_reveal_secret", {}, is_operator=True, is_privileged=False)
        assert decision.action == "privileged_reveal"

    def test_vault_reveal_still_confirms_when_privileged(self):
        from app.services.guardian.policy import decide_tool_use

        decision = decide_tool_use("vault_reveal_secret", {}, is_operator=True, is_privileged=True)
        assert decision.action == "confirm"


# ── RISK-6: Task Guardian write-mode gate enforcement ─────────────────────────


class TestTaskGuardianWriteModeGate:
    def _reload_tg(self, monkeypatch, tmp_path, write_enabled="false"):
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))
        monkeypatch.setenv("SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED", write_enabled)
        import app.services.guardian.task_guardian as tg

        return importlib.reload(tg)

    def test_write_tool_rejected_without_write_mode(self, monkeypatch, tmp_path):
        tg = self._reload_tg(monkeypatch, tmp_path, write_enabled="false")

        with pytest.raises(ValueError, match="does not allow"):
            tg.schedule_task(
                name="Send email",
                tool_name="gmail_send",
                tool_args={"to": "x@example.com"},
                schedule="every:3600",
                room_id="room-1",
                user_id="user-1",
            )

    def test_write_tool_accepted_with_write_mode(self, monkeypatch, tmp_path):
        tg = self._reload_tg(monkeypatch, tmp_path, write_enabled="true")

        scheduled = tg.schedule_task(
            name="Send email",
            tool_name="gmail_send",
            tool_args={"to": "x@example.com"},
            schedule="every:3600",
            room_id="room-1",
            user_id="user-1",
        )
        assert scheduled["id"]

    def test_read_tool_accepted_without_write_mode(self, monkeypatch, tmp_path):
        tg = self._reload_tg(monkeypatch, tmp_path, write_enabled="false")

        scheduled = tg.schedule_task(
            name="Check inbox",
            tool_name="gmail_fetch_inbox",
            tool_args={"max_emails": 5},
            schedule="every:3600",
            room_id="room-1",
            user_id="user-1",
        )
        assert scheduled["id"]


# ── RISK-7: Memory PII redaction verified at persistence layer ────────────────


class TestMemoryPIIRedactionAtPersistence:
    def _reset(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_ENABLED", "true")
        monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_DATA_DIR", str(tmp_path / "memory"))
        monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS", "1200")
        monkeypatch.setenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT", "6")
        monkeypatch.delenv("SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS", raising=False)
        monkeypatch.delenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVER", raising=False)
        monkeypatch.setenv("SPARKBOT_IMPROVEMENT_DATA_DIR", str(tmp_path / "improvement"))
        from app.services.guardian import memory

        memory._guardian.cache_clear()
        memory._SNAPSHOT_STATE.clear()
        return memory

    def test_phone_redacted_in_stored_ledger(self, monkeypatch, tmp_path):
        memory = self._reset(monkeypatch, tmp_path)

        memory.remember_chat_message(
            user_id="user-1",
            room_id="room-1",
            role="user",
            content="Call me at 555-123-4567 please.",
        )

        events = list(memory._guardian().ledger.iter_events())
        stored_contents = [e.content for e in events]
        all_text = " ".join(stored_contents)
        assert "555-123-4567" not in all_text
        assert "[REDACTED_PHONE]" in all_text

    def test_email_redacted_in_stored_ledger(self, monkeypatch, tmp_path):
        memory = self._reset(monkeypatch, tmp_path)

        memory.remember_chat_message(
            user_id="user-1",
            room_id="room-1",
            role="user",
            content="Send updates to private@secret.org.",
        )

        events = list(memory._guardian().ledger.iter_events())
        stored_contents = [e.content for e in events]
        all_text = " ".join(stored_contents)
        assert "private@secret.org" not in all_text
        assert "[REDACTED_EMAIL]" in all_text

    def test_api_key_redacted_in_stored_ledger(self, monkeypatch, tmp_path):
        memory = self._reset(monkeypatch, tmp_path)

        memory.remember_chat_message(
            user_id="user-1",
            room_id="room-1",
            role="user",
            content="My key is sk-1234567890abcdefghijklmnop.",
        )

        events = list(memory._guardian().ledger.iter_events())
        stored_contents = [e.content for e in events]
        all_text = " ".join(stored_contents)
        assert "sk-1234567890abcdefghijklmnop" not in all_text
        assert "[REDACTED_TOKEN]" in all_text
