from __future__ import annotations

import logging
import os
import re
import time
import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models import ChatUser
from app.services.guardian import auth as guardian_auth

log = logging.getLogger(__name__)

_DEFAULT_SESSION_TTL_SECONDS = 1800
_OPERATOR_PRIVATE_RECALL_SCOPE = "operator_private_recall"
_PIN_COMMAND_RE = re.compile(r"^/(?:pin|verify)\s+([0-9]{6})\s*$", re.IGNORECASE)
_LOGOUT_COMMANDS = {"/logout", "/forget-session", "/forget_session", "/pin logout", "/verify logout"}
_PRIVATE_RECALL_TERMS = (
    "meeting",
    "round table",
    "roundtable",
    "meeting notes",
    "meeting note",
    "decisions",
    "decision",
    "action items",
    "action item",
    "next steps",
    "what did we decide",
    "what happened",
)


@dataclass
class ConnectorSession:
    connector: str
    external_identity: str
    channel_id: str
    linked_sparkbot_user_id: str
    scope: str
    verified_at: float
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def ttl_remaining(self) -> int:
        return max(0, int(self.expires_at - time.time()))


_CONNECTOR_SESSIONS: dict[str, ConnectorSession] = {}


def _session_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("SPARKBOT_CONNECTOR_PIN_TTL_SECONDS", str(_DEFAULT_SESSION_TTL_SECONDS))))
    except ValueError:
        return _DEFAULT_SESSION_TTL_SECONDS


def connector_identity_key(connector: str, external_identity: str, channel_id: str = "") -> str:
    safe_connector = (connector or "").strip().lower()
    safe_identity = (external_identity or "").strip()
    safe_channel = (channel_id or "").strip()
    return f"connector:{safe_connector}:{safe_channel}:{safe_identity}"


def private_recall_requested(text: str) -> bool:
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return False
    return any(term in normalized for term in _PRIVATE_RECALL_TERMS)


def parse_pin_command(text: str) -> str | None:
    match = _PIN_COMMAND_RE.match((text or "").strip())
    return match.group(1) if match else None


def is_logout_command(text: str) -> bool:
    return (text or "").strip().lower() in _LOGOUT_COMMANDS


def verification_required_message(connector_label: str = "this connector") -> str:
    return (
        "Private meeting memory requires operator verification for "
        f"{connector_label}. Reply with /pin <PIN> to open a time-limited verified session, "
        "or use Main Chat."
    )


def verification_success_message(session: ConnectorSession) -> str:
    minutes = max(1, session.ttl_remaining() // 60)
    return f"Operator verification accepted. Private recall is available for about {minutes} minutes."


def verification_closed_message() -> str:
    return "Connector verification session closed."


def resolve_operator_user_id(session: Session) -> str | None:
    usernames = sorted(guardian_auth.operator_usernames())
    if not usernames:
        usernames = ["sparkbot-user"]
    for username in usernames:
        try:
            user = session.exec(select(ChatUser).where(ChatUser.username == username)).first()
        except Exception:
            user = None
        if user and guardian_auth.is_operator_identity(username=user.username, user_type=user.type, is_superuser=False):
            return str(user.id)
    return None


def active_connector_session(*, connector: str, external_identity: str, channel_id: str = "") -> ConnectorSession | None:
    key = connector_identity_key(connector, external_identity, channel_id)
    session = _CONNECTOR_SESSIONS.get(key)
    if session is None:
        return None
    if session.is_expired():
        _CONNECTOR_SESSIONS.pop(key, None)
        return None
    return session


def verify_connector_pin(
    *,
    connector: str,
    external_identity: str,
    submitted_pin: str,
    linked_sparkbot_user_id: str,
    channel_id: str = "",
    scope: str = _OPERATOR_PRIVATE_RECALL_SCOPE,
) -> ConnectorSession | None:
    key = connector_identity_key(connector, external_identity, channel_id)
    if not linked_sparkbot_user_id:
        log.warning("[connector-verification] PIN denied for %s: no linked Sparkbot operator user", key)
        return None
    if guardian_auth.is_locked_out(key):
        log.warning("[connector-verification] PIN locked out for %s", key)
        return None
    if not guardian_auth.verify_pin(key, submitted_pin or ""):
        return None
    now = time.time()
    session = ConnectorSession(
        connector=(connector or "").strip().lower(),
        external_identity=(external_identity or "").strip(),
        channel_id=(channel_id or "").strip(),
        linked_sparkbot_user_id=str(linked_sparkbot_user_id),
        scope=scope,
        verified_at=now,
        expires_at=now + _session_ttl_seconds(),
    )
    _CONNECTOR_SESSIONS[key] = session
    log.info("[connector-verification] Verified connector session opened for %s ttl=%ds", key, session.ttl_remaining())
    return session


def close_connector_session(*, connector: str, external_identity: str, channel_id: str = "") -> None:
    _CONNECTOR_SESSIONS.pop(connector_identity_key(connector, external_identity, channel_id), None)


def private_recall_gate(
    db: Session,
    *,
    connector: str,
    external_identity: str,
    current_user_id: str,
    channel_id: str = "",
    linked_operator_identity: bool = False,
) -> tuple[bool, str | None, str]:
    if linked_operator_identity and guardian_auth.is_operator_user_id(db, current_user_id):
        return True, str(current_user_id), "linked_operator_identity"

    connector_session = active_connector_session(
        connector=connector,
        external_identity=external_identity,
        channel_id=channel_id,
    )
    if connector_session and connector_session.linked_sparkbot_user_id:
        return True, connector_session.linked_sparkbot_user_id, "pin_verified_session"

    return False, None, "verification_required"


def session_dump_contains(value: str) -> bool:
    return value in repr(_CONNECTOR_SESSIONS)


def _clear_sessions_for_tests() -> None:
    _CONNECTOR_SESSIONS.clear()
