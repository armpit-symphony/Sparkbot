"""Event schemas for the memory ledger."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events that can be logged."""
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THOUGHT = "thought"
    DECISION = "decision"
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Event(BaseModel):
    """An event in the append-only ledger."""
    id: str = Field(default_factory=lambda: f"{datetime.utcnow().isoformat()}-{EventType.SYSTEM.value}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: EventType
    role: str | None = None  # user, assistant, system
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    turn: int | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
