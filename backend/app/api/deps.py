from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlalchemy import select
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import TokenPayload, User, ChatUser, UserType

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_chat_user(session: SessionDep, token: TokenDep) -> ChatUser:
    """
    Get the current chat user from JWT token.
    Used for chat routes that authenticate via passphrase login.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    # Handle special case for passphrase login (subject = "sparkbot-user")
    # This creates a pseudo-user on-the-fly for passphrase authentication
    if token_data.sub == "sparkbot-user":
        # Check if sparkbot-user exists, create if not
        user = session.exec(
            select(ChatUser).where(ChatUser.username == "sparkbot-user")
        ).scalar_one_or_none()
        if not user:
            # Create a default chat user for passphrase login
            user = ChatUser(
                username="sparkbot-user",
                type=UserType.HUMAN,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    
    # The subject should be the ChatUser.id (UUID) or a string identifier
    # For passphrase login, we need to find the chat user by some identifier
    # Check if subject looks like a UUID first
    try:
        from uuid import UUID
        user_uuid = UUID(token_data.sub)
        user = session.get(ChatUser, user_uuid)
    except (ValueError, AttributeError):
        # If not a UUID, try to find by username or bot_slug
        user = session.exec(
            select(ChatUser).where(ChatUser.username == token_data.sub)
        ).scalar_one_or_none()
        if not user:
            user = session.exec(
                select(ChatUser).where(ChatUser.bot_slug == token_data.sub)
            ).scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Chat user not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentChatUser = Annotated[ChatUser, Depends(get_current_chat_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
