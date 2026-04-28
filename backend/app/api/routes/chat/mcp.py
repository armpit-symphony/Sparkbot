from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentChatUser
from app.services.mcp_registry import get_mcp_registry

router = APIRouter(tags=["chat-mcp"])


@router.get("/mcp/registry")
def mcp_registry(current_user: CurrentChatUser) -> dict[str, Any]:
    """Return the unified Sparkbot + LIMA MCP registry and live health metadata."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_mcp_registry()

