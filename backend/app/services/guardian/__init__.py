"""Guardian service integrations for Sparkbot."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .suite import GuardianComponent, GuardianSuite


def get_guardian_suite():
    from .suite import get_guardian_suite as _get_guardian_suite

    return _get_guardian_suite()


def guardian_suite_inventory() -> list[dict[str, str]]:
    from .suite import guardian_suite_inventory as _guardian_suite_inventory

    return _guardian_suite_inventory()


def __getattr__(name: str) -> Any:
    if name in {"GuardianComponent", "GuardianSuite", "guardian_suite"}:
        from . import suite as guardian_suite_module

        return getattr(guardian_suite_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["GuardianComponent", "GuardianSuite", "get_guardian_suite", "guardian_suite", "guardian_suite_inventory"]
