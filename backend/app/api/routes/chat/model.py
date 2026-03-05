"""
Model preference endpoints.

GET  /chat/models       — list available models
GET  /chat/model        — get current user's active model
POST /chat/model        — set current user's model preference
"""
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentChatUser
from app.api.routes.chat.llm import AVAILABLE_MODELS, get_model, set_model

router = APIRouter(tags=["chat-model"])


@router.get("/models")
def list_models(current_user: CurrentChatUser) -> dict:
    """Return all available models with descriptions."""
    active = get_model(str(current_user.id))
    return {
        "models": [
            {"id": k, "description": v, "active": k == active}
            for k, v in AVAILABLE_MODELS.items()
        ],
        "active": active,
    }


@router.get("/model")
def get_current_model(current_user: CurrentChatUser) -> dict:
    """Return the active model for the current user."""
    model = get_model(str(current_user.id))
    return {"model": model, "description": AVAILABLE_MODELS.get(model, model)}


class ModelSelect(BaseModel):
    model: str


@router.post("/model")
def set_current_model(body: ModelSelect, current_user: CurrentChatUser) -> dict:
    """Set the active model for the current user."""
    try:
        chosen = set_model(str(current_user.id), body.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"model": chosen, "description": AVAILABLE_MODELS[chosen]}
