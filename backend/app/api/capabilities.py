from typing import Literal, TypedDict

from fastapi import APIRouter

router = APIRouter()

CapabilityStatus = Literal["available", "preview", "planned", "disabled-by-default", "guarded-future"]
ALLOWED_CAPABILITY_STATUSES: set[str] = {
    "available",
    "preview",
    "planned",
    "disabled-by-default",
    "guarded-future",
}


class Capability(TypedDict):
    id: str
    label: str
    status: CapabilityStatus
    notes: str


class CapabilitiesResponse(TypedDict):
    service: str
    mode: str
    capabilities: list[Capability]


CAPABILITIES: list[Capability] = [
    {
        "id": "backend-health",
        "label": "Backend health endpoint",
        "status": "available",
        "notes": "Read-only local health check.",
    },
    {
        "id": "frontend-shell",
        "label": "Frontend shell",
        "status": "available",
        "notes": "Public shell interface.",
    },
    {
        "id": "workstation",
        "label": "Workstation shell",
        "status": "preview",
        "notes": "Navigation and product shell preview.",
    },
    {
        "id": "chat",
        "label": "Chat shell",
        "status": "preview",
        "notes": "No model calls or message persistence.",
    },
    {
        "id": "work-page",
        "label": "Work Page shell",
        "status": "preview",
        "notes": "No file reads, file writes, connector calls, or worker execution.",
    },
    {
        "id": "round-table",
        "label": "Round Table",
        "status": "preview",
        "notes": "No meeting engine or agent orchestration.",
    },
    {
        "id": "provider-setup",
        "label": "Provider Setup shell",
        "status": "preview",
        "notes": "No credential storage or provider calls.",
    },
    {
        "id": "local-ai-settings",
        "label": "Local AI Settings shell",
        "status": "preview",
        "notes": "No credentials, endpoint checks, provider calls, or model routing.",
    },
    {
        "id": "guardian-controls",
        "label": "Guardian Controls shell",
        "status": "preview",
        "notes": "No policy enforcement runtime.",
    },
    {
        "id": "desktop-packaging",
        "label": "Desktop packaging",
        "status": "planned",
        "notes": "No installer or desktop binary yet.",
    },
    {
        "id": "connectors",
        "label": "Connectors",
        "status": "guarded-future",
        "notes": "No connector calls or external sends.",
    },
    {
        "id": "model-calls",
        "label": "Model calls",
        "status": "guarded-future",
        "notes": "No provider runtime or model routing.",
    },
    {
        "id": "credential-storage",
        "label": "Credential storage",
        "status": "guarded-future",
        "notes": "No credential entry or storage path.",
    },
    {
        "id": "tool-execution",
        "label": "Tool execution",
        "status": "guarded-future",
        "notes": "No terminal, tool, or automation execution.",
    },
]


@router.get("/capabilities")
def capabilities() -> CapabilitiesResponse:
    return {
        "service": "sparkbot-server",
        "mode": "local",
        "capabilities": CAPABILITIES,
    }
