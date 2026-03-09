"""Tests for Guardian Auth (break-glass) and Guardian Vault."""
import asyncio
from datetime import timedelta
import time
from uuid import UUID

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import ChatUser, UserType


def _ensure_chat_user(username: str) -> UUID:
    with Session(engine) as db:
        user = db.exec(select(ChatUser).where(ChatUser.username == username)).first()
        if user:
            return user.id
        user = ChatUser(username=username, type=UserType.HUMAN, is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _chat_headers_for_user(user_id: UUID) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


# ── Guardian Auth Tests ────────────────────────────────────────────────────────

class TestCreatePinHash:
    def test_creates_pbkdf2_hash(self):
        from app.services.guardian.auth import create_pin_hash
        h = create_pin_hash("mypin")
        parts = h.split("$")
        assert len(parts) == 5
        assert parts[0] == "pbkdf2"
        assert parts[1] == "sha256"
        assert parts[2] == "300000"

    def test_unique_salts_per_call(self):
        from app.services.guardian.auth import create_pin_hash
        h1 = create_pin_hash("same")
        h2 = create_pin_hash("same")
        assert h1 != h2  # Different salts → different hashes


class TestVerifyPin:
    def test_correct_pin_returns_true(self, monkeypatch):
        from app.services.guardian.auth import create_pin_hash, verify_pin
        pin_hash = create_pin_hash("correct_pin")
        monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", pin_hash)
        assert verify_pin("user1", "correct_pin") is True

    def test_wrong_pin_returns_false(self, monkeypatch):
        from app.services.guardian.auth import create_pin_hash, verify_pin
        pin_hash = create_pin_hash("correct_pin")
        monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", pin_hash)
        assert verify_pin("user1", "wrong_pin") is False

    def test_unconfigured_hash_returns_false(self, monkeypatch):
        monkeypatch.delenv("SPARKBOT_OPERATOR_PIN_HASH", raising=False)
        from app.services.guardian.auth import verify_pin
        assert verify_pin("user1", "anything") is False


class TestToolOutputMasking:
    def test_masks_vault_use_secret_for_external_paths(self):
        from app.api.routes.chat.llm import mask_tool_result_for_external

        assert (
            mask_tool_result_for_external(
                "vault_use_secret",
                {"alias": "prod_db_password"},
                "super-secret-value",
            )
            == "[vault:prod_db_password]"
        )

    def test_redacts_vault_value_and_generic_secret_pairs_for_audit(self):
        from app.api.routes.chat.llm import redact_tool_call_for_audit

        redacted_input, redacted_result = redact_tool_call_for_audit(
            "vault_add_secret",
            {"alias": "smtp_pass", "value": "hunter2", "notes": "token=abc123"},
            "password=hunter2 token=abc123",
        )

        assert "hunter2" not in redacted_input
        assert "abc123" not in redacted_result
        assert "[REDACTED]" in redacted_input
        assert "[REDACTED]" in redacted_result


class TestGuardianPolicy:
    def test_vault_tools_require_operator_identity(self):
        from app.services.guardian.policy import decide_tool_use

        denied = decide_tool_use("vault_list_secrets", {}, is_operator=False)
        allowed = decide_tool_use("vault_list_secrets", {}, is_operator=True)

        assert denied.action == "deny"
        assert "operators" in denied.reason.lower()
        assert allowed.action == "allow"


class TestFailedAttempts:
    def setup_method(self):
        from app.services.guardian import auth as auth_module
        auth_module._FAILED_ATTEMPTS.clear()

    def test_lockout_after_max_attempts(self, monkeypatch):
        from app.services.guardian.auth import create_pin_hash, is_locked_out, verify_pin
        pin_hash = create_pin_hash("correct")
        monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", pin_hash)
        monkeypatch.setenv("SPARKBOT_PIN_MAX_ATTEMPTS", "3")
        monkeypatch.setenv("SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS", "300")
        for _ in range(3):
            verify_pin("lockout_user", "wrong")
        assert is_locked_out("lockout_user") is True

    def test_no_lockout_before_max_attempts(self, monkeypatch):
        from app.services.guardian.auth import create_pin_hash, is_locked_out, verify_pin
        pin_hash = create_pin_hash("correct")
        monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", pin_hash)
        monkeypatch.setenv("SPARKBOT_PIN_MAX_ATTEMPTS", "5")
        monkeypatch.setenv("SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS", "300")
        for _ in range(2):
            verify_pin("safe_user", "wrong")
        assert is_locked_out("safe_user") is False


class TestPrivilegedSession:
    def setup_method(self):
        from app.services.guardian import auth as auth_module
        auth_module._PRIVILEGED_SESSIONS.clear()
        auth_module._FAILED_ATTEMPTS.clear()

    def test_open_and_check_session(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_BREAKGLASS_TTL_SECONDS", "900")
        from app.services.guardian.auth import (
            get_active_session,
            is_operator_privileged,
            open_privileged_session,
        )
        session = open_privileged_session("user_a", "user_a")
        assert session.user_id == "user_a"
        assert session.ttl_remaining() > 0
        assert is_operator_privileged("user_a") is True
        retrieved = get_active_session("user_a")
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_close_session(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_BREAKGLASS_TTL_SECONDS", "900")
        from app.services.guardian.auth import (
            close_privileged_session,
            is_operator_privileged,
            open_privileged_session,
        )
        open_privileged_session("user_b", "user_b")
        assert is_operator_privileged("user_b") is True
        close_privileged_session("user_b")
        assert is_operator_privileged("user_b") is False

    def test_expired_session_returns_none(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_BREAKGLASS_TTL_SECONDS", "1")
        from app.services.guardian.auth import get_active_session, open_privileged_session
        open_privileged_session("user_c", "user_c")
        time.sleep(1.1)
        assert get_active_session("user_c") is None

    def test_correct_pin_clears_failed_attempts(self, monkeypatch):
        monkeypatch.setenv("SPARKBOT_BREAKGLASS_TTL_SECONDS", "900")
        monkeypatch.setenv("SPARKBOT_PIN_MAX_ATTEMPTS", "5")
        monkeypatch.setenv("SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS", "300")
        from app.services.guardian.auth import (
            create_pin_hash,
            is_locked_out,
            open_privileged_session,
            verify_pin,
        )
        pin_hash = create_pin_hash("mypin")
        monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", pin_hash)
        verify_pin("user_d", "wrong1")
        verify_pin("user_d", "wrong2")
        open_privileged_session("user_d", "user_d")  # success clears attempts
        assert is_locked_out("user_d") is False


class TestGuardianRouteAccess:
    def test_breakglass_and_vault_routes_require_operator(self, client, monkeypatch):
        from app.services.guardian.auth import create_pin_hash

        outsider_id = _ensure_chat_user("outsider_guardian")
        headers = _chat_headers_for_user(outsider_id)
        monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", create_pin_hash("1234"))

        assert client.get(f"{settings.API_V1_STR}/chat/guardian/breakglass/status", headers=headers).status_code == 403
        assert client.post(
            f"{settings.API_V1_STR}/chat/guardian/breakglass",
            headers=headers,
            json={"pin": "1234"},
        ).status_code == 403
        assert client.get(f"{settings.API_V1_STR}/chat/guardian/vault", headers=headers).status_code == 403

    def test_breakglass_status_expires_cleanly_for_operator(self, client):
        from app.services.guardian import auth as auth_module

        operator_id = _ensure_chat_user("sparkbot-user")
        headers = _chat_headers_for_user(operator_id)
        session = auth_module.open_privileged_session(str(operator_id), "sparkbot-user")
        session.expires_at = time.time() - 1

        response = client.get(f"{settings.API_V1_STR}/chat/guardian/breakglass/status", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"active": False}

    def test_breakglass_close_revokes_operator_session(self, client):
        from app.services.guardian import auth as auth_module

        operator_id = _ensure_chat_user("sparkbot-user")
        headers = _chat_headers_for_user(operator_id)
        auth_module.open_privileged_session(str(operator_id), "sparkbot-user")

        response = client.delete(f"{settings.API_V1_STR}/chat/guardian/breakglass", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"closed": True}
        assert auth_module.get_active_session(str(operator_id)) is None


class TestTelegramAwaitingPin:
    def setup_method(self):
        from app.services import telegram_bridge

        telegram_bridge._AWAITING_PIN.clear()

    def test_awaiting_pin_entries_expire(self, monkeypatch):
        from app.services import telegram_bridge

        fake_now = {"value": 1000.0}
        monkeypatch.setattr(telegram_bridge, "_AWAITING_PIN_TTL_SECONDS", 60)
        monkeypatch.setattr(telegram_bridge.time, "time", lambda: fake_now["value"])

        telegram_bridge._set_awaiting_pin("chat-1", confirm_id="abc", requires_confirm=False)
        fake_now["value"] = 1061.0

        expired = telegram_bridge._prune_awaiting_pin(chat_id="chat-1")

        assert expired == {"chat-1"}
        assert "chat-1" not in telegram_bridge._AWAITING_PIN


class TestTelegramOperatorLinking:
    def test_operator_chat_maps_to_operator_user(self, monkeypatch, tmp_path):
        from app.services import telegram_bridge

        operator_id = _ensure_chat_user("sparkbot-user")
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS", "operator-chat")

        with Session(engine) as db:
            link = telegram_bridge._ensure_linked_room(
                db,
                "operator-chat",
                {"id": "12345", "first_name": "Phil"},
            )

        assert link.user_id == str(operator_id)

    def test_existing_operator_chat_link_is_remapped_to_operator_user(self, monkeypatch, tmp_path):
        from app.services import telegram_bridge

        operator_id = _ensure_chat_user("sparkbot-user")
        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path))

        with Session(engine) as db:
            first_link = telegram_bridge._ensure_linked_room(
                db,
                "operator-chat",
                {"id": "12345", "first_name": "Phil"},
            )

        assert first_link.user_id != str(operator_id)

        monkeypatch.setenv("SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS", "operator-chat")

        with Session(engine) as db:
            remapped = telegram_bridge._ensure_linked_room(
                db,
                "operator-chat",
                {"id": "12345", "first_name": "Phil"},
            )

        assert remapped.room_id == first_link.room_id
        assert remapped.user_id == str(operator_id)

    def test_non_operator_telegram_breakglass_is_denied(self, monkeypatch, tmp_path):
        from app.services import telegram_bridge

        monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path))
        sent_messages: list[str] = []

        async def _fake_send_text(chat_id: str, text: str) -> None:
            sent_messages.append(text)

        monkeypatch.setattr(telegram_bridge, "_send_text", _fake_send_text)
        telegram_bridge._AWAITING_PIN.clear()

        message = {
            "chat": {"id": "operator-chat", "type": "private"},
            "from": {"id": "12345", "first_name": "Phil", "is_bot": False},
            "text": "/breakglass",
        }

        def _get_db_session():
            with Session(engine) as db:
                yield db

        async def _run() -> None:
            await telegram_bridge._handle_private_message(message, _get_db_session)

        asyncio.run(_run())

        assert sent_messages == ["Break-glass is restricted to configured Sparkbot operators."]


# ── Guardian Vault Tests ───────────────────────────────────────────────────────

@pytest.fixture
def vault_env(tmp_path, monkeypatch):
    """Set up temp vault DB and Fernet key for vault tests."""
    pytest.importorskip("cryptography", reason="cryptography package not installed")
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SPARKBOT_VAULT_KEY", key)
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path))
    from app.services.guardian.vault import init_vault_db
    init_vault_db()
    return key


class TestVaultAddList:
    def test_add_and_list(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_list
        vault_add("my_token", "s3cr3t", category="api", operator="op1")
        entries = vault_list()
        assert any(e["alias"] == "my_token" for e in entries)

    def test_duplicate_alias_raises(self, vault_env):
        from app.services.guardian.vault import vault_add
        vault_add("dup_alias", "value1", operator="op1")
        with pytest.raises(ValueError, match="already exists"):
            vault_add("dup_alias", "value2", operator="op1")

    def test_list_contains_no_plaintext(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_list
        vault_add("secret_alias", "supersecret_value", operator="op1")
        entries = vault_list()
        for e in entries:
            assert "supersecret_value" not in str(e)
            assert "encrypted_value" not in e


class TestVaultUseReveal:
    def test_use_returns_plaintext(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_use
        vault_add("tok1", "plainvalue", policy="use_only", operator="op1")
        result = vault_use("tok1", "user1", "op1")
        assert result == "plainvalue"

    def test_reveal_blocked_for_use_only(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_reveal
        vault_add("tok2", "plainvalue", policy="use_only", operator="op1")
        with pytest.raises(ValueError, match="use_only"):
            vault_reveal("tok2", "user1", "op1")

    def test_reveal_allowed_for_privileged_reveal_policy(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_reveal
        vault_add("tok3", "revealme", policy="privileged_reveal", operator="op1")
        result = vault_reveal("tok3", "user1", "op1", session_id="s123")
        assert result == "revealme"

    def test_disabled_policy_blocks_use(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_use
        vault_add("tok4", "value", policy="disabled", operator="op1")
        with pytest.raises(ValueError, match="disabled"):
            vault_use("tok4", "user1", "op1")

    def test_unknown_alias_raises_on_use(self, vault_env):
        from app.services.guardian.vault import vault_use
        with pytest.raises(ValueError, match="No secret"):
            vault_use("nonexistent", "user1", "op1")

    def test_unknown_alias_raises_on_reveal(self, vault_env):
        from app.services.guardian.vault import vault_reveal
        with pytest.raises(ValueError, match="No secret"):
            vault_reveal("nonexistent", "user1", "op1")


class TestVaultUpdateDelete:
    def test_update_changes_value(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_update, vault_use
        vault_add("upd1", "oldvalue", operator="op1")
        vault_update("upd1", "newvalue", operator="op1")
        assert vault_use("upd1", "user1", "op1") == "newvalue"

    def test_update_nonexistent_raises(self, vault_env):
        from app.services.guardian.vault import vault_update
        with pytest.raises(ValueError, match="No secret"):
            vault_update("ghost", "value", operator="op1")

    def test_delete_removes_entry(self, vault_env):
        from app.services.guardian.vault import vault_add, vault_delete, vault_list
        vault_add("del1", "todelete", operator="op1")
        ok = vault_delete("del1", operator="op1")
        assert ok is True
        entries = vault_list()
        assert not any(e["alias"] == "del1" for e in entries)

    def test_delete_nonexistent_returns_false(self, vault_env):
        from app.services.guardian.vault import vault_delete
        assert vault_delete("ghost", operator="op1") is False


class TestVaultEncryptionRoundTrip:
    def test_raw_db_does_not_contain_plaintext(self, vault_env, tmp_path):
        """Verify the raw SQLite DB does not store plaintext values."""
        import sqlite3
        from app.services.guardian.vault import vault_add, _db_path
        vault_add("enc_test", "my_very_secret_value", operator="op1")
        conn = sqlite3.connect(_db_path())
        row = conn.execute(
            "SELECT encrypted_value FROM vault_entries WHERE alias = 'enc_test'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert b"my_very_secret_value" not in bytes(row[0])


class TestVaultInvalidPolicy:
    def test_invalid_policy_raises(self, vault_env):
        from app.services.guardian.vault import vault_add
        with pytest.raises(ValueError, match="Invalid access_policy"):
            vault_add("bad_policy", "value", policy="super_secret", operator="op1")
