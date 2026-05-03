from app.api.routes.chat.agents import (
    BUILT_IN_AGENTS,
    agent_is_enabled,
    get_all_agents,
    resolve_agent_from_message,
)
from app.api.routes.chat.model import list_agents
from app.services.guardian.governance import connector_health, evaluation_summary, workflow_templates
from app.services.guardian.tool_guardrails import validate_tool_input


def test_agent_identity_metadata_and_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_DISABLED_AGENTS", "researcher")
    agents = get_all_agents()

    identity = agents["researcher"]["identity"]
    assert identity["owner"] == "sparkbot-core"
    assert identity["kill_switch"] is True
    assert agent_is_enabled("researcher") is False
    assert resolve_agent_from_message("@researcher check this") == (None, "@researcher check this")


def test_packaged_specialist_agents_are_registered() -> None:
    expected = {
        "meetings_manager": "Plans, runs, summarizes, and follows up on meetings with clear agendas, decisions, action items, owners, deadlines, and operator-ready recaps.",
        "web_designer": "Designs clean, modern, responsive web pages and product experiences with strong layout, copy structure, visual hierarchy, and implementation-ready specs.",
        "marketing_agent": "Creates practical marketing strategy, landing page copy, launch messaging, social posts, positioning, and campaign plans for SparkPit Labs products and services.",
        "business_analyst": "Turns ideas, products, operations, and technical plans into clear business requirements, risks, priorities, metrics, workflows, and execution-ready recommendations.",
    }

    for name, description in expected.items():
        assert name in BUILT_IN_AGENTS
        assert BUILT_IN_AGENTS[name]["description"] == description
        assert BUILT_IN_AGENTS[name]["system_prompt"].startswith(f"You are {name.replace('_', ' ').title()}")
        assert get_all_agents()[name]["identity"]["owner"] == "sparkbot-core"

    assert len(BUILT_IN_AGENTS) == len(set(BUILT_IN_AGENTS))


def test_packaged_specialist_agents_are_returned_by_api_registry() -> None:
    payload = list_agents(current_user=object())
    names = {item["name"] for item in payload["agents"]}

    assert {
        "meetings_manager",
        "web_designer",
        "marketing_agent",
        "business_analyst",
    }.issubset(names)


def test_tool_guardrail_rejects_secret_like_payload() -> None:
    result = validate_tool_input("gmail_send", {"to": "a@example.com", "api_key": "secret", "body": "hi"})

    assert result.allowed is False
    assert result.behavior == "rejectContent"
    assert "Guardian Vault" in result.reason


def test_workflow_templates_and_connector_health_are_available() -> None:
    templates = workflow_templates()
    connectors = connector_health()

    assert any(item["id"] == "morning_brief" for item in templates)
    assert any(item["id"] == "github" for item in connectors)
    assert all("read_scopes" in item and "write_scopes" in item for item in connectors)


def test_evaluation_summary_runs_baseline_cases(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    summary = evaluation_summary()

    assert summary["failed"] == 0
    assert summary["passed"] >= 4
