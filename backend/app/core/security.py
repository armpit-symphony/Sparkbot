from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def decode_token(token: str) -> dict | None:
    """
    Decode a JWT token without verification.
    Used for WebSocket authentication where we just need the payload.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": True},
        )
        logger.info(f"[WS] decode_token success: {payload}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.error(f"[WS] decode_token: expired signature")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"[WS] decode_token: invalid token - {e}")
        return None
    except Exception as e:
        logger.error(f"[WS] decode_token: unexpected error - {type(e).__name__}: {e}")
        return None
