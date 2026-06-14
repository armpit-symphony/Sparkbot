"""Static proof checks for the Sparkbot LIMA V1-G7 packet.

These tests only read local docs, fixtures, and source text. They do not import
Sparkbot runtime modules, call models, execute tools, open connectors, or write
application state.
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/sparkbot_lima_v1_g7_integration_proof_packet.json"

REQUIRED_STATES = {
    "received",
    "thinking",
    "preview_ready",
    "blocked",
    "needs_approval",
    "completed",
    "failed_safe",
    "deferred",
}

REQUIRED_SOURCE_BACKED_STATES = {
    "received",
    "thinking",
    "preview_ready",
    "blocked",
    "needs_approval",
    "completed",
    "failed_safe",
}


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_fixture_boundary_flags_remain_static() -> None:
    data = _load_fixture()

    assert data["proof_gap_id"] == "V1-G7"
    assert data["shell_repo"] == "Sparkbot"
    assert data["proof_branch"] == "v1-g7-sparkbot-integration-proof-packet"
    assert data["can_consume_lima_contract_outputs_as_static_evidence"] is True
    assert data["can_consume_lima_runtime_outputs_live"] is False
    assert data["lima_runtime_wiring_added"] is False
    assert data["lima_runtime_behavior_added"] is False
    assert data["runtime_exports_required_from_lima"] == []
    assert data["runtime_exports_changed_in_lima"] is False
    assert data["sparkbot_code_copied_to_lima"] is False
    assert data["sparkbot_imported_by_lima"] is False
    assert data["lima_imported_by_shell_runtime"] is False
    assert data["production_readiness_claimed"] is False
    assert data["v1_product_readiness_claimed"] is False
    assert data["accepted_as_static_shell_evidence"] is True
    assert data["accepted_as_live_runtime_parity"] is False


def test_required_docs_and_fixture_files_exist() -> None:
    data = _load_fixture()

    for rel_path in data["proof_packet_files"]:
        assert (REPO_ROOT / rel_path).exists(), rel_path


def test_required_response_states_and_status_mappings_are_evaluated() -> None:
    data = _load_fixture()

    assert set(data["shell_response_states_evaluated"]) == REQUIRED_STATES
    assert set(data["source_backed_shell_response_states"]) == REQUIRED_SOURCE_BACKED_STATES
    assert data["docs_fixture_only_shell_response_states"] == ["deferred"]
    assert data["missing_shell_response_states"] == []

    assert data["kernel_status_mappings"]["proposed"] == "preview_only"
    assert data["kernel_status_mappings"]["needs_review"] == "explain_plan"
    assert data["kernel_status_mappings"]["blocked"] == "blocked"
    assert {"preview_only", "explain_plan", "blocked", "completed", "deferred"}.issubset(
        set(data["packet_statuses"])
    )


def test_haptics_and_destructive_approval_boundaries() -> None:
    data = _load_fixture()

    assert data["haptic_intent_metadata_supported"] is False
    assert data["shell_owns_haptics"] is True
    assert data["lima_owns_haptic_device_behavior"] is False
    assert data["haptic_device_behavior_added"] is False
    assert data["device_haptic_command_added"] is False
    assert data["destructive_edit_delete_requires_operator_approval"] is True
    assert data["raw_natural_language_to_tool_execution_allowed"] is False


def test_sparkbot_source_contains_response_state_evidence() -> None:
    rooms = _read("backend/app/api/routes/chat/rooms.py")
    dm_page = _read("frontend/src/pages/SparkbotDmPage.tsx")
    bubble = _read("frontend/src/components/chat/MessageBubble.tsx")
    chat_window = _read("frontend/src/components/chat/ChatWindow.tsx")

    assert '@router.post("/{room_id}/messages/stream")' in rooms
    for marker in ("human_message", "token", "done", "error"):
        assert marker in rooms
    assert "confirm_required" in rooms
    assert "privileged_required" in rooms
    assert "needs_approval" in rooms
    assert "blocked" in rooms

    assert "ConfirmModal" in dm_page
    assert "pendingConfirm" in dm_page
    assert "handleConfirm" in dm_page
    assert "isStreaming" in dm_page
    assert "isStreaming" in bubble
    assert "typing" in bubble
    assert "TypingIndicator" in chat_window


def test_sparkbot_source_contains_guardian_approval_evidence() -> None:
    policy = _read("backend/app/services/guardian/policy.py")
    approvals = _read("backend/app/services/guardian/pending_approvals.py")
    dashboard = _read("backend/app/api/routes/chat/dashboard.py")

    assert 'PolicyAction = Literal["allow", "confirm", "deny", "privileged", "privileged_reveal"]' in policy
    assert "def decide_tool_use" in policy
    assert "Write-like shell command requires explicit confirmation before execution." in policy
    assert "Edits, deletes, sends, and critical changes still require yes/no confirmation." in policy

    for marker in (
        "def store_pending_approval",
        "def consume_pending_approval",
        "def discard_pending_approval",
        "def list_pending_approvals",
        "approval.required",
        "approval.granted",
        "approval.discarded",
    ):
        assert marker in approvals

    assert "async def _execute_dashboard_approval" in dashboard
    assert 'decision.action not in {"allow", "confirm"}' in dashboard
    assert '"/dashboard/approvals/{confirm_id}/approve"' in dashboard
    assert '"/dashboard/approvals/{confirm_id}/deny"' in dashboard


def test_sparkbot_source_contains_provider_model_routing_evidence() -> None:
    llm = _read("backend/app/api/routes/chat/llm.py")
    model_seats = _read("backend/app/services/model_seats.py")
    controls = _read("frontend/src/lib/sparkbotControls.ts")

    assert "VALID_AGENT_ROUTES" in llm
    for route in ("openrouter", "local_ai", "openai_codex", "claude_sub", "anthropic", "google", "groq", "minimax", "xai"):
        assert route in llm
    assert "def get_agent_route_context" in llm
    assert "async def _stream_text_with_fallback" in llm
    assert "async def stream_chat_with_tools" in llm
    assert "stream=True" in llm
    assert "def record_latency" in llm
    assert "def record_model_error" in llm

    assert "def normalize_model_seat_provider" in model_seats
    assert "providerForModel" in controls
    assert "routeForModelOverride" in controls
    assert "resolveControlsModelSelection" in controls


def test_sparkbot_source_contains_preview_audit_and_robo_boundary_evidence() -> None:
    capabilities = _read("docs/capabilities.md")
    tools = _read("backend/app/api/routes/chat/tools.py")
    mcp = _read("backend/app/api/routes/chat/mcp.py")
    mcp_registry = _read("backend/app/services/mcp_registry.py")
    spine = _read("backend/app/services/guardian/spine.py")
    spine_client = _read("frontend/src/lib/spine.ts")

    assert "guardian_simulate_policy" in capabilities
    assert "without executing" in capabilities
    assert "guardian_simulate_policy" in tools
    assert "without executing the tool" in tools
    assert '@router.post("/mcp/explain-plan")' in mcp
    assert "without executing anything" in mcp
    assert "preview-only" in mcp_registry
    assert "Public Robo Preview does not expose live stop or emergency-control paths." in mcp_registry

    assert "CREATE TABLE IF NOT EXISTS guardian_spine_tasks" in spine
    assert "CREATE TABLE IF NOT EXISTS guardian_spine_events" in spine
    assert "CREATE TABLE IF NOT EXISTS guardian_spine_approvals" in spine
    assert "approval-waiting" in spine_client
    assert "/api/v1/chat/spine/operator" in spine_client


def test_no_haptic_device_vibration_implementation_in_source_roots() -> None:
    source_roots = [
        REPO_ROOT / "backend/app",
        REPO_ROOT / "frontend/src",
    ]
    forbidden = ("navigator.vibrate", ".vibrate(", "Vibration API")

    for root in source_roots:
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".py", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                assert marker not in text, f"{marker} found in {path.relative_to(REPO_ROOT)}"
