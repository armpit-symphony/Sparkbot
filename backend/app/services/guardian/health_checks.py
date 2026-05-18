from __future__ import annotations

import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HEALTH_CHECK_TOOL_NAME = "sparkbot_health_check"
DEFAULT_HEALTH_SCHEDULE = "daily-local:06:00"

DEFAULT_THRESHOLDS: dict[str, float] = {
    "disk_warning_percent": 80.0,
    "disk_critical_percent": 90.0,
    "memory_warning_percent": 85.0,
    "memory_critical_percent": 95.0,
    "cpu_warning_percent": 85.0,
    "cpu_critical_percent": 95.0,
    "load_warning_per_cpu": 1.5,
    "load_critical_per_cpu": 2.5,
}


def health_task_templates() -> list[dict[str, Any]]:
    """Return public-safe Task Guardian health templates.

    These are templates, not auto-created jobs. They default to disabled and
    app-only delivery so the user explicitly opts into recurring reports and
    external connector sends.
    """
    common = {
        "tool_name": HEALTH_CHECK_TOOL_NAME,
        "schedule": DEFAULT_HEALTH_SCHEDULE,
        "enabled": False,
        "read_only": True,
        "delivery_channels": ["app"],
        "default_schedule_label": "Daily at 6:00 AM local time",
        "editable": True,
    }
    return [
        {
            **common,
            "id": "pc_health_check",
            "name": "PC Health Check",
            "description": "Daily local workstation health report for Sparkbot Public.",
            "source_label": "task_guardian.health.pc",
            "tool_args": {
                "mode": "pc",
                "delivery_channels": ["app"],
                "thresholds": DEFAULT_THRESHOLDS,
            },
        },
        {
            **common,
            "id": "server_health_check",
            "name": "Server Health Check",
            "description": "Daily server health report for Sparkbot Public.",
            "source_label": "task_guardian.health.server",
            "tool_args": {
                "mode": "server",
                "delivery_channels": ["app"],
                "thresholds": DEFAULT_THRESHOLDS,
            },
        },
    ]


def health_source_label(mode: str | None) -> str:
    normalized = _normalize_mode(mode)
    return f"task_guardian.health.{normalized}"


def delivery_channels_from_args(args: dict[str, Any] | None) -> list[str]:
    args = args if isinstance(args, dict) else {}
    raw = args.get("delivery_channels")
    if raw is None and isinstance(args.get("delivery"), dict):
        raw = args["delivery"].get("channels")
    if raw is None:
        return ["app"]
    if isinstance(raw, str):
        channels = [item.strip().lower() for item in raw.replace(",", " ").split()]
    elif isinstance(raw, list):
        channels = [str(item).strip().lower() for item in raw]
    else:
        channels = []
    allowed = {"app", "telegram", "discord", "slack", "whatsapp"}
    cleaned: list[str] = []
    for channel in channels:
        if channel in allowed and channel not in cleaned:
            cleaned.append(channel)
    return cleaned or ["app"]


async def run_health_check(
    args: dict[str, Any] | None,
    *,
    session: Any = None,
    room_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    args = args if isinstance(args, dict) else {}
    mode = _normalize_mode(args.get("mode"))
    thresholds = _thresholds(args.get("thresholds"))
    collected = await collect_health(mode=mode, thresholds=thresholds, session=session)
    collected["source_label"] = health_source_label(mode)
    collected["delivery_channels"] = delivery_channels_from_args(args)
    collected["room_id"] = room_id
    collected["user_id"] = user_id
    report = render_health_report(collected)
    return {"report": report, **collected}


async def collect_health(
    *,
    mode: str,
    thresholds: dict[str, float] | None = None,
    session: Any = None,
) -> dict[str, Any]:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    now = datetime.now(timezone.utc)
    system: dict[str, Any] = {
        "mode": mode,
        "timestamp": now.isoformat(),
        "platform": platform.platform(aliased=True, terse=True),
        "python": platform.python_version(),
    }
    findings: list[dict[str, str]] = []
    passed: list[str] = []
    recommended: list[str] = []

    psutil_mod = _psutil()
    if psutil_mod is None:
        findings.append(
            {
                "severity": "SEV-3",
                "check": "Metrics",
                "detail": "psutil is unavailable, so CPU, memory, disk, battery, and uptime checks are limited.",
                "recommendation": "Install Sparkbot with its standard backend dependencies to enable full health checks.",
            }
        )
    else:
        _collect_psutil_metrics(
            psutil_mod,
            mode=mode,
            thresholds=thresholds,
            system=system,
            findings=findings,
            passed=passed,
            recommended=recommended,
        )

    _collect_load_metrics(
        thresholds=thresholds,
        system=system,
        findings=findings,
        passed=passed,
        recommended=recommended,
    )
    _collect_sparkbot_status(system=system, findings=findings, passed=passed)
    await _collect_local_ai_status(system=system, findings=findings, passed=passed, recommended=recommended)
    _collect_connector_status(system=system, findings=findings, passed=passed)
    _collect_update_status(system=system, passed=passed)

    status = _overall_status(findings)
    if not recommended and status == "Nominal":
        recommended.append("No action required.")
    elif not recommended:
        recommended.append("Review the findings above and adjust the affected service or connector.")

    return {
        "timestamp": now.isoformat(),
        "mode": mode,
        "status": status,
        "sev1_detected": any(item.get("severity") == "SEV-1" for item in findings),
        "system": system,
        "findings": findings,
        "passed_checks": passed,
        "recommended_actions": recommended,
        "read_only": True,
    }


def render_health_report(payload: dict[str, Any]) -> str:
    timestamp = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())
    mode = str(payload.get("mode") or "pc").upper()
    status = str(payload.get("status") or "Unknown")
    system = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    passed = payload.get("passed_checks") if isinstance(payload.get("passed_checks"), list) else []
    recommended = payload.get("recommended_actions") if isinstance(payload.get("recommended_actions"), list) else []

    sev1 = [item for item in findings if item.get("severity") == "SEV-1"]
    sev2 = [item for item in findings if item.get("severity") == "SEV-2"]
    sev3 = [item for item in findings if item.get("severity") == "SEV-3"]

    lines = [
        f"Sparkbot Health Report - {timestamp}",
        "",
        "SEV-1 Assessment:",
        "DETECTED" if sev1 else "NONE",
        "",
        "System Status:",
        f"{status} ({mode})",
        "",
        "System Snapshot:",
        f"- Platform: {system.get('platform', 'unknown')}",
        f"- Uptime: {system.get('uptime', 'unavailable')}",
        f"- CPU: {system.get('cpu', 'unavailable')}",
        f"- Load: {system.get('load', 'unavailable')}",
        f"- Memory: {system.get('memory', 'unavailable')}",
        f"- Swap: {system.get('swap', 'unavailable')}",
        f"- Disk: {system.get('disk', 'unavailable')}",
        f"- Battery: {system.get('battery', 'not applicable')}",
        "",
        "Sparkbot / Connector Status:",
        f"- Sparkbot backend: {system.get('sparkbot_backend', 'running')}",
        f"- Local AI: {system.get('local_ai', 'setup optional')}",
        f"- Connectors: {system.get('connectors', 'setup optional')}",
        f"- Updates: {system.get('updates', 'manual check only')}",
        "",
    ]
    lines.extend(_render_findings_section("SEV-1 Findings", sev1))
    lines.extend(_render_findings_section("SEV-2 Findings", sev2))
    lines.extend(_render_findings_section("SEV-3 Findings", sev3))
    lines.append("Passed Checks:")
    if passed:
        lines.extend(f"- {str(item)[:220]}" for item in passed[:12])
    else:
        lines.append("- No passed checks recorded.")
    lines.extend(["", "Recommended Actions:"])
    if recommended:
        lines.extend(f"- {str(item)[:220]}" for item in recommended[:8])
    else:
        lines.append("- No action required.")
    lines.extend(["", "Read-only safety boundary: no packages were updated, no services were restarted, and no destructive commands were run."])
    return "\n".join(lines)


def _render_findings_section(title: str, findings: list[dict[str, str]]) -> list[str]:
    lines = [f"{title}:"]
    if not findings:
        lines.append("- None")
    else:
        for item in findings[:10]:
            detail = str(item.get("detail") or "").strip()
            recommendation = str(item.get("recommendation") or "").strip()
            suffix = f" Recommendation: {recommendation}" if recommendation else ""
            lines.append(f"- {item.get('check', 'Check')}: {detail}{suffix}"[:500])
    lines.append("")
    return lines


def _normalize_mode(value: Any) -> str:
    raw = str(value or "pc").strip().lower()
    return "server" if raw == "server" else "pc"


def _thresholds(raw: Any) -> dict[str, float]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in thresholds:
                try:
                    thresholds[key] = float(value)
                except (TypeError, ValueError):
                    pass
    return thresholds


def _psutil():
    try:
        import psutil  # type: ignore

        return psutil
    except Exception:
        return None


def _collect_psutil_metrics(
    psutil_mod: Any,
    *,
    mode: str,
    thresholds: dict[str, float],
    system: dict[str, Any],
    findings: list[dict[str, str]],
    passed: list[str],
    recommended: list[str],
) -> None:
    boot_time = datetime.fromtimestamp(float(psutil_mod.boot_time()), tz=timezone.utc)
    uptime_seconds = max(0, int(time.time() - float(psutil_mod.boot_time())))
    system["uptime"] = _format_duration(uptime_seconds)
    passed.append(f"Uptime read successfully since {boot_time.isoformat()}.")

    cpu_percent = float(psutil_mod.cpu_percent(interval=0.1))
    system["cpu"] = f"{cpu_percent:.1f}% used"
    if cpu_percent >= thresholds["cpu_critical_percent"]:
        findings.append(
            {
                "severity": "SEV-2",
                "check": "CPU",
                "detail": f"CPU usage is {cpu_percent:.1f}% at the time of the check.",
                "recommendation": "Check active local models, browser sessions, builds, or long-running jobs.",
            }
        )
        recommended.append("Inspect active processes before launching additional heavy model or build work.")
    elif cpu_percent >= thresholds["cpu_warning_percent"]:
        findings.append(
            {
                "severity": "SEV-3",
                "check": "CPU",
                "detail": f"CPU usage is elevated at {cpu_percent:.1f}%.",
                "recommendation": "Watch for repeated high CPU in future reports.",
            }
        )
    else:
        passed.append(f"CPU usage nominal at {cpu_percent:.1f}%.")

    mem = psutil_mod.virtual_memory()
    mem_percent = float(getattr(mem, "percent", 0.0))
    system["memory"] = f"{mem_percent:.1f}% used ({_bytes_gb(mem.available)} GB available)"
    if mem_percent >= thresholds["memory_critical_percent"]:
        findings.append(
            {
                "severity": "SEV-1",
                "check": "Memory",
                "detail": f"Memory usage is critical at {mem_percent:.1f}%.",
                "recommendation": "Close heavy jobs or reduce local model load before starting more work.",
            }
        )
        recommended.append("Reduce memory pressure before running more agents or local models.")
    elif mem_percent >= thresholds["memory_warning_percent"]:
        findings.append(
            {
                "severity": "SEV-2",
                "check": "Memory",
                "detail": f"Memory usage is high at {mem_percent:.1f}%.",
                "recommendation": "Review local model and browser memory use.",
            }
        )
    else:
        passed.append(f"Memory usage nominal at {mem_percent:.1f}%.")

    swap = psutil_mod.swap_memory()
    system["swap"] = f"{float(getattr(swap, 'percent', 0.0)):.1f}% used"

    disk_path = _disk_probe_path(mode)
    usage = psutil_mod.disk_usage(str(disk_path))
    disk_percent = float(getattr(usage, "percent", 0.0))
    system["disk"] = f"{disk_percent:.1f}% used ({_bytes_gb(usage.free)} GB free)"
    if disk_percent >= thresholds["disk_critical_percent"]:
        findings.append(
            {
                "severity": "SEV-1",
                "check": "Disk",
                "detail": f"Primary volume is {disk_percent:.1f}% full.",
                "recommendation": "Free disk space before saving more model artifacts, logs, or uploads.",
            }
        )
        recommended.append("Free disk space or move large artifacts before continuing long-running work.")
    elif disk_percent >= thresholds["disk_warning_percent"]:
        findings.append(
            {
                "severity": "SEV-2",
                "check": "Disk",
                "detail": f"Primary volume is {disk_percent:.1f}% full.",
                "recommendation": "Plan cleanup before the volume crosses 90%.",
            }
        )
    else:
        passed.append(f"Primary disk usage nominal at {disk_percent:.1f}%.")

    battery_status = "not applicable"
    if mode == "pc" and hasattr(psutil_mod, "sensors_battery"):
        try:
            battery = psutil_mod.sensors_battery()
            if battery is not None:
                plugged = "plugged in" if battery.power_plugged else "on battery"
                battery_status = f"{float(battery.percent):.0f}% ({plugged})"
                if not battery.power_plugged and float(battery.percent) <= 20:
                    findings.append(
                        {
                            "severity": "SEV-2",
                            "check": "Battery",
                            "detail": f"Battery is low at {float(battery.percent):.0f}%.",
                            "recommendation": "Plug in before starting long local model or agent work.",
                        }
                    )
                else:
                    passed.append(f"Battery status read: {battery_status}.")
        except Exception:
            battery_status = "unavailable"
    system["battery"] = battery_status


def _collect_load_metrics(
    *,
    thresholds: dict[str, float],
    system: dict[str, Any],
    findings: list[dict[str, str]],
    passed: list[str],
    recommended: list[str],
) -> None:
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        system["load"] = "unavailable on this platform"
        return
    cores = max(1, os.cpu_count() or 1)
    per_core = float(load5) / cores
    system["load"] = f"{load1:.2f}, {load5:.2f}, {load15:.2f} ({per_core:.2f} per core at 5m)"
    if per_core >= thresholds["load_critical_per_cpu"]:
        findings.append(
            {
                "severity": "SEV-1",
                "check": "Load",
                "detail": f"Five-minute load is {per_core:.2f} per CPU core.",
                "recommendation": "Inspect queued jobs, local model servers, and service saturation.",
            }
        )
        recommended.append("Reduce queued work or scale the host before adding more scheduled jobs.")
    elif per_core >= thresholds["load_warning_per_cpu"]:
        findings.append(
            {
                "severity": "SEV-2",
                "check": "Load",
                "detail": f"Five-minute load is elevated at {per_core:.2f} per CPU core.",
                "recommendation": "Check for sustained background work.",
            }
        )
    else:
        passed.append("Load average is within the configured threshold.")


def _collect_sparkbot_status(
    *,
    system: dict[str, Any],
    findings: list[dict[str, str]],
    passed: list[str],
) -> None:
    system["sparkbot_backend"] = "running (current backend process)"
    passed.append("Sparkbot backend process is running.")
    if os.getenv("SPARKBOT_TASK_GUARDIAN_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        findings.append(
            {
                "severity": "SEV-2",
                "check": "Task Guardian",
                "detail": "Task Guardian is disabled by environment setting.",
                "recommendation": "Enable Task Guardian before relying on scheduled health reports.",
            }
        )
    else:
        passed.append("Task Guardian is enabled by environment setting.")


async def _collect_local_ai_status(
    *,
    system: dict[str, Any],
    findings: list[dict[str, str]],
    passed: list[str],
    recommended: list[str],
) -> None:
    summaries: list[str] = []
    try:
        from app.api.routes.chat.llm import get_ollama_status
        from app.services.local_ai import get_local_ai_status, local_ai_config

        ollama = await get_ollama_status()
        if ollama.get("reachable"):
            summaries.append(f"Ollama reachable ({len(ollama.get('model_ids') or [])} models)")
            passed.append("Ollama local provider is reachable.")
        else:
            summaries.append("Ollama setup optional")

        local_config = local_ai_config()
        local_enabled = bool(local_config.get("enabled"))
        local_status = await get_local_ai_status()
        if local_status.get("reachable"):
            summaries.append(f"{local_status.get('runtime_label', 'Local AI')} reachable ({len(local_status.get('model_ids') or [])} models)")
            passed.append("OpenAI-compatible local provider is reachable.")
        elif local_enabled:
            summaries.append(f"{local_config.get('runtime_label', 'Local AI')} setup needed")
            findings.append(
                {
                    "severity": "SEV-2",
                    "check": "Local AI",
                    "detail": f"{local_config.get('runtime_label', 'Local AI')} is enabled but unreachable.",
                    "recommendation": "Start the local model server or update the base URL in Command Center.",
                }
            )
            recommended.append("Fix or disable the configured local AI endpoint before using local model seats.")
        else:
            summaries.append("OpenAI-compatible local endpoint setup optional")
    except Exception:
        summaries.append("local AI status unavailable")
    system["local_ai"] = "; ".join(summaries)


def _collect_connector_status(
    *,
    system: dict[str, Any],
    findings: list[dict[str, str]],
    passed: list[str],
) -> None:
    try:
        from app.services.guardian.governance import connector_health

        connectors = connector_health()
    except Exception:
        system["connectors"] = "status unavailable"
        return
    configured = [str(item.get("label")) for item in connectors if item.get("configured")]
    optional = [str(item.get("label")) for item in connectors if not item.get("configured")]
    if configured:
        passed.append(f"Configured connectors detected: {', '.join(configured[:6])}.")
    if optional:
        findings.append(
            {
                "severity": "SEV-3",
                "check": "Connectors",
                "detail": f"Optional connectors awaiting setup: {', '.join(optional[:6])}.",
                "recommendation": "Configure Telegram, Discord, or Slack before enabling external health-report delivery.",
            }
        )
    system["connectors"] = (
        f"{len(configured)} configured, {len(optional)} optional setup"
        if connectors
        else "no connector catalog available"
    )


def _collect_update_status(*, system: dict[str, Any], passed: list[str]) -> None:
    system["updates"] = "manual check only; no package manager commands run"
    passed.append("Update availability check skipped safely; no package manager command was run.")


def _disk_probe_path(mode: str) -> Path:
    configured = os.getenv("SPARKBOT_HEALTH_DISK_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    if mode == "server" and os.name != "nt":
        return Path("/")
    data_dir = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir).expanduser()
    return Path.cwd()


def _overall_status(findings: list[dict[str, str]]) -> str:
    severities = {str(item.get("severity") or "") for item in findings}
    if "SEV-1" in severities:
        return "Critical"
    if "SEV-2" in severities:
        return "Warning"
    return "Nominal"


def _format_duration(seconds: int) -> str:
    days, rem = divmod(max(0, seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _bytes_gb(value: Any) -> str:
    try:
        return f"{float(value) / 1_000_000_000:.1f}"
    except (TypeError, ValueError):
        return "0.0"
