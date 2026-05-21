from __future__ import annotations

import importlib
import uuid

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import ChatRoom, ChatUser, UserType


def _reload_slack(monkeypatch, *, signing_secret: str = ""):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", signing_secret)
    import app.api.routes.chat.slack as slack

    return importlib.reload(slack)


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_slack_signature_fails_closed_without_secret(monkeypatch) -> None:
    slack = _reload_slack(monkeypatch, signing_secret="")

    assert slack._verify_slack_signature(b"{}", "123", "v0=bad") is False


def test_slack_identity_authorization_requires_channel_and_user_allowlists(monkeypatch) -> None:
    slack = _reload_slack(monkeypatch, signing_secret="secret")

    monkeypatch.delenv("SLACK_ALLOWED_CHANNEL_IDS", raising=False)
    monkeypatch.delenv("SLACK_ALLOWED_USER_IDS", raising=False)
    assert slack._slack_identity_authorized("C-test", "U-test") is False

    monkeypatch.setenv("SLACK_ALLOWED_CHANNEL_IDS", "C-test,C-other")
    assert slack._slack_identity_authorized("C-test", "U-test") is False

    monkeypatch.setenv("SLACK_ALLOWED_USER_IDS", "U-test,U-other")
    assert slack._slack_identity_authorized("C-test", "U-test") is True
    assert slack._slack_identity_authorized("C-missing", "U-test") is False
    assert slack._slack_identity_authorized("C-test", "U-missing") is False


def test_slack_memory_context_requires_existing_linked_owner(monkeypatch) -> None:
    slack = _reload_slack(monkeypatch, signing_secret="secret")
    monkeypatch.delenv("SPARKBOT_SLACK_OWNER_USERNAME", raising=False)

    with _session() as session:
        assert slack._get_slack_memory_context(session) is None
        assert session.exec(select(ChatUser)).all() == []


def test_slack_memory_context_uses_existing_owner(monkeypatch) -> None:
    slack = _reload_slack(monkeypatch, signing_secret="secret")
    monkeypatch.setenv("SPARKBOT_SLACK_OWNER_USERNAME", "operator")

    with _session() as session:
        owner = ChatUser(username="operator", type=UserType.HUMAN, hashed_password="")
        session.add(owner)
        session.commit()
        session.refresh(owner)

        context = slack._get_slack_memory_context(session)
        assert context is not None
        user_id, room_id = context
        assert user_id == str(owner.id)
        room = session.get(ChatRoom, uuid.UUID(room_id))
        assert room is not None
        assert room.name == "Slack Bridge"
