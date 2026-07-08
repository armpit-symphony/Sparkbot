"""Public-safe LIMA decision preview routes.

LIMA decision preview is non-executing and does not represent active Guardian enforcement.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.lima_decision_preview import (
    PUBLIC_PREVIEW_NOTE,
    lima_decision_preview_status,
    preview_lima_decision,
)

router = APIRouter(prefix="/lima", tags=["lima-decision-preview"])


class LimaDecisionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str = Field(..., min_length=1, max_length=120)
    normalized_request: Any
    requested_action: str = Field(..., min_length=1, max_length=200)
    action_category: str = Field(..., min_length=1, max_length=80)
    tool_name: str | None = Field(default=None, max_length=120)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


@router.get("/status")
def lima_status() -> dict[str, Any]:
    payload = lima_decision_preview_status()
    payload["public_copy"] = PUBLIC_PREVIEW_NOTE
    return payload


@router.post("/decision-preview")
def lima_decision_preview(body: LimaDecisionPreviewRequest) -> dict[str, Any]:
    payload = preview_lima_decision(body.model_dump(mode="python"))
    payload["public_copy"] = PUBLIC_PREVIEW_NOTE
    return payload
