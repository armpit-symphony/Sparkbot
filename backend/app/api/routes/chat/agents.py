"""
Sparkbot agent registry.

Defines built-in named agents (researcher, coder, writer, analyst) that can
be invoked from chat with @mention syntax: "@researcher what's the latest on X?"

Each agent has a name, emoji, description, and system prompt override. The
default "sparkbot" agent uses the base SYSTEM_PROMPT from llm.py.

Custom agents can be added via the SPARKBOT_AGENTS_JSON environment variable:
  [{"name": "sysadmin", "emoji": "🖥️", "description": "...", "system_prompt": "..."}]
"""
import json
import os
from typing import Optional

# ─── Built-in agents ──────────────────────────────────────────────────────────

BUILT_IN_AGENTS: dict[str, dict] = {
    "researcher": {
        "emoji": "🔍",
        "description": "Research specialist — finds accurate info, cites sources, searches the web",
        "system_prompt": (
            "You are the Researcher agent for Sparkpit Labs. "
            "You specialize in finding accurate, up-to-date information. "
            "Use the web_search tool proactively for any factual question, current event, or statistic. "
            "Always cite sources. Be thorough, balanced, and analytical in your responses."
        ),
    },
    "coder": {
        "emoji": "💻",
        "description": "Software engineer — writes clean, working code with clear explanations",
        "system_prompt": (
            "You are the Coder agent for Sparkpit Labs. "
            "You specialize in software engineering across all languages and frameworks. "
            "Provide precise, working code. Prefer idiomatic, clean solutions. "
            "Always explain the code and any trade-offs. "
            "Ask clarifying questions if requirements are ambiguous before writing code."
        ),
    },
    "writer": {
        "emoji": "✍️",
        "description": "Professional writer — drafts, edits, and structures content clearly",
        "system_prompt": (
            "You are the Writer agent for Sparkpit Labs. "
            "You specialize in writing, editing, and content creation. "
            "Produce clear, engaging, well-structured prose tailored to the audience and purpose. "
            "Help with emails, documentation, summaries, blog posts, and any written content. "
            "Offer multiple options when tone or style choices matter."
        ),
    },
    "analyst": {
        "emoji": "📊",
        "description": "Data analyst — structured reasoning, logic, and actionable insights",
        "system_prompt": (
            "You are the Analyst agent for Sparkpit Labs. "
            "You specialize in structured problem-solving, data analysis, and logical reasoning. "
            "Break complex problems into clear components. Use the calculate tool for quantitative work. "
            "Present findings with evidence and clear, actionable recommendations. "
            "Be concise and precise — avoid vague generalisations."
        ),
    },
    "workstation_backup_1": {
        "emoji": "🧭",
        "description": "Workstation companion 01 — second opinion and practical alternatives",
        "system_prompt": (
            "You are Workstation Companion 01. "
            "Your job is to add a distinct second opinion, surface tradeoffs, and improve the plan without repeating the chair. "
            "Favor concrete alternatives, missing constraints, and practical next steps."
        ),
    },
    "workstation_backup_2": {
        "emoji": "🛠️",
        "description": "Workstation companion 02 — implementation and risk detail",
        "system_prompt": (
            "You are Workstation Companion 02. "
            "Your job is to turn broad ideas into concrete execution detail. "
            "Focus on implementation steps, operational risks, dependencies, and what would break first."
        ),
    },
    "workstation_heavy_hitter": {
        "emoji": "🚀",
        "description": "Workstation heavy hitter — strongest synthesis and final recommendation",
        "system_prompt": (
            "You are the Workstation Heavy Hitter. "
            "Your job is to deliver the strongest synthesis in the room. "
            "Challenge weak assumptions, compress noise, and drive toward the highest-value recommendation."
        ),
    },
}


def _load_custom_agents() -> dict[str, dict]:
    """Load custom agents from SPARKBOT_AGENTS_JSON env var."""
    raw = os.getenv("SPARKBOT_AGENTS_JSON", "").strip()
    if not raw:
        return {}
    try:
        items = json.loads(raw)
        custom: dict[str, dict] = {}
        for item in items:
            name = str(item.get("name", "")).strip().lower()
            if not name:
                continue
            custom[name] = {
                "emoji": str(item.get("emoji", "🤖")),
                "description": str(item.get("description", "")),
                "system_prompt": str(item.get("system_prompt", "")),
            }
        return custom
    except Exception:
        return {}


# ─── Runtime registry (DB-loaded + hot-spawned agents) ───────────────────────

_RUNTIME_AGENTS: dict[str, dict] = {}
_RUNTIME_AGENT_IDENTITIES: dict[str, dict] = {}


def _disabled_agents() -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv("SPARKBOT_DISABLED_AGENTS", "").split(",")
        if item.strip()
    }


def _identity_overrides() -> dict[str, dict]:
    raw = os.getenv("SPARKBOT_AGENT_IDENTITY_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = [{"name": name, **value} for name, value in parsed.items() if isinstance(value, dict)]
    else:
        return {}
    overrides: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        overrides[name] = item
    return overrides


def _as_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(fallback)


def _default_identity(name: str, info: dict, *, is_builtin: bool) -> dict:
    purpose = str(info.get("description") or "General Sparkbot agent").strip()
    if name == "researcher":
        scopes = ["web_research", "knowledge_read", "citation"]
        allowed_tools = ["web_search", "fetch_url", "memory_recall"]
        risk_tier = "low"
    elif name == "coder":
        scopes = ["code_help", "diagnostics", "documentation"]
        allowed_tools = ["read_tools", "policy_gated_execute"]
        risk_tier = "medium"
    elif name == "analyst":
        scopes = ["analysis", "calculation", "structured_reasoning"]
        allowed_tools = ["calculate", "memory_recall"]
        risk_tier = "low"
    elif name == "writer":
        scopes = ["drafting", "editing", "summarization"]
        allowed_tools = ["memory_recall"]
        risk_tier = "low"
    else:
        scopes = ["chat", "room_context"]
        allowed_tools = ["policy_registry"]
        risk_tier = "medium" if is_builtin else "standard"
    return {
        "owner": "sparkbot-core" if is_builtin else "local-operator",
        "purpose": purpose,
        "scopes": scopes,
        "allowed_tools": allowed_tools,
        "expires_at": None,
        "risk_tier": risk_tier,
        "kill_switch": name in _disabled_agents(),
    }


def _merge_identity(name: str, info: dict, *, is_builtin: bool) -> dict:
    identity = _default_identity(name, info, is_builtin=is_builtin)
    identity.update(_RUNTIME_AGENT_IDENTITIES.get(name, {}))
    override = _identity_overrides().get(name, {})
    if override:
        identity.update(
            {
                "owner": str(override.get("owner") or identity["owner"]),
                "purpose": str(override.get("purpose") or identity["purpose"]),
                "expires_at": override.get("expires_at", identity["expires_at"]),
                "risk_tier": str(override.get("risk_tier") or identity["risk_tier"]),
                "kill_switch": bool(override.get("kill_switch", identity["kill_switch"])),
            }
        )
        identity["scopes"] = _as_list(override.get("scopes"), identity["scopes"])
        identity["allowed_tools"] = _as_list(override.get("allowed_tools"), identity["allowed_tools"])
    identity["kill_switch"] = bool(identity.get("kill_switch")) or name in _disabled_agents()
    return identity


def register_agent(
    name: str,
    emoji: str,
    description: str,
    system_prompt: str,
    *,
    identity: dict | None = None,
) -> None:
    """Add/update an agent in the runtime registry. Call after persisting to DB."""
    normalized = name.lower()
    _RUNTIME_AGENTS[normalized] = {
        "emoji": emoji,
        "description": description,
        "system_prompt": system_prompt,
    }
    if identity:
        _RUNTIME_AGENT_IDENTITIES[normalized] = identity


def unregister_agent(name: str) -> None:
    """Remove an agent from the runtime registry."""
    normalized = name.lower()
    _RUNTIME_AGENTS.pop(normalized, None)
    _RUNTIME_AGENT_IDENTITIES.pop(normalized, None)


def get_all_agents() -> dict[str, dict]:
    """Return the full merged registry: built-ins + env-loaded + runtime DB agents."""
    agents = {**BUILT_IN_AGENTS, **_load_custom_agents(), **_RUNTIME_AGENTS}
    enriched: dict[str, dict] = {}
    for name, info in agents.items():
        enriched[name] = {
            **info,
            "identity": _merge_identity(name, info, is_builtin=name in BUILT_IN_AGENTS),
        }
    return enriched


def load_db_agents_into_registry(session) -> None:
    """Load all custom agents from DB into the runtime registry. Call at startup."""
    from sqlmodel import select
    from app.models import CustomAgent
    try:
        CustomAgent.__table__.create(session.get_bind(), checkfirst=True)
        for a in session.exec(select(CustomAgent)).all():
            register_agent(a.name, a.emoji, a.description, a.system_prompt)
    except Exception:
        pass  # DB may not be ready yet at first boot


# Keep AGENTS as a backward-compat alias for the static snapshot (used by imports)
AGENTS: dict[str, dict] = {**BUILT_IN_AGENTS, **_load_custom_agents()}


def get_agent(name: str) -> Optional[dict]:
    """Return agent dict for a name, or None if not found."""
    agent = get_all_agents().get(name.lower())
    if not agent or (agent.get("identity") or {}).get("kill_switch"):
        return None
    return agent


def get_agent_identity(name: str) -> dict | None:
    agent = get_all_agents().get(name.lower())
    if not agent:
        return None
    return dict(agent.get("identity") or {})


def agent_is_enabled(name: str) -> bool:
    identity = get_agent_identity(name)
    return bool(identity) and not bool(identity.get("kill_switch"))


def resolve_agent_from_message(content: str) -> tuple[Optional[str], str]:
    """
    Check if the message starts with @agentname.

    Returns (agent_name, stripped_content) where agent_name is None if no
    valid @mention is found, and stripped_content is the message without
    the @mention prefix.
    """
    import re
    match = re.match(r"^@(\w+)\s*(.*)", content.strip(), re.DOTALL)
    if not match:
        return None, content
    candidate = match.group(1).lower()
    if candidate not in get_all_agents() or not agent_is_enabled(candidate):
        return None, content  # not a known agent — treat as regular message
    stripped = match.group(2).strip()
    return candidate, stripped or content  # if nothing after @agent, use full content


def agents_list_text() -> str:
    """Return a formatted agent list for display in chat."""
    lines = ["**Available agents** — mention with @name:"]
    for name, info in get_all_agents().items():
        if (info.get("identity") or {}).get("kill_switch"):
            continue
        lines.append(f"{info['emoji']} **@{name}** — {info['description']}")
    lines.append("\nExample: `@researcher what's the latest on quantum computing?`")
    return "\n".join(lines)
