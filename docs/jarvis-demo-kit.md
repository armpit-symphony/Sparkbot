# Sparkbot Jarvis Demo Kit

This is a copy-ready 9am presentation and demo package for showing Sparkbot as a governed "Jarvis for work": proactive assistance, policy-gated action, vault-backed secrets, approvals, and audit-first operations.

## One-Line Headline

Sparkbot is Jarvis for work: a secure orchestration layer that runs autonomous assistants, scheduled automations, and company ops with human-in-the-loop governance, secrets-safe execution, and durable audit context.

## 15-Second Pitch

"Sparkbot safely automates repetitive work and agent decisions by combining an always-on assistant, policy-enforced execution, scheduled and on-demand briefing workflows, and an audit trail, so teams get autonomous-agent productivity without giving up control."

## Slide Outline

1. Title: Sparkbot, Jarvis for governed work.
2. Problem: agent automation is useful but risky without policy, approvals, secrets controls, and logs.
3. Solution: orchestrator rooms, policy engine, scheduler, memory, vault, approvals, and audit.
4. Architecture: user trigger -> orchestrator -> policy simulation/decision -> execution or approval -> audit and memory.
5. Live demo: run a morning briefing, start a Round Table, simulate a risky action, approve a gated action, then show audit evidence.
6. Roadmap: stabilize baseline, core Jarvis features, production readiness, scale and polish.
7. Business case: governance-first automation for engineering, SRE, and security teams.
8. Ask: pick pilot workflows and enable production connectors.

## Demo Script

1. Open Sparkbot and explain the goal: "daily briefing plus safe execution under policy."
2. In Controls -> Task Guardian, create the "9am Morning Brief" job using the JSON below.
3. Click Run now or ask: "Run my morning briefing now."
4. Show the concise result: calendar, unread email, reminders, weather if configured.
5. Open Workstation -> Round Table, Auto-fill Stack, and start a short project meeting to show Sparkbot acting as an orchestrator.
6. Ask Sparkbot to simulate a risky write action before running it, for example: "Use guardian_simulate_policy for gmail_send to alex@example.com with subject Status update."
7. Attempt a risky write action such as creating a calendar event or sending a Slack message.
8. Show the confirmation or breakglass flow and explain that scheduled writes require explicit pre-authorization.
9. Approve the action, then open recent Task Guardian runs and audit entries.
10. Close with the roadmap and pilot ask.

## Pasteable Task Guardian Jobs

### 9am Morning Briefing

Use `daily:13:00` for 9am America/New_York during daylight time. Use `daily:14:00` during standard time.

```json
{
  "name": "9am Morning Brief",
  "tool_name": "morning_briefing",
  "schedule": "daily:13:00",
  "tool_args": {
    "timezone": "America/New_York",
    "days_ahead": 2,
    "max_emails": 5,
    "include_weather": true,
    "location": "New York",
    "include_news": true,
    "news_topic": "technology"
  }
}
```

### Calendar Preview

```json
{
  "name": "Daily Calendar Preview",
  "tool_name": "calendar_list_events",
  "schedule": "daily:12:30",
  "tool_args": {
    "days_ahead": 1
  }
}
```

### Risky Write Demo

Requires `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true`. Sparkbot still prompts for confirmation before creating the job.

```json
{
  "name": "Demo Calendar Write",
  "tool_name": "calendar_create_event",
  "schedule": "at:2026-04-24T20:00:00Z",
  "tool_args": {
    "title": "Sparkbot pilot follow-up",
    "start": "2026-04-24T16:00:00-04:00",
    "end": "2026-04-24T16:30:00-04:00",
    "description": "Follow up on Sparkbot pilot workflows."
  }
}
```

## Security And Ops Notes

- Default posture: read-only scheduled jobs are allowed; write jobs require opt-in configuration and confirmation.
- Breakglass: privileged actions require operator PIN, scoped session TTL, justification, and audit logging.
- Policy simulator: `guardian_simulate_policy` previews allow, confirm, deny, privileged, or privileged-reveal outcomes without executing the target tool.
- Approval inbox: pending confirmations are durable and can be approved or denied from the dashboard, Telegram, GitHub, and bridge surfaces.
- Vault: comms and Google credentials can be stored as use-only secrets, with environment fallback.
- Audit: Task Guardian records run status, verifier confidence, evidence, recommended next action, and output excerpts.
- Recovery: failed or unverified jobs retry within a bounded budget, then pause and escalate instead of looping forever.
- Truth rule: Sparkbot must not present guesses as facts. Any statement, status, diagnosis, or recommendation under 90% confidence has to say what could be wrong and what verification is missing.
- Self-improvement rule: Sparkbot can propose workflow, prompt, docs, policy, or code improvements through Guardian, but must wait for explicit operator approval before applying changes.

## Jarvis Self-Improvement Flow

Sparkbot now treats mistakes and uncertainty as improvement signals:

1. Notice a weak spot: repeated failure, uncertain answer, missing tool, stale docs, unsafe workflow, or incomplete verification.
2. Record it with `guardian_propose_improvement`, including evidence, suggested change, and risk level.
3. Surface the proposal in Guardian/Spine as awaiting approval.
4. Wait for the operator to approve the exact change.
5. Apply only the approved change with the appropriate tool, then verify and report evidence.

Useful demo prompt:

> "List pending Sparkbot improvement proposals, then propose one improvement for anything you think would make this room safer or more useful. Do not apply it yet."

## Marketing One-Pager

Tagline: "Sparkbot - turn agents loose, safely."

Value props:

- Governance-first automation: policy decisions before actions run.
- Local-first agent OS: meetings, scheduled jobs, tools, approvals, memory, and audit evidence run through one governed orchestrator.
- Always-on assistant: scheduled briefings, reminders, diagnostics, and connector workflows.
- Compliance-friendly operations: evidence, approvals, and audit history for risky actions.

Use cases:

- Daily briefings and meeting prep.
- Safe automated deployments and diagnostics.
- PR and CI monitoring.
- Secure secret-driven operations.
- Calendar, inbox, chat, and cloud workflow automation.

Target buyers:

- Engineering leaders.
- SRE and platform teams.
- Security and compliance teams.

## Roadmap Summary

Phase 0, baseline: CI, health checks, basic approval queue, use-only vault secrets, demo flow.

Phase 1, core Jarvis: natural-language command routing, richer connector health, run history, notifications, policy editor, risk defaults.

Phase 2, production: first-class agent identity/permissions, Postgres-backed state, HA scheduler, backups, metrics, audit export, breakglass sessions, credential rotation.

Phase 3, scale: visual trace viewer, persistent mobile approval center/PWA, policy templates, SSO, SIEM, incident-response integrations.

Phase 4, autonomous augmentation: resumable multi-step agents, workflow builder templates, per-tool pre/post validators, and proactive approval requests.

Phase 5, governed self-improvement: Sparkbot continuously proposes concrete improvements from mistakes, low-confidence answers, and missing capabilities, then applies only approved changes with tests, docs, evals, and audit evidence.
