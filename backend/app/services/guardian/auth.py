"""
Guardian Auth — Privileged session management and PIN verification.

Provides break-glass operator authentication:
- PIN hash stored in env (SPARKBOT_OPERATOR_PIN_HASH)
- PBKDF2-HMAC-SHA256, format: pbkdf2$sha256$300000$<salt_hex>$<dk_hex>
- In-memory privileged sessions with TTL
- Failed-attempt lockout
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

_DEFAULT_OPERATOR_USERNAMES = {"sparkbot-user"}
_SESSION_TTL_DEFAULT = 900   # 15 minutes
_PIN_MAX_ATTEMPTS_DEFAULT = 5
_PIN_LOCKOUT_WINDOW_DEFAULT = 300  # 5 minutes
_PBKDF2_ITERATIONS = 300_000
_PBKDF2_HASH = "sha256"
_PBKDF2_DK_LEN = 32


@dataclass
class PrivilegedSession:
    session_id: str
    user_id: str
    operator: str
    started_at: float
    expires_at: float
    scopes: list = field(default_factory=lambda: ["vault", "service_control"])

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def ttl_remaining(self) -> int:
        return max(0, int(self.expires_at - time.time()))


# In-memory state — intentionally not persisted (sessions die with the process)
_PRIVILEGED_SESSIONS: dict[str, PrivilegedSession] = {}
_FAILED_ATTEMPTS: dict[str, list[float]] = {}


def operator_usernames() -> set[str]:
    configured = {
        name.strip().lower()
        for name in os.getenv("SPARKBOT_OPERATOR_USERNAMES", "").split(",")
        if name.strip()
    }
    return configured or set(_DEFAULT_OPERATOR_USERNAMES)


def is_operator_identity(*, username: str | None, user_type: object | None) -> bool:
    normalized_type = getattr(user_type, "value", user_type)
    if str(normalized_type).upper() != "HUMAN":
        return False
    return (username or "").strip().lower() in operator_usernames()


def is_operator_user_id(session, user_id: str | None) -> bool:
    if not session or not user_id:
        return False
    try:
        from sqlmodel import select
        from app.models import ChatUser

        user_uuid = uuid.UUID(str(user_id))
        user = session.exec(select(ChatUser).where(ChatUser.id == user_uuid)).first()
    except Exception:
        return False
    if user is None:
        return False
    return is_operator_identity(username=user.username, user_type=user.type)


def _session_ttl() -> int:
    return int(os.getenv("SPARKBOT_BREAKGLASS_TTL_SECONDS", str(_SESSION_TTL_DEFAULT)))


def _pin_max_attempts() -> int:
    return int(os.getenv("SPARKBOT_PIN_MAX_ATTEMPTS", str(_PIN_MAX_ATTEMPTS_DEFAULT)))


def _pin_lockout_window() -> int:
    return int(os.getenv("SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS", str(_PIN_LOCKOUT_WINDOW_DEFAULT)))


def create_pin_hash(pin: str) -> str:
    """Hash a PIN for storage in .env.
    Returns 'pbkdf2$sha256$300000$<salt_hex>$<dk_hex>'.
    Usage: python3 -c "from app.services.guardian.auth import create_pin_hash; print(create_pin_hash('YOUR_PIN'))"
    """
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH,
        pin.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_PBKDF2_DK_LEN,
    )
    return f"pbkdf2$sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def _verify_pbkdf2(pin: str, stored_hash: str) -> bool:
    """Constant-time verification of a PIN against a stored PBKDF2 hash."""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 5 or parts[0] != "pbkdf2" or parts[1] != "sha256":
            return False
        iterations = int(parts[2])
        salt = bytes.fromhex(parts[3])
        expected_dk = bytes.fromhex(parts[4])
        candidate_dk = hashlib.pbkdf2_hmac(
            _PBKDF2_HASH,
            pin.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_dk),
        )
        return hmac.compare_digest(candidate_dk, expected_dk)
    except Exception:
        return False


def is_locked_out(user_id: str) -> bool:
    """Return True if this user_id has too many recent failed PIN attempts."""
    now = time.time()
    window = _pin_lockout_window()
    attempts = _FAILED_ATTEMPTS.get(user_id, [])
    recent = [t for t in attempts if now - t < window]
    _FAILED_ATTEMPTS[user_id] = recent
    return len(recent) >= _pin_max_attempts()


def _record_failed_attempt(user_id: str) -> None:
    now = time.time()
    attempts = _FAILED_ATTEMPTS.get(user_id, [])
    attempts.append(now)
    _FAILED_ATTEMPTS[user_id] = attempts


def verify_pin(user_id: str, submitted_pin: str) -> bool:
    """
    Verify submitted PIN against the stored hash. Records failed attempts.
    Returns True on success, False on failure or if not configured.
    """
    stored = os.getenv("SPARKBOT_OPERATOR_PIN_HASH", "").strip()
    if not stored:
        log.warning("[guardian-auth] SPARKBOT_OPERATOR_PIN_HASH is not configured — PIN auth disabled")
        return False
    ok = _verify_pbkdf2(submitted_pin, stored)
    if not ok:
        _record_failed_attempt(user_id)
        log.warning("[guardian-auth] Failed PIN attempt for user_id=%s", user_id)
    return ok


def open_privileged_session(user_id: str, operator: str) -> PrivilegedSession:
    """Open (or refresh) a privileged session for this user."""
    now = time.time()
    ttl = _session_ttl()
    session = PrivilegedSession(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        operator=operator,
        started_at=now,
        expires_at=now + ttl,
    )
    _PRIVILEGED_SESSIONS[user_id] = session
    _FAILED_ATTEMPTS.pop(user_id, None)
    log.info(
        "[guardian-auth] Privileged session opened user_id=%s session_id=%s ttl=%ds",
        user_id, session.session_id, ttl,
    )
    return session


def get_active_session(user_id: str) -> Optional[PrivilegedSession]:
    """Return active non-expired session, or None."""
    session = _PRIVILEGED_SESSIONS.get(user_id)
    if session is None:
        return None
    if session.is_expired():
        _PRIVILEGED_SESSIONS.pop(user_id, None)
        return None
    return session


def is_operator_privileged(user_id: str) -> bool:
    """Return True if this user has an active privileged session."""
    return get_active_session(user_id) is not None


def close_privileged_session(user_id: str) -> None:
    """Explicitly close/revoke a privileged session."""
    session = _PRIVILEGED_SESSIONS.pop(user_id, None)
    if session:
        log.info(
            "[guardian-auth] Privileged session closed user_id=%s session_id=%s",
            user_id, session.session_id,
        )
