# Consumer Readiness Checklist

## Goal

Move Sparkbot from an operator-focused internal assistant to a consumer-safe product without losing its useful automation surface.

## Security — The Differentiator

While competitors are being described in mainstream press as "security nightmares," Sparkbot ships with guardrails that most enterprise tools charge extra for. This is the story to lead with.

### What is already true (ship this message now)

- [x] **Policy before autonomy.** Every tool is classified read / write / execute / admin before it can run. Unknown tools are denied by default.
- [x] **No silent external writes.** Email, Slack, GitHub, Notion, Confluence, Calendar, Drive — all require a confirmation modal. The LLM cannot bypass it.
- [x] **Execution gate defaults off.** Server and SSH commands are locked until the room owner explicitly enables the gate. Per room.
- [x] **Audit trail on every tool call.** Allow, confirm, and deny decisions are logged with redacted arguments.
- [x] **Audit redaction.** Secret-pattern keys and token-format values are stripped before any log write — not as a post-processing step.
- [x] **Executive decision journal.** High-risk actions write a structured entry before and after execution under `data/guardian/executive/decisions/`.
- [x] **Policy simulator.** `guardian_simulate_policy` previews allow / confirm / deny / break-glass outcomes before an automation runs.
- [x] **Persistent approval inbox.** Pending confirmations are stored durably and exposed through dashboard, Telegram, GitHub, and bridge approval flows.
- [x] **Truth and confidence guardrails.** Sparkbot must disclose uncertainty under 90% confidence and name the missing verification step instead of guessing.
- [x] **Approval-first self-improvement.** Sparkbot can propose improvements, but code/config/docs/workflow changes still require explicit operator approval before execution.
- [x] **Meeting orchestrator baseline.** Round Table meetings, meeting heartbeats, project rooms, notes/artifacts, and Guardian follow-up tasks already work as an orchestrated loop.
- [x] **HttpOnly cookies.** Session tokens are never reachable from JavaScript. No localStorage tokens.
- [x] **Security headers.** HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy, Referrer-Policy on every response.
- [x] **Dependency scanning CI.** `pip-audit` + `npm audit` on every push and weekly.
- [x] **Full internal security audit passed.** Phases A–E complete. See `SECURITY.md`.
- [x] **No secrets in git history.** `.env` purged via `git filter-repo`; `gitleaks` pre-commit hook active.

### Remaining security work before public launch

- [ ] Publish a plain-language privacy and data retention page (non-technical users need this before trusting the product with their email/calendar).
- [ ] Add visible permission labels in the UI — non-technical users should see what each integration can and cannot do before they connect it.
- [ ] Add first-class agent identity records: owner, purpose, scopes, allowed tools, expiration, risk tier, and kill switch.
- [ ] Add a visual trace viewer for prompt/model/tool/approval/guardrail/output/cost/audit-hash timelines.
- [ ] Add a broader evaluation harness for agent behavior regressions.
- [ ] Add stronger ownership checks on any endpoint that reads or mutates room state.
- [ ] End-to-end tests for confirmation flow, execution gate, and audit log.

## Current Strengths (product)

- Chat is streaming and stable in the live `sparkbot-v2` stack.
- Memory Guardian gives Sparkbot better recall across sessions.
- Token Guardian shadow mode is capturing routing and cost telemetry.
- Policy decisions now gate tool use and enforce room execution boundaries.
- Executive Guardian journals high-risk actions.
- Task Guardian supports approved read-only recurring work.
- Round Table and task-linked project meetings operate as an orchestrator with participant manifests, meeting heartbeats, notes/artifacts, and follow-up tasks.
- Persistent approvals can be approved/denied from dashboard and bridge surfaces.
- Guardian Improvement records outcome learning and approval-required self-improvement proposals.
- Gmail, Drive, reminders, tasks, audit, and server diagnostics are all available behind a single chat surface.

## Must-Have Before Wider Consumer Use

### Access and Safety

- [x] Room execution gate defaults to off.
- [x] High-risk tools require explicit confirmation.
- [x] Tool actions and policy decisions are audited.
- [x] Room-scoped scheduled jobs are restricted to approved read-only tools.
- [x] Write-like shell changes require confirmation when Guardian policy mode is enabled.
- [x] Sparkbot self-improvement changes are proposal-first and approval-required.
- [x] Policy simulator can preview risky tool outcomes before users enable automations.
- [ ] Add clearer permission labels in the UI for non-technical users.
- [ ] Add stronger ownership checks anywhere room state can be read or mutated.

### Onboarding and UX

- [x] Telegram bridge foundation exists in the backend, using private-chat polling and room mapping.
- [x] Sparkbot DM now has a controls panel for execution gate, policy visibility, and scheduled jobs.
- [x] Superuser settings now include a Sparkbot ops overview tab.
- [ ] First-run onboarding should explain what Sparkbot can and cannot do.
- [ ] Add visible navigation to Sparkbot controls so users do not need to guess browser routes like `/dm` or `/settings`.
- [ ] Add starter templates for common scheduled jobs.
- [ ] Add empty states and friendlier errors for integrations that are not configured.

### Reliability

- [x] Live chat stream bug around tool-confirmation path has been fixed.
- [x] Task Guardian scheduler runs inside FastAPI startup.
- [x] Reminder scheduling and reminder listing now work again in the live stack after the March 6 async guard fix.
- [x] Meeting heartbeat continues autonomous Workstation meetings and stops on terminal states.
- [ ] Add end-to-end tests for reminder creation, confirmation flow, and room controls.
- [ ] Add health/status surface for Guardian components.

### Consumer Trust

- [x] No secrets are committed to GitHub.
- [x] Runtime Guardian data is ignored by git.
- [ ] Publish a plain-language privacy and data retention note.
- [ ] Publish an integrations/setup guide for non-technical users.

## Recommended Next Milestones

1. Polish the Sparkbot controls UI for non-technical room owners.
2. Add canned recurring-job templates.
3. Add first-class agent identity and a visual run timeline.
4. Add a lightweight admin dashboard for Guardian status and queue health.
5. Add onboarding copy and product guardrails for first-time users.
6. Run an end-to-end consumer smoke pass on login, chat, reminders, Gmail, Drive, Telegram, meetings, approvals, and room settings.
