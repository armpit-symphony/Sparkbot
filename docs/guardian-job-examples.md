# Sparkbot Task Guardian Job Examples

Copy-paste examples for scheduled Guardian jobs. Public-safe health jobs use
`sparkbot_health_check`, not the broader `system_diagnostics` skill. Health
reports are read-only: Sparkbot does not update packages, restart services, run
destructive commands, or expose raw secrets.

## Creating A Job

Tell Sparkbot in plain language:

```text
Every morning at 8am, run my morning briefing.
Add the PC Health Check template and run it every morning at 6am local time.
Check CI status on my main branch every hour.
```

Or use Command Center -> Task Guardian. The PC and Server Health Check templates
are built in, disabled by default, and app-only by default.

## Health Jobs

### PC Health Check

```json
{
  "name": "PC Health Check",
  "tool_name": "sparkbot_health_check",
  "schedule": "daily-local:06:00",
  "tool_args": {
    "mode": "pc",
    "delivery_channels": ["app"]
  }
}
```

Checks include uptime, CPU/load where available, memory, swap, primary disk,
battery when available, Sparkbot backend status, local AI status, connector
status, safe update guidance, passed checks, findings, and recommended actions.

### Server Health Check

```json
{
  "name": "Server Health Check",
  "tool_name": "sparkbot_health_check",
  "schedule": "daily-local:06:00",
  "tool_args": {
    "mode": "server",
    "delivery_channels": ["app"]
  }
}
```

Server mode uses the same read-only collector and focuses on host uptime,
load/memory/swap/disk, Sparkbot backend status, configured connector status, and
local AI setup state. It does not run package-manager commands, dump cron, tail
logs, inspect private paths, or restart services.

### Optional Connector Delivery

External delivery is opt-in. The job still saves an in-app Task Guardian run
record if Telegram, Discord, or Slack delivery fails.

```json
{
  "name": "PC Health Check",
  "tool_name": "sparkbot_health_check",
  "schedule": "daily-local:06:00",
  "tool_args": {
    "mode": "pc",
    "delivery_channels": ["app", "telegram"]
  }
}
```

For Slack delivery, add a configured channel after Slack is connected:

```json
{
  "name": "Server Health Check",
  "tool_name": "sparkbot_health_check",
  "schedule": "daily-local:06:00",
  "tool_args": {
    "mode": "server",
    "delivery_channels": ["app", "slack"],
    "slack_channel": "#ops"
  }
}
```

## Productivity Jobs

### Morning Brief

```json
{
  "name": "Morning Brief",
  "tool_name": "morning_briefing",
  "schedule": "daily-local:08:00",
  "tool_args": {
    "timezone": "America/New_York",
    "location": "New York"
  }
}
```

### Hourly Inbox Check

```json
{
  "name": "Hourly Inbox Check",
  "tool_name": "gmail_fetch_inbox",
  "schedule": "every:3600",
  "tool_args": {
    "max_emails": 5,
    "unread_only": true
  }
}
```

### CI Status Check

```json
{
  "name": "CI Status Check",
  "tool_name": "github_get_ci_status",
  "schedule": "every:3600",
  "tool_args": {
    "repo": "owner/repo",
    "branch": "main"
  }
}
```

## Write-Action Jobs

Write-action jobs such as `gmail_send`, `slack_send_message`, and
`calendar_create_event` require explicit confirmation during setup and:

```env
SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true
```

## Schedule Reference

| Schedule string | Meaning |
|---|---|
| `every:300` | Every 5 minutes |
| `every:3600` | Every hour |
| `daily:13:00` | Daily at 13:00 UTC |
| `daily-local:06:00` | Daily at 6:00 AM in the host local timezone |
| `at:2026-04-24T14:00:00Z` | One-shot run at an exact UTC time |

Use `daily-local:<HH:MM>` for public health checks so a non-technical user can
say "6:00 AM" without converting to UTC.

## Managing Jobs

```text
Show my scheduled jobs.
Run my PC Health Check now.
Pause the Server Health Check.
Show the last Task Guardian run.
```

Task Guardian run records include verifier status, confidence, evidence summary,
recommended next action, output excerpt, and bounded retries.
