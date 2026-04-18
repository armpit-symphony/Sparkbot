"""
Skill interface smoke tests.

Validates every .py file in the skills/ directory without executing any
external calls. Catches the class of bug where a POLICY dict uses wrong
keys (e.g. 'category' instead of 'scope'), a DEFINITION is malformed, or
the execute() function has the wrong signature.

Run:
    cd backend && uv run python -m pytest tests/test_skills.py -v
"""
from __future__ import annotations

import importlib.util
import inspect
import os
from dataclasses import fields as dc_fields
from pathlib import Path

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

SKILLS_DIR = Path(__file__).parents[1] / "skills"

from app.services.guardian.policy import ToolPolicy as _ToolPolicy  # noqa: E402
_VALID_POLICY_KEYS = {f.name for f in dc_fields(_ToolPolicy)} - {"tool_name"}


def _load_skill_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_skill_test.{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _skill_paths() -> list[Path]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(p for p in SKILLS_DIR.glob("*.py") if not p.name.startswith("_"))


# ── Parametrize over all skill files ──────────────────────────────────────────

@pytest.mark.parametrize("skill_path", _skill_paths(), ids=lambda p: p.stem)
class TestSkillInterface:

    def test_imports_cleanly(self, skill_path: Path):
        """Skill must import without raising."""
        _load_skill_module(skill_path)

    def test_has_definition(self, skill_path: Path):
        """Skill must export DEFINITION dict."""
        mod = _load_skill_module(skill_path)
        assert hasattr(mod, "DEFINITION"), f"{skill_path.name}: missing DEFINITION"
        assert isinstance(mod.DEFINITION, dict), f"{skill_path.name}: DEFINITION must be a dict"

    def test_definition_has_name(self, skill_path: Path):
        """DEFINITION must have a non-empty 'name' key (OpenAI function-calling format)."""
        mod = _load_skill_module(skill_path)
        defn = mod.DEFINITION
        # Support both flat {"name": ...} and nested {"function": {"name": ...}}
        name = defn.get("name") or (defn.get("function") or {}).get("name")
        assert name, (
            f"{skill_path.name}: DEFINITION['name'] (or DEFINITION['function']['name']) is missing or empty"
        )

    def test_definition_has_description(self, skill_path: Path):
        """DEFINITION must have a non-empty description."""
        mod = _load_skill_module(skill_path)
        defn = mod.DEFINITION
        desc = defn.get("description") or (defn.get("function") or {}).get("description")
        assert desc, f"{skill_path.name}: DEFINITION is missing a description"

    def test_definition_has_parameters(self, skill_path: Path):
        """DEFINITION must have a parameters block."""
        mod = _load_skill_module(skill_path)
        defn = mod.DEFINITION
        params = defn.get("parameters") or (defn.get("function") or {}).get("parameters")
        assert params is not None, f"{skill_path.name}: DEFINITION is missing 'parameters'"
        assert isinstance(params, dict), f"{skill_path.name}: DEFINITION['parameters'] must be a dict"

    def test_has_execute(self, skill_path: Path):
        """Skill must export an execute() coroutine function."""
        mod = _load_skill_module(skill_path)
        assert hasattr(mod, "execute"), f"{skill_path.name}: missing execute function"
        assert inspect.iscoroutinefunction(mod.execute), (
            f"{skill_path.name}: execute must be an async function (async def execute(...))"
        )

    def test_execute_signature(self, skill_path: Path):
        """execute() must accept (args, *, user_id=None, room_id=None, session=None)."""
        mod = _load_skill_module(skill_path)
        sig = inspect.signature(mod.execute)
        params = sig.parameters

        # First positional arg (args dict)
        positional = [
            name for name, p in params.items()
            if p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        assert len(positional) >= 1, (
            f"{skill_path.name}: execute() must accept at least one positional argument (args)"
        )

        # Keyword-only args
        kw_only = {name for name, p in params.items() if p.kind == inspect.Parameter.KEYWORD_ONLY}
        for expected_kw in ("user_id", "room_id", "session"):
            assert expected_kw in kw_only or expected_kw in params, (
                f"{skill_path.name}: execute() missing keyword argument '{expected_kw}'"
            )

    def test_policy_keys_valid(self, skill_path: Path):
        """If POLICY is defined, its keys must exactly match ToolPolicy fields (no 'category', no 'description')."""
        mod = _load_skill_module(skill_path)
        if not hasattr(mod, "POLICY"):
            return  # POLICY is optional

        policy = mod.POLICY
        if not isinstance(policy, dict):
            pytest.fail(f"{skill_path.name}: POLICY must be a dict, got {type(policy)}")

        invalid_keys = set(policy.keys()) - _VALID_POLICY_KEYS - {"tool_name"}
        assert not invalid_keys, (
            f"{skill_path.name}: POLICY contains invalid keys: {sorted(invalid_keys)}. "
            f"Valid keys are: {sorted(_VALID_POLICY_KEYS)}. "
            f"Remove 'category' and 'description' — use 'scope', 'resource', 'action_type' instead."
        )

        required_keys = {"scope", "resource", "default_action", "action_type"}
        missing_keys = required_keys - set(policy.keys())
        assert not missing_keys, (
            f"{skill_path.name}: POLICY is missing required keys: {sorted(missing_keys)}"
        )

    def test_policy_scope_valid(self, skill_path: Path):
        """POLICY scope must be one of the allowed PolicyScope values."""
        mod = _load_skill_module(skill_path)
        if not hasattr(mod, "POLICY") or not isinstance(mod.POLICY, dict):
            return
        scope = mod.POLICY.get("scope")
        valid_scopes = {"read", "write", "execute", "admin"}
        assert scope in valid_scopes, (
            f"{skill_path.name}: POLICY['scope'] = {scope!r} is not valid. "
            f"Must be one of: {sorted(valid_scopes)}"
        )

    def test_policy_default_action_valid(self, skill_path: Path):
        """POLICY default_action must be allow, confirm, or deny."""
        mod = _load_skill_module(skill_path)
        if not hasattr(mod, "POLICY") or not isinstance(mod.POLICY, dict):
            return
        action = mod.POLICY.get("default_action")
        valid_actions = {"allow", "confirm", "deny"}
        assert action in valid_actions, (
            f"{skill_path.name}: POLICY['default_action'] = {action!r} is not valid. "
            f"Must be one of: {sorted(valid_actions)}"
        )


# ── Multi-tool skill extra registration ───────────────────────────────────────

@pytest.mark.parametrize("skill_path", _skill_paths(), ids=lambda p: p.stem)
def test_register_extra_does_not_crash(skill_path: Path):
    """If _register_extra is defined, calling it with a mock registry must not raise."""
    mod = _load_skill_module(skill_path)
    if not hasattr(mod, "_register_extra"):
        return

    class _MockRegistry:
        definitions: list = []
        executors: dict = {}
        policies: dict = {}

    try:
        mod._register_extra(_MockRegistry())
    except Exception as exc:
        pytest.fail(f"{skill_path.name}: _register_extra raised: {exc}")
