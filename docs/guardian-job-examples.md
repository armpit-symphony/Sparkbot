# Sparkbot — Task Guardian Job Examples

Copy-paste examples for scheduling autonomous jobs. All examples use natural language in chat — Sparkbot creates the Guardian job from the description.

---

## Table of Contents

1. [How to create a scheduled job](#how-to-create-a-scheduled-job)
2. [Diagnostics & health jobs](#diagnostics--health-jobs)
3. [Productivity jobs](#productivity-jobs)
4. [Write-action jobs (opt-in)](#write-action-jobs-opt-in)
5. [Custom intervals reference](#custom-intervals-reference)
6. [Managing jobs from chat](#managing-jobs-from-chat)
7. [Guardian job JSON schema](#guardian-job-json-schema)

---

## How to create a scheduled job

Tell Sparkbot in plain language:

```
"Every morning at 8am, run my morning briefing"
"Check system health every 15 minutes and post to this room"
"Send me a calendar preview every day at 7:30am"
```

Or use the Task Guardian panel in **Sparkbot Controls** to create jobs with a form.

---

## Diagnostics & health jobs

### System health check every 15 minutes

**Chat prompt:**
```
Schedule system_diagnostics to run every 15 minutes
```

**What it posts:**
```
## System Diagnostics — 2026-04-18 14:30:00 UTC

### CPU
- Overall: 23.4%
- Per core: C0:18%  C1:28%  C2:22%  C3:25%

### Memory
- RAM: 61.2% used (9.8 GB / 16.0 GB)
- Swap: 0.0% used

### Disk
  - C:\: 54.3% used (271.5 GB / 500.0 GB free: 228.5 GB)

### Top 10 Processes (by CPU)
  - ollama.exe (PID 4821): CPU 34.2%  MEM 8.1%
  - chrome.exe (PID 9102): CPU 12.1%  MEM 3.4%
  ...

### Model Endpoint Reachability
  - ✅ OpenAI (api.openai.com:443): reachable
  - ✅ Anthropic (api.anthropic.com:443): reachable
  - ❌ Ollama (localhost:11434): unreachable

### Status
⚠️ CPU is at 34% — consider pausing Ollama
```

**JSON schema (for API use):**
```json
{
  "name": "System Health Check",
  "tool_name": "system_diagnostics",
  "schedule": "every:900",
  "tool_args": {
    "include_log_tail": true,
    "top_processes": 10
  }
}
```

---

### Daily log review at 9pm

**Chat prompt:**
```
Every day at 9pm, run system diagnostics with the last 20 log lines and post results here
```

**JSON schema:**
```json
{
  "name": "Daily Log Review",
  "tool_name": "system_diagnostics",
  "schedule": "daily:21:00",
  "tool_args": {
    "include_log_tail": true,
    "top_processes": 5
  }
}
```

---

### Hourly model endpoint probe

**Chat prompt:**
```
Every hour, check if my AI providers are reachable and post the results
```

**JSON schema:**
```json
{
  "name": "Hourly Provider Check",
  "tool_name": "system_diagnostics",
  "schedule": "every:3600",
  "tool_args": {
    "include_log_tail": false,
    "top_processes": 0
  }
}
```

---

## Productivity jobs

### Morning briefing — daily at 8am

**Chat prompt:**
```
Every morning at 8am, run my morning briefing
```

**What it posts:** Gmail unread summary + today's and tomorrow's calendar events + pending reminders for this room.

**JSON schema:**
```json
{
  "name": "Morning Brief",
  "tool_name": "morning_briefing",
  "schedule": "daily:08:00",
  "tool_args": {
    "timezone": "America/New_York",
    "location": "New York"
  }
}
```

---

### Hourly inbox check

**Chat prompt:**
```
Check my Gmail inbox every hour and summarize any new messages
```

**JSON schema:**
```json
{
  "name": "Hourly Inbox Check",
  "tool_name": "gmail_fetch_inbox",
  "schedule": "every:3600",
  "tool_args": {
    "max_results": 5
  }
}
```

---

### Daily calendar preview at 7:30am

**Chat prompt:**
```
Every morning at 7:30am, show me today's calendar events
```

**JSON schema:**
```json
{
  "name": "Daily Calendar Preview",
  "tool_name": "calendar_list_events",
  "schedule": "daily:07:30",
  "tool_args": {
    "days_ahead": 1
  }
}
```

---

### Daily open task digest at 5pm

**Chat prompt:**
```
Every day at 5pm, list my open tasks in this room
```

**JSON schema:**
```json
{
  "name": "Daily Task Digest",
  "tool_name": "list_tasks",
  "schedule": "daily:17:00",
  "tool_args": {
    "status": "open"
  }
}
```

---

### Daily news headlines at 6am

**Chat prompt:**
```
Every morning at 6am, fetch today's top news headlines
```

**JSON schema:**
```json
{
  "name": "Morning Headlines",
  "tool_name": "news_headlines",
  "schedule": "daily:06:00",
  "tool_args": {
    "source": "hn",
    "count": 5
  }
}
```

---

### Crypto price check every 30 minutes

**Chat prompt:**
```
Check Bitcoin and Ethereum prices every 30 minutes
```

**JSON schema:**
```json
{
  "name": "Crypto Price Watch",
  "tool_name": "crypto_price",
  "schedule": "every:1800",
  "tool_args": {
    "coins": ["bitcoin", "ethereum"]
  }
}
```

---

### GitHub CI status check every hour

**Chat prompt:**
```
Check the CI status on my main branch every hour
```

**JSON schema:**
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

---

## Write-action jobs (opt-in)

Write-action jobs send email, post to Slack, or create calendar events on a schedule. These require explicit pre-authorization during job setup and:

```env
SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true
```

### Daily Slack standup post at 9am

**Chat prompt:**
```
Every weekday at 9am, post a standup summary to the #team channel in Slack
```

**JSON schema:**
```json
{
  "name": "Daily Standup Post",
  "tool_name": "slack_send_message",
  "schedule": "daily:09:00",
  "tool_args": {
    "channel": "#team",
    "message": "Good morning! Daily standup starting now. What are you working on today?"
  },
  "write_confirmed": true
}
```

> Note: `write_confirmed: true` is set automatically when you approve the confirmation modal during job creation. Do not set it manually in JSON — Sparkbot will prompt for approval.

---

## Custom intervals reference

| Schedule string | Meaning |
|----------------|---------|
| `"every:300"` | Every 5 minutes |
| `"every:900"` | Every 15 minutes |
| `"every:1800"` | Every 30 minutes |
| `"every:3600"` | Every hour |
| `"every:86400"` | Every 24 hours |
| `"daily:08:00"` | Every day at 8:00am UTC |
| `"daily:13:00"` | Every day at 9:00am America/New_York during daylight time |
| `"at:2026-04-24T14:00:00Z"` | One-shot run at an exact UTC time |

> Timezone note: schedule times are in UTC. For 9am America/New_York, use `daily:13:00` during daylight time and `daily:14:00` during standard time.

---

## Managing jobs from chat

```
"Show my scheduled jobs"         → lists all Guardian jobs in this room
"Pause the system health job"    → suspends without deleting
"Delete the hourly inbox check"  → removes the job permanently
"Run my morning briefing now"    → triggers immediately without waiting for schedule
```

Or manage via **Workstation → Company Operations → Guardian Tasks**.

---

## Guardian job JSON schema

Full schema for the `guardian_schedule_task` tool call:

```json
{
  "name": "string — display name for the job",
  "tool_name": "string — name of the tool to run (must be in AVAILABLE_TOOLS)",
  "schedule": "string — schedule expression (see Custom intervals reference)",
  "tool_args": {
    "...": "any args accepted by the tool"
  },
  "write_confirmed": false,
  "max_retries": 3,
  "notify_on_failure": true
}
```

| Field | Default | Notes |
|-------|---------|-------|
| `name` | required | Shown in Workstation and chat |
| `tool_name` | required | Must be a loaded tool or skill name |
| `schedule` | required | `every:N` (seconds) or `daily:HH:MM` |
| `tool_args` | `{}` | Passed directly to the tool |
| `write_confirmed` | `false` | Set by approval flow — do not set manually |
| `max_retries` | `3` | Bounded retries per run (Verifier Guardian) |
| `notify_on_failure` | `true` | Posts to room on repeated failures |

---

## Debugging a Guardian job

**Check last run status:**
```
"What happened with my morning briefing last run?"
"Show the Guardian task log for system health check"
```

**Check backend logs:**
```powershell
# Windows — tail the backend log
Get-Content "$env:LOCALAPPDATA\Sparkbot Local\sparkbot-backend.log" -Tail 50 | Select-String "task_guardian|guardian_schedule"
```
```bash
# Linux / macOS (systemd)
journalctl -u sparkbot-v2 -n 100 | grep task_guardian
```

**Force a run now** from the Workstation Tasks tab — click the **Run** button next to any job.
