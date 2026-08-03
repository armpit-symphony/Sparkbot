from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new
from pathlib import Path
from time import monotonic
from typing import Any

import os


ActionClass = str

OPEN_ACTIONS = frozenset({"read", "status", "health"})
CONFIRM_REQUIRED_ACTIONS = frozenset(
    {
        "chat_execution",
        "connectors",
        "terminal",
        "web",
        "model-calls",
        "tool-execution",
    }
)
ANOMALY_ACTIONS = CONFIRM_REQUIRED_ACTIONS

SAFE_DEFAULT_FEATURE_FLAGS = {
    "chat_execution": True,
    "connectors": True,
    "terminal": True,
    "web": True,
    "model-calls": True,
    "tool-execution": True,
}

DEFAULT_AUDIT_RETENTION = 500


@dataclass
class CommandCenterAction:
    action_id: str
    action_name: str
    action_class: ActionClass
    feature: str
    tenant_id: str = "default"
    user_id: str = "default"
    operator_confirmation: bool = False
    policy_token: str | None = None
    break_glass: bool = False
    connector: str | None = None
    simulate_fault: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    code: str
    allowed: bool
    requires_confirmation: bool = False
    message: str = ""
    http_status: int = 200
    decision_id: str = ""


@dataclass
class CommandCenterAuditEvent:
    decision_id: str
    sequence: int
    timestamp: str
    tenant_id: str
    user_id: str
    action_id: str
    action_name: str
    action_class: str
    feature: str
    decision_code: str
    message: str
    requires_confirmation: bool
    break_glass: bool
    policy_health: str
    queue_depth: int
    chain_hash: str


class CommandCenterSafetyEngine:
    def __init__(
        self,
        *,
        policy_token: str = "public-command-center-policy-token",
        audit_file: str | None = None,
        audit_signing_key: str | None = None,
        audit_retention: int = DEFAULT_AUDIT_RETENTION,
    ) -> None:
        self._policy_token = policy_token
        self.safe_mode = True
        self.global_kill_switch = False
        self.rollback_mode = False
        self.static_shell_fallback = False
        self.policy_health = "healthy"
        self.rate_limit_per_tenant_per_min = 60
        self.anomaly_cap_per_tenant_per_min = 18
        self.queue_backlog_limit = 32
        self.feature_flags = SAFE_DEFAULT_FEATURE_FLAGS.copy()
        self.connector_allow = {"slack", "github", "discord"}
        self.connector_deny: set[str] = set()
        self._sequence = 0
        self._queue: deque[float] = deque()
        self._tenant_queue: dict[str, deque[float]] = defaultdict(deque)
        self._tenant_anomaly_queue: dict[str, deque[float]] = defaultdict(deque)
        self._last_hash = "0" * 64
        self.audit_retention = max(1, audit_retention)
        self.audit_signing_key = audit_signing_key
        self.audit_alerts: list[str] = []
        self._audit_file: Path | None = Path(audit_file).expanduser().resolve() if audit_file else None
        if self._audit_file is not None:
            self._audit_file.parent.mkdir(parents=True, exist_ok=True)
        self._audit: list[CommandCenterAuditEvent] = []
        self._load_existing_audit()

    def reset_for_tests(self) -> None:
        self.safe_mode = True
        self.global_kill_switch = False
        self.rollback_mode = False
        self.static_shell_fallback = False
        self.policy_health = "healthy"
        self.rate_limit_per_tenant_per_min = 60
        self.anomaly_cap_per_tenant_per_min = 18
        self.queue_backlog_limit = 32
        self.feature_flags = SAFE_DEFAULT_FEATURE_FLAGS.copy()
        self.connector_allow = {"slack", "github", "discord"}
        self.connector_deny = set()
        self._sequence = 0
        self._queue.clear()
        self._tenant_queue.clear()
        self._tenant_anomaly_queue.clear()
        self._last_hash = "0" * 64
        self.audit_alerts = []
        self._audit = []
        if self._audit_file is not None and self._audit_file.exists():
            self._audit_file.unlink()

    @property
    def policy_token(self) -> str:
        return self._policy_token

    @policy_token.setter
    def policy_token(self, token: str) -> None:
        self._policy_token = token

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _new_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _actor_key(self, tenant_id: str, user_id: str) -> str:
        return f"{tenant_id}:{user_id}"

    def _drain_older(self, bucket: deque[float], window_seconds: int) -> None:
        threshold = monotonic() - window_seconds
        while bucket and bucket[0] < threshold:
            bucket.popleft()

    def _audit_redaction_rules(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = key.lower()
            if any(secret in lowered for secret in {"secret", "token", "apikey", "api_key", "password"}):
                redacted[key] = "***redacted***"
            elif isinstance(value, dict):
                redacted[key] = self._audit_redaction_rules(value)
            elif isinstance(value, list):
                redacted[key] = [
                    item if not isinstance(item, dict) else self._audit_redaction_rules(item)
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted

    def _check_rate_limits(self, tenant_id: str, user_id: str, *, is_high_risk: bool) -> PolicyDecision | None:
        actor = self._actor_key(tenant_id, user_id)
        now = monotonic()
        per_minute = self._tenant_queue[actor]
        self._drain_older(per_minute, 60)
        if len(per_minute) >= self.rate_limit_per_tenant_per_min:
            return PolicyDecision(
                code="tenant-rate-limit",
                allowed=False,
                message=f"tenant {tenant_id} user {user_id} rate limit exceeded",
                http_status=429,
            )
        per_minute.append(now)

        if is_high_risk:
            anomalies = self._tenant_anomaly_queue[actor]
            self._drain_older(anomalies, 60)
            if len(anomalies) >= self.anomaly_cap_per_tenant_per_min:
                return PolicyDecision(
                    code="tenant-anomaly-cap",
                    allowed=False,
                    message="high-risk anomaly cap reached",
                    http_status=429,
                )
            anomalies.append(now)

        self._drain_older(self._queue, 10)
        if len(self._queue) > self.queue_backlog_limit:
            return PolicyDecision(
                code="queue-backlog",
                allowed=False,
                message="command center queue backlog exceeded",
                http_status=429,
            )
        self._queue.append(now)
        return None

    def _load_existing_audit(self) -> None:
        if self._audit_file is None or not self._audit_file.exists():
            return
        try:
            lines = deque(self._audit_file.read_text(encoding="utf-8").splitlines(), maxlen=self.audit_retention)
        except OSError:
            return

        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            try:
                event = CommandCenterAuditEvent(
                    decision_id=str(record["decision_id"]),
                    sequence=int(record["sequence"]),
                    timestamp=str(record["timestamp"]),
                    tenant_id=str(record["tenant_id"]),
                    user_id=str(record["user_id"]),
                    action_id=str(record["action_id"]),
                    action_name=str(record["action_name"]),
                    action_class=str(record["action_class"]),
                    feature=str(record["feature"]),
                    decision_code=str(record["decision_code"]),
                    message=str(record["message"]),
                    requires_confirmation=bool(record["requires_confirmation"]),
                    break_glass=bool(record["break_glass"]),
                    policy_health=str(record["policy_health"]),
                    queue_depth=int(record["queue_depth"]),
                    chain_hash=str(record["chain_hash"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._audit.append(event)
            self._sequence = max(self._sequence, event.sequence)
            self._last_hash = event.chain_hash

    def _hash_chain_append(self, event: dict[str, Any]) -> str:
        event_blob = {
            "prev": self._last_hash,
            "event": event,
        }
        event_bytes = str(sorted(event_blob.items())).encode("utf-8")
        self._last_hash = sha256(event_bytes).hexdigest()
        return self._last_hash

    def _sign_chain_payload(self, payload: dict[str, Any]) -> str | None:
        if not self.audit_signing_key:
            return None
        body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hmac_new(key=self.audit_signing_key.encode("utf-8"), msg=body, digestmod=sha256).hexdigest()

    def _append_audit_file(self, event: dict[str, Any]) -> None:
        if self._audit_file is None:
            return
        record = event.copy()
        signature = self._sign_chain_payload(record)
        if signature is not None:
            record["signature"] = signature
        try:
            with self._audit_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True, ensure_ascii=True))
                fh.write("\n")
        except OSError:
            return

        if len(self._audit) > self.audit_retention:
            try:
                lines = []
                for audit_event in self._audit[-self.audit_retention :]:
                    payload = asdict(audit_event)
                    signature = self._sign_chain_payload(payload)
                    if signature is not None:
                        payload["signature"] = signature
                    lines.append(json.dumps(payload, sort_keys=True, ensure_ascii=True))
                self._audit_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except OSError:
                return

    def _record_and_return_decision(
        self,
        action: CommandCenterAction,
        code: str,
        *,
        allowed: bool,
        requires_confirmation: bool = False,
        message: str,
        status: int = 200,
        decision_id: str | None = None,
    ) -> PolicyDecision:
        if decision_id is None:
            decision_id = sha256(f"{monotonic()}-{action.action_id}-{code}".encode("utf-8")).hexdigest()
        decision = PolicyDecision(
            code=code,
            allowed=allowed,
            requires_confirmation=requires_confirmation,
            message=message,
            http_status=status,
            decision_id=decision_id,
        )
        self._append_audit(action=action, tenant_id=action.tenant_id, user_id=action.user_id, decision=decision)
        if decision.code in {
            "provider-timeout",
            "bad-credentials",
            "tenant-rate-limit",
            "tenant-anomaly-cap",
            "queue-backlog",
            "policy-unavailable",
            "kill-switch-active",
            "rollback-mode",
        }:
            self.audit_alerts.append(f"{decision.code}:{decision.message}")
            if len(self.audit_alerts) > 200:
                self.audit_alerts = self.audit_alerts[-200:]
        return decision

    def _append_audit(self, *, tenant_id: str, user_id: str, action: CommandCenterAction, decision: PolicyDecision) -> CommandCenterAuditEvent:
        sequence = self._new_sequence()
        event = CommandCenterAuditEvent(
            decision_id=decision.decision_id,
            sequence=sequence,
            timestamp=self._timestamp(),
            tenant_id=tenant_id,
            user_id=user_id,
            action_id=action.action_id,
            action_name=action.action_name,
            action_class=action.action_class,
            feature=action.feature,
            decision_code=decision.code,
            message=decision.message,
            requires_confirmation=decision.requires_confirmation,
            break_glass=action.break_glass,
            policy_health=self.policy_health,
            queue_depth=len(self._queue),
            chain_hash="",
        )
        redacted_payload = asdict(event)
        redacted_payload.pop("chain_hash")
        redacted_payload["event_id"] = redacted_payload.pop("decision_id")
        redacted_payload["payload"] = self._audit_redaction_rules(action.payload)
        event.chain_hash = self._hash_chain_append(redacted_payload)
        self._audit.append(event)
        if len(self._audit) > self.audit_retention:
            self._audit = self._audit[-self.audit_retention :]
        self._append_audit_file(redacted_payload | {
            "sequence": event.sequence,
            "decision_id": event.decision_id,
            "tenant_id": event.tenant_id,
            "user_id": event.user_id,
            "timestamp": event.timestamp,
            "action_id": event.action_id,
            "action_name": event.action_name,
            "action_class": event.action_class,
            "feature": event.feature,
            "decision_code": event.decision_code,
            "message": event.message,
            "requires_confirmation": event.requires_confirmation,
            "break_glass": event.break_glass,
            "policy_health": event.policy_health,
            "queue_depth": event.queue_depth,
            "chain_hash": event.chain_hash,
        })
        return event

    def evaluate_action(self, action: CommandCenterAction) -> PolicyDecision:
        if self.global_kill_switch and action.action_class not in OPEN_ACTIONS:
            return self._record_and_return_decision(
                action=action,
                code="kill-switch-active",
                allowed=False,
                message="operator emergency stop is active",
                status=423,
            )

        if self.rollback_mode and action.action_class not in OPEN_ACTIONS:
            return self._record_and_return_decision(
                action=action,
                code="rollback-mode",
                allowed=False,
                message="rollback mode is active: runtime actions are disabled",
                status=423,
            )

        if action.feature not in self.feature_flags:
            return self._record_and_return_decision(
                action=action,
                code="unknown-feature",
                allowed=False,
                message=f"feature '{action.feature}' is not registered",
                status=400,
            )

        if not self.feature_flags[action.feature] and action.action_class not in OPEN_ACTIONS:
            return self._record_and_return_decision(
                action=action,
                code="feature-disabled",
                allowed=False,
                message=f"feature '{action.feature}' is disabled",
                status=403,
            )

        if self.policy_health != "healthy" and action.action_class not in OPEN_ACTIONS:
            return self._record_and_return_decision(
                action=action,
                code="policy-unavailable",
                allowed=False,
                message="policy engine unhealthy; closing all mutating actions",
                status=503,
            )

        limit_decision = self._check_rate_limits(
            action.tenant_id,
            action.user_id,
            is_high_risk=action.action_class in ANOMALY_ACTIONS,
        )
        if limit_decision is not None:
            limit_decision.decision_id = sha256(
                f"{monotonic()}-{action.action_id}-limit".encode("utf-8")
            ).hexdigest()
            return self._append_and_return(action=action, decision=limit_decision)

        if action.simulate_fault:
            if action.simulate_fault == "provider_timeout":
                return self._record_and_return_decision(
                    action=action,
                    code="provider-timeout",
                    allowed=False,
                    message="provider timeout during command center execution",
                    status=504,
                )
            if action.simulate_fault == "bad_credentials":
                return self._record_and_return_decision(
                    action=action,
                    code="bad-credentials",
                    allowed=False,
                    message="credential validation failed",
                    status=401,
                )

        if action.action_class == "connectors" and action.connector:
            if action.connector in self.connector_deny:
                return self._record_and_return_decision(
                    action=action,
                    code="connector-denied",
                    allowed=False,
                    message=f"connector '{action.connector}' denied by registry",
                    status=403,
                )
            if action.connector not in self.connector_allow:
                return self._record_and_return_decision(
                    action=action,
                    code="connector-not-allowed",
                    allowed=False,
                    message=f"connector '{action.connector}' is not allowed by registry",
                    status=403,
                )

        if action.action_class in CONFIRM_REQUIRED_ACTIONS and self.safe_mode:
            if not action.operator_confirmation and not action.break_glass:
                return self._record_and_return_decision(
                    action=action,
                    code="requires-confirmation",
                    allowed=False,
                    requires_confirmation=True,
                    message="operator confirmation required for high-risk action",
                    status=409,
                )

            if action.break_glass:
                if action.policy_token != self.policy_token:
                    return self._record_and_return_decision(
                        action=action,
                        code="break-glass-unauthorized",
                        allowed=False,
                        message="break-glass token is invalid",
                        status=403,
                    )
                return self._record_and_return_decision(
                    action=action,
                    code="allowed",
                    allowed=True,
                    message="executed under break-glass override",
                )

            if action.policy_token != self.policy_token:
                return self._record_and_return_decision(
                    action=action,
                    code="confirmation-token-required",
                    allowed=False,
                    requires_confirmation=True,
                    message="policy token required for confirmation flow",
                    status=409,
                )

        return self._record_and_return_decision(
            action=action,
            code="allowed",
            allowed=True,
            message="action allowed by safety policy",
        )

    def _append_and_return(self, *, action: CommandCenterAction, decision: PolicyDecision) -> PolicyDecision:
        self._append_audit(action=action, tenant_id=action.tenant_id, user_id=action.user_id, decision=decision)
        return decision

    def set_policy_health(self, status: str) -> None:
        if status not in {"healthy", "degraded", "down"}:
            raise ValueError("unknown policy health status")
        self.policy_health = status

    def set_feature_flag(self, feature: str, enabled: bool) -> None:
        if feature not in self.feature_flags:
            raise ValueError(f"unknown feature '{feature}'")
        self.feature_flags[feature] = enabled

    def set_emergency_stop(self, enabled: bool) -> None:
        self.global_kill_switch = enabled

    def set_rollback_mode(self, enabled: bool) -> bool:
        self.rollback_mode = enabled
        self.static_shell_fallback = enabled
        if enabled:
            self.feature_flags = {key: False for key in self.feature_flags}
        else:
            self.feature_flags.update(SAFE_DEFAULT_FEATURE_FLAGS)
        return True

    def configure_connector_policy(self, connector: str, *, allowed: bool) -> None:
        if allowed:
            self.connector_deny.discard(connector)
            self.connector_allow.add(connector)
        else:
            self.connector_allow.discard(connector)
            self.connector_deny.add(connector)

    def get_audit_events(self, *, tenant_id: str | None = None, user_id: str | None = None, limit: int = 100) -> list[CommandCenterAuditEvent]:
        if limit < 1:
            return []
        events = self._audit
        if tenant_id:
            events = [event for event in events if event.tenant_id == tenant_id]
        if user_id:
            events = [event for event in events if event.user_id == user_id]
        events = sorted(events, key=lambda e: e.sequence)
        return events[-limit:]

    def dump_state(self) -> dict[str, Any]:
        return {
            "safe_mode": self.safe_mode,
            "global_kill_switch": self.global_kill_switch,
            "rollback_mode": self.rollback_mode,
            "static_shell_fallback": self.static_shell_fallback,
            "policy_health": self.policy_health,
            "feature_flags": self.feature_flags.copy(),
            "connector_allow": sorted(self.connector_allow),
            "connector_deny": sorted(self.connector_deny),
            "limits": {
                "tenant_rate_limit_per_minute": self.rate_limit_per_tenant_per_min,
                "tenant_anomaly_cap_per_minute": self.anomaly_cap_per_tenant_per_min,
                "queue_backlog_limit": self.queue_backlog_limit,
            },
            "recent_audit_sequence": self._sequence,
            "audit_retention": self.audit_retention,
            "head_chain_hash": self._last_hash,
            "audit_alerts": len(self.audit_alerts),
            "audit_file_enabled": self._audit_file is not None,
        }

    def set_limits(
        self,
        *,
        tenant_rate_limit_per_minute: int | None = None,
        tenant_anomaly_cap_per_minute: int | None = None,
        queue_backlog_limit: int | None = None,
    ) -> None:
        if tenant_rate_limit_per_minute is not None:
            self.rate_limit_per_tenant_per_min = max(1, tenant_rate_limit_per_minute)
        if tenant_anomaly_cap_per_minute is not None:
            self.anomaly_cap_per_tenant_per_min = max(1, tenant_anomaly_cap_per_minute)
        if queue_backlog_limit is not None:
            self.queue_backlog_limit = max(1, queue_backlog_limit)


command_center_safety_engine = CommandCenterSafetyEngine(
    audit_file=os.getenv("COMMAND_CENTER_AUDIT_FILE"),
    audit_signing_key=os.getenv("COMMAND_CENTER_AUDIT_SIGNING_KEY"),
)
