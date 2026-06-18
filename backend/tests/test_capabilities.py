from fastapi.testclient import TestClient

from app.api.capabilities import ALLOWED_CAPABILITY_STATUSES
from app.main import app


def _capability_by_id(payload: dict) -> dict[str, dict]:
    return {item["id"]: item for item in payload["capabilities"]}


def test_capabilities_are_static_and_public_safe() -> None:
    client = TestClient(app)
    response = client.get("/capabilities")

    assert response.status_code == 200
    payload = response.json()

    assert payload["service"] == "sparkbot-server"
    assert payload["mode"] == "local"
    assert payload["capabilities"] == [
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


def test_capability_statuses_use_contract_values() -> None:
    client = TestClient(app)
    payload = client.get("/capabilities").json()

    assert ALLOWED_CAPABILITY_STATUSES == {
        "available",
        "preview",
        "planned",
        "disabled-by-default",
        "guarded-future",
    }
    statuses = {item["status"] for item in payload["capabilities"]}
    assert statuses <= ALLOWED_CAPABILITY_STATUSES
    assert "guarded-future" in statuses


def test_guarded_future_capabilities_are_present_and_inactive() -> None:
    client = TestClient(app)
    payload = client.get("/capabilities").json()
    capabilities = _capability_by_id(payload)

    for capability_id in ["connectors", "model-calls", "credential-storage", "tool-execution"]:
        assert capabilities[capability_id]["status"] == "guarded-future"

    inactive_notes = " ".join(item["notes"].lower() for item in payload["capabilities"])
    assert "no file reads" in inactive_notes
    assert "file writes" in inactive_notes
    assert "no connector calls" in inactive_notes
    assert "external sends" in inactive_notes
    assert "endpoint checks" in inactive_notes
    assert "no provider runtime" in inactive_notes
    assert "no credential entry" in inactive_notes
    assert "no terminal" in inactive_notes
    assert "available" not in {
        capabilities["connectors"]["status"],
        capabilities["model-calls"]["status"],
        capabilities["credential-storage"]["status"],
        capabilities["tool-execution"]["status"],
    }


def test_preview_shell_capabilities_do_not_claim_runtime_operation() -> None:
    client = TestClient(app)
    payload = client.get("/capabilities").json()
    capabilities = _capability_by_id(payload)

    preview_expectations = {
        "chat": ["no model calls", "message persistence"],
        "work-page": ["no file reads", "file writes", "connector calls"],
        "round-table": ["no meeting engine", "agent orchestration"],
        "provider-setup": ["no credential storage", "provider calls"],
        "local-ai-settings": ["no credentials", "endpoint checks", "provider calls", "model routing"],
        "guardian-controls": ["no policy enforcement runtime"],
    }

    for capability_id, expected_note_fragments in preview_expectations.items():
        capability = capabilities[capability_id]
        assert capability["status"] == "preview"
        assert capability["status"] != "available"
        notes = capability["notes"].lower()
        for fragment in expected_note_fragments:
            assert fragment in notes
