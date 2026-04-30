"""
Sparkbot skill plugin loader.

Any .py file dropped into the skills/ directory (default: backend/skills/) is
auto-discovered at startup. Each file must export:
  - DEFINITION: OpenAI function-calling schema dict
  - execute: async function(args, *, user_id=None, room_id=None, session=None) -> str

Optionally:
  - POLICY: dict matching ToolPolicy fields (defaults to read/allow if omitted)

Set SPARKBOT_SKILLS_DIR env var to override the directory (relative to backend/
or absolute).
"""
import importlib.util
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

_DEFAULT_POLICY = {
    "scope": "read",
    "resource": "workspace",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


@dataclass
class _SkillRegistry:
    definitions: list[dict] = field(default_factory=list)
    executors: dict[str, Callable] = field(default_factory=dict)
    policies: dict[str, dict] = field(default_factory=dict)


_registry = _SkillRegistry()


def _normalise_definition(raw: dict) -> dict | None:
    """Accept either OpenAI-wrapped or flat tool definitions.

    Wrapped: {"type": "function", "function": {"name": ..., ...}}
    Flat:    {"name": ..., "description": ..., "parameters": ...}
    Returns the wrapped form, or None if the shape is unrecognisable.
    """
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("function"), dict) and raw["function"].get("name"):
        wrapped = dict(raw)
        wrapped.setdefault("type", "function")
        return wrapped
    if raw.get("name"):
        return {"type": "function", "function": dict(raw)}
    return None


def _load() -> None:
    raw = os.getenv("SPARKBOT_SKILLS_DIR", "skills").strip()
    skills_dir = Path(raw) if Path(raw).is_absolute() else Path(__file__).parents[2] / raw
    if not skills_dir.exists():
        log.debug("Skills directory %s does not exist — no skills loaded", skills_dir)
        return
    for path in sorted(skills_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"sparkbot_skill.{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "DEFINITION") or not hasattr(mod, "execute"):
                log.warning("Skill %s missing DEFINITION or execute — skipped", path.name)
                continue
            definition = _normalise_definition(mod.DEFINITION)
            if not definition:
                log.warning("Skill %s DEFINITION shape unrecognised — skipped", path.name)
                continue
            name = definition["function"]["name"]
            _registry.definitions.append(definition)
            _registry.executors[name] = mod.execute
            _registry.policies[name] = getattr(mod, "POLICY", _DEFAULT_POLICY)
            log.info("Loaded skill: %s", name)
            # Multi-tool skills may expose _register_extra(registry) to add more tools
            if hasattr(mod, "_register_extra"):
                try:
                    mod._register_extra(_registry)
                except Exception as extra_exc:
                    log.warning("Skill %s _register_extra failed: %s", path.name, extra_exc)
        except Exception as exc:
            log.warning("Failed to load skill %s: %s", path.name, exc)


_load()
