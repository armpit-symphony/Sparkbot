from __future__ import annotations

import time

from sqlmodel import Session, SQLModel, create_engine

from app.models import ChatUser, UserType
from app.services import connector_verification
from app.services.guardian import auth as guardian_auth


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _configure_pin(monkeypatch, tmp_path, pin: str = "123456") -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))
    monkeypatch.setenv("SPARKBOT_OPERATOR_PIN_HASH", guardian_auth.create_pin_hash(pin))
    monkeypatch.setenv("SPARKBOT_OPERATOR_USERNAMES", "operator")
    connector_verification._clear_sessions_for_tests()


def _operator(session: Session) -> ChatUser:
    user = ChatUser(username="operator", type=UserType.HUMAN, hashed_password="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_valid_pin_creates_connector_session(monkeypatch, tmp_path) -> None:
    _configure_pin(monkeypatch, tmp_path)
    with _session() as session:
        operator = _operator(session)
        verified = connector_verification.verify_connector_pin(
            connector="telegram",
            external_identity="chat-1",
            submitted_pin="123456",
            linked_sparkbot_user_id=str(operator.id),
        )
        assert verified is not None
        assert verified.connector == "telegram"
        assert verified.linked_sparkbot_user_id == str(operator.id)
        assert connector_verification.active_connector_session(connector="telegram", external_identity="chat-1") is verified
        assert not connector_verification.session_dump_contains("123456")


def test_invalid_pin_does_not_create_session(monkeypatch, tmp_path) -> None:
    _configure_pin(monkeypatch, tmp_path)
    with _session() as session:
        operator = _operator(session)
        verified = connector_verification.verify_connector_pin(
            connector="telegram",
            external_identity="chat-1",
            submitted_pin="000000",
            linked_sparkbot_user_id=str(operator.id),
        )
        assert verified is None
        assert connector_verification.active_connector_session(connector="telegram", external_identity="chat-1") is None


def test_expired_connector_session_fails_gate(monkeypatch, tmp_path) -> None:
    _configure_pin(monkeypatch, tmp_path)
    with _session() as session:
        operator = _operator(session)
        verified = connector_verification.verify_connector_pin(
            connector="whatsapp",
            external_identity="15551234567",
            submitted_pin="123456",
            linked_sparkbot_user_id=str(operator.id),
        )
        assert verified is not None
        verified.expires_at = time.time() - 1
        allowed, context_user_id, reason = connector_verification.private_recall_gate(
            session,
            connector="whatsapp",
            external_identity="15551234567",
            current_user_id=str(operator.id),
        )
        assert allowed is False
        assert context_user_id is None
        assert reason == "verification_required"


def test_private_recall_gate_allows_linked_operator_without_pin(monkeypatch, tmp_path) -> None:
    _configure_pin(monkeypatch, tmp_path)
    with _session() as session:
        operator = _operator(session)
        allowed, context_user_id, reason = connector_verification.private_recall_gate(
            session,
            connector="slack",
            external_identity="U-test",
            channel_id="C-test",
            current_user_id=str(operator.id),
            linked_operator_identity=True,
        )
        assert allowed is True
        assert context_user_id == str(operator.id)
        assert reason == "linked_operator_identity"


def test_pin_command_parser_requires_six_digit_command() -> None:
    assert connector_verification.parse_pin_command("/pin 123456") == "123456"
    assert connector_verification.parse_pin_command("/verify 123456") == "123456"
    assert connector_verification.parse_pin_command("123456") is None
    assert connector_verification.parse_pin_command("/pin 1234567") is None


def test_private_recall_detection_covers_meeting_questions() -> None:
    assert connector_verification.private_recall_requested("What did the meeting decide?") is True
    assert connector_verification.private_recall_requested("show the Round Table action items") is True
    assert connector_verification.private_recall_requested("hello sparkbot") is False



def test_whatsapp_verify_token_has_no_predictable_default(monkeypatch) -> None:
    from app.services import whatsapp_bridge

    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    assert whatsapp_bridge._wa_verify_token() == ""


def test_whatsapp_allowed_phones_empty_is_not_public_ready(monkeypatch) -> None:
    from app.services import whatsapp_bridge

    monkeypatch.delenv("WHATSAPP_ALLOWED_PHONES", raising=False)
    assert whatsapp_bridge._wa_allowed_phones() == set()
