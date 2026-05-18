# Task Guardian Health Checks Status

Date: 2026-05-17
Branch: `public-release-task-guardian-health-checks`

## Summary

Sparkbot Public now has two built-in Task Guardian health-check templates:

- PC Health Check
- Server Health Check

Both templates use the new `sparkbot_health_check` read-only tool. They default
to `daily-local:06:00`, are disabled until the user adds/enables them, and use
app-only delivery by default.

## Implementation Status

| Area | Status |
|---|---|
| Template definitions | Implemented in `backend/app/services/guardian/health_checks.py`. |
| Task Guardian allowlist | `sparkbot_health_check` is allowlisted for scheduled jobs. |
| Scheduler | Added `daily-local:<HH:MM>` alongside existing `every:`, `daily:`, and `at:` schedules. |
| Collector | Implemented as read-only, cross-platform, graceful degradation if `psutil` or platform metrics are unavailable. |
| Report renderer | Implemented plain-text Sparkbot Health Report with SEV-1, SEV-2, SEV-3, passed checks, and recommended actions. |
| UI | Command Center Task Guardian shows built-in health templates, can add/edit the template payload, and shows recent run output excerpts so the latest health report is visible. Legacy Task Guardian option lists now include the safe health tool instead of stale non-allowlisted tools. |
| Memory/context | Health runs write source-labeled summaries as `task_guardian.health.pc` or `task_guardian.health.server`. |
| Delivery | In-app task history/chat message always happens. Telegram, Discord, WhatsApp, and Slack are opt-in via `delivery_channels`; delivery failures are returned without failing the whole task. |

## Read-Only Safety Boundary

The health collector does not:

- update packages
- restart services
- mutate files
- run destructive commands
- expose connector secrets
- store credentials in browser storage
- dump raw logs, private paths, cron entries, process command lines, or host listener lists

The older `system_diagnostics` skill remains available as a broader diagnostic
tool, but public health templates do not preload or schedule it.

## Metrics

PC Health Check targets:

- uptime
- CPU/load where available
- memory and swap
- primary disk usage
- battery status when available
- Sparkbot backend status
- local AI status
- connector setup status
- safe update guidance

Server Health Check targets:

- uptime
- load average where available
- memory and swap
- root/app-data disk usage
- Sparkbot backend status
- local AI status
- connector setup status
- safe update guidance

## Severity Model

| Severity | Meaning |
|---|---|
| SEV-1 | Critical condition requiring immediate attention, such as disk over 90% or memory over 95%. |
| SEV-2 | Warning/non-critical issue, such as disk over 80%, high memory, unreachable enabled local AI, or Task Guardian disabled. |
| SEV-3 | Informational setup or minor condition, such as optional connectors not configured. |

## Connector Delivery

- App/in-room delivery is default and always attempted.
- Telegram, Discord, WhatsApp, and Slack require explicit `delivery_channels`.
- Slack requires a configured `SLACK_BOT_TOKEN` and `slack_channel` or `SPARKBOT_HEALTH_SLACK_CHANNEL`.
- External delivery failures do not fail the health task; they are returned as delivery errors.

## Remaining Blockers

- Browser QA for the Command Center Task Guardian template cards and recent-report display.
- Add a simple delivery-channel picker instead of requiring JSON editing for Telegram/Discord/Slack.
- Decide whether health tasks should be offered during first-run setup for desktop/server installs.
- Multi-worker server deployments still need leader locking before increasing API workers beyond the documented public default.
