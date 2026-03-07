from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.api.deps import get_db
from app.services.github_bridge import (
    _configured,
    _enabled,
    handle_github_event,
    mark_delivery_seen,
    verify_signature,
)

router = APIRouter(tags=["github"])


@router.post("/github/events")
async def github_events(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    if not _enabled():
        return {"ok": True, "ignored": "github bridge disabled"}
    if not _configured():
        return Response(status_code=503, content="GitHub bridge not configured")

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature):
        return Response(status_code=403, content="Invalid GitHub signature")

    delivery_id = request.headers.get("X-GitHub-Delivery", "").strip()
    if delivery_id and not mark_delivery_seen(delivery_id):
        return {"ok": True}

    try:
        payload = json.loads(body)
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    event_name = request.headers.get("X-GitHub-Event", "").strip()
    if event_name == "ping":
        return {
            "ok": True,
            "zen": payload.get("zen", ""),
            "hook_id": payload.get("hook_id"),
        }

    background_tasks.add_task(
        handle_github_event,
        event_name=event_name,
        payload=payload,
        get_db=get_db,
    )
    return {"ok": True}

