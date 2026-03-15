"""Unified Guardian suite entrypoint for Sparkbot.

This file provides a single import surface for the Guardian stack so the
integration can be treated as one suite even though the implementation still
uses focused modules internally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import auth, executive, meeting_recorder, memory, pending_approvals, policy, task_guardian, token_guardian, vault, verifier


@dataclass(frozen=True)
class GuardianComponent:
    name: str
    module: Any
    description: str


@dataclass(frozen=True)
class GuardianSuite:
    auth: Any
    executive: Any
    meeting_recorder: Any
    memory: Any
    pending_approvals: Any
    policy: Any
    task_guardian: Any
    token_guardian: Any
    vault: Any
    verifier: Any

    def components(self) -> tuple[GuardianComponent, ...]:
        return (
            GuardianComponent("auth", self.auth, "Guardian authority, operator identity, break-glass, and session gating."),
            GuardianComponent("executive", self.executive, "Executive journaling and guarded execution wrappers."),
            GuardianComponent("meeting_recorder", self.meeting_recorder, "Meeting and decision artifact generation."),
            GuardianComponent("memory", self.memory, "Memory Guardian adapter and recall utilities."),
            GuardianComponent("pending_approvals", self.pending_approvals, "Pending approval storage for confirmation-gated actions."),
            GuardianComponent("policy", self.policy, "Policy registry and tool-use decision engine."),
            GuardianComponent("task_guardian", self.task_guardian, "Scheduled Guardian tasks and run history."),
            GuardianComponent("token_guardian", self.token_guardian, "Routing telemetry and model-selection guardrails."),
            GuardianComponent("vault", self.vault, "Guardian Authority Vault secret storage and reveal controls."),
            GuardianComponent("verifier", self.verifier, "Output verification and post-action review utilities."),
        )

    def inventory(self) -> list[dict[str, str]]:
        return [
            {
                "name": component.name,
                "module": getattr(component.module, "__name__", component.name),
                "description": component.description,
            }
            for component in self.components()
        ]


guardian_suite = GuardianSuite(
    auth=auth,
    executive=executive,
    meeting_recorder=meeting_recorder,
    memory=memory,
    pending_approvals=pending_approvals,
    policy=policy,
    task_guardian=task_guardian,
    token_guardian=token_guardian,
    vault=vault,
    verifier=verifier,
)


def get_guardian_suite() -> GuardianSuite:
    return guardian_suite


def guardian_suite_inventory() -> list[dict[str, str]]:
    return guardian_suite.inventory()


__all__ = [
    "GuardianComponent",
    "GuardianSuite",
    "get_guardian_suite",
    "guardian_suite",
    "guardian_suite_inventory",
]
