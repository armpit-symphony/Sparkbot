"""
Skills discovery endpoint.

GET /api/v1/chat/skills — returns the list of loaded skill plugins with their
definition (name, description) and policy (scope, action_type, high_risk,
requires_execution_gate).

Read-only, authenticated. Used by the frontend skill marketplace panel to show
what capabilities are available without needing to query the LLM.
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentChatUser

router = APIRouter(tags=["chat-skills"])


@router.get("/skills")
async def list_skills(current_user: CurrentChatUser):
    """Return all loaded skill plugins with name, description, and policy."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    from app.services.skills import _registry as _skill_registry

    skills_out = []
    for defn in _skill_registry.definitions:
        fn = defn.get("function", {})
        name = fn.get("name", "")
        description = fn.get("description", "")
        policy = _skill_registry.policies.get(name, {})
        skills_out.append({
            "name": name,
            "description": description,
            "scope": policy.get("scope", "read"),
            "action_type": policy.get("action_type", "read"),
            "high_risk": bool(policy.get("high_risk", False)),
            "requires_execution_gate": bool(policy.get("requires_execution_gate", False)),
            "default_action": policy.get("default_action", "allow"),
        })

    return {"skills": skills_out}
