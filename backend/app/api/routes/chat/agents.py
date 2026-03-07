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


def register_agent(name: str, emoji: str, description: str, system_prompt: str) -> None:
    """Add/update an agent in the runtime registry. Call after persisting to DB."""
    _RUNTIME_AGENTS[name.lower()] = {
        "emoji": emoji,
        "description": description,
        "system_prompt": system_prompt,
    }


def unregister_agent(name: str) -> None:
    """Remove an agent from the runtime registry."""
    _RUNTIME_AGENTS.pop(name.lower(), None)


def get_all_agents() -> dict[str, dict]:
    """Return the full merged registry: built-ins + env-loaded + runtime DB agents."""
    return {**BUILT_IN_AGENTS, **_load_custom_agents(), **_RUNTIME_AGENTS}


def load_db_agents_into_registry(session) -> None:
    """Load all custom agents from DB into the runtime registry. Call at startup."""
    from sqlmodel import select
    from app.models import CustomAgent
    try:
        for a in session.exec(select(CustomAgent)).all():
            register_agent(a.name, a.emoji, a.description, a.system_prompt)
    except Exception:
        pass  # DB may not be ready yet at first boot


# Keep AGENTS as a backward-compat alias for the static snapshot (used by imports)
AGENTS: dict[str, dict] = {**BUILT_IN_AGENTS, **_load_custom_agents()}


def get_agent(name: str) -> Optional[dict]:
    """Return agent dict for a name, or None if not found."""
    return get_all_agents().get(name.lower())


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
    if candidate not in get_all_agents():
        return None, content  # not a known agent — treat as regular message
    stripped = match.group(2).strip()
    return candidate, stripped or content  # if nothing after @agent, use full content


def agents_list_text() -> str:
    """Return a formatted agent list for display in chat."""
    lines = ["**Available agents** — mention with @name:"]
    for name, info in get_all_agents().items():
        lines.append(f"{info['emoji']} **@{name}** — {info['description']}")
    lines.append("\nExample: `@researcher what's the latest on quantum computing?`")
    return "\n".join(lines)
