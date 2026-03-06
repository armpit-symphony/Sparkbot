# Consumer Readiness Checklist

## Goal

Move Sparkbot from an operator-focused internal assistant to a consumer-safe product without losing its useful automation surface.

## Current Strengths

- Chat is streaming and stable in the live `sparkbot-v2` stack.
- Memory Guardian gives Sparkbot better recall across sessions.
- Token Guardian shadow mode is capturing routing and cost telemetry.
- Policy decisions now gate tool use and enforce room execution boundaries.
- Executive Guardian journals high-risk actions.
- Task Guardian supports approved read-only recurring work.
- Gmail, Drive, reminders, tasks, audit, and server diagnostics are all available behind a single chat surface.

## Must-Have Before Wider Consumer Use

### Access and Safety

- [x] Room execution gate defaults to off.
- [x] High-risk tools require explicit confirmation.
- [x] Tool actions and policy decisions are audited.
- [x] Room-scoped scheduled jobs are restricted to approved read-only tools.
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
3. Add a lightweight admin dashboard for Guardian status and queue health.
4. Add onboarding copy and product guardrails for first-time users.
5. Run an end-to-end consumer smoke pass on login, chat, reminders, Gmail, Drive, Telegram, and room settings.
