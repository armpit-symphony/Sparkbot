# Sparkbot Public Capability And Permission Model

Date: 2026-05-17
Branch: `public-release-capability-memory-roundtable`
Scope: Public-release planning for Sparkbot only. This document does not wire LIMA AI OS, Arc Bot, LIMA Office, LIMA IT, robotics, or `Sparkbot_shell`.

## Product Stance

Sparkbot Public should feel like a capable self-hosted AI workstation, not a locked-down agent runner. The default experience should be:

- Sparkbot reasons through the request and attempts useful work.
- Configured tools are available when the owner has enabled them.
- Risky actions ask for confirmation before execution.
- Security blockers explain the reason and propose the next safe step.
- Command Center Security makes guardrails stricter when the user chooses it.
- Custom blockers/guardrails are user-owned, editable, and added through the Security section in Command Center.
- Slack is a public baseline connector target because it should carry across Sparkbot Public, Arc Bot, and future custom bots.
- Free / Personal mode allows terminal and browser capability by default, with confirmation for risky actions.
- The profile pattern should later inform Arc Bot, custom bots, and LIMA runtime policy design, but no runtime wiring happens in this phase.

## Current Implementation Anchors

- Policy toggle: `SPARKBOT_GUARDIAN_POLICY_ENABLED` in `backend/app/services/guardian/policy.py:13`.
- Custom guardrail env: `SPARKBOT_CUSTOM_GUARDRAILS` in `backend/app/services/guardian/policy.py:16`.
- Custom guardrail matching: `backend/app/services/guardian/policy.py:46`.
- Default personal-mode behavior: `backend/app/services/guardian/policy.py:594`.
- Global Computer Control TTL path: `backend/app/services/guardian/policy.py:81`.
- Tool policy registry with allow/confirm/privileged/deny actions: `backend/app/services/guardian/policy.py:105`, `backend/app/services/guardian/policy.py:131`.
- Command Center Security toggle save: `backend/app/api/routes/chat/model.py:1056`.
- Custom guardrail save: `backend/app/api/routes/chat/model.py:1079`.

## Permission Actions

| Action | Public meaning | Product behavior |
|---|---|---|
| `allow` | Safe enough for current profile and configured tool state. | Run the tool and summarize results. |
| `confirm` | Risky or externally visible. | Show a clear yes/no confirmation with tool, target, effect, and cancel path. |
| `privileged` | Requires operator PIN or break-glass session. | Explain the blocker, ask for PIN only when the user chooses to proceed, and offer a safe read-only alternative. |
| `privileged_reveal` | Secret reveal or destructive Vault path. | Require break-glass and explicit confirmation. |
| `deny` | Not supported or blocked by owner rule/profile. | Explain the rule and suggest the nearest safe next step. Never dead-end with only "blocked". |

## Security Profiles

### Free / Personal Mode

Default public mode. Sparkbot is capable by default.

Allowed:
- Normal chat reasoning, model routing, memory recall/write, tasks/reminders, file reads, local/server diagnostics, browser reads, terminal diagnostics, room-local ordinary writes, and safe tool use.
- Configured Telegram/Discord/WhatsApp/GitHub bridges can read and reply in their linked context.
- Configured Slack should follow the same bridge pattern and become part of the public connector baseline.

Requires confirmation:
- External sends, browser writes/clicks/fills, file edits/deletes, package installs/builds, service control, scheduled write jobs, credential writes/reveals, terminal writes, and Git mutations.

Blocked:
- Unknown tools, unsupported real robot/drone/humanoid control, private/proprietary integrations, and owner-defined custom blockers if the user explicitly enables them for this mode later.

### Balanced Mode

Recommended public server/default shared-machine mode.

Allowed:
- Chat, memory, model routing, Workstation navigation, Round Table, file reads, browser reads, diagnostics, task/reminder reads, and configured connector reads.

Requires confirmation:
- File writes, terminal commands, browser form writes/clicks, external sends, connector writes, calendar/mail/Slack/GitHub writes, service changes, and scheduled jobs.

Blocked:
- Real robotics/IoT control, secret reveal without PIN, unconfigured connectors, private build tools, and custom blocker matches.

### Locked Mode

Strict mode for public internet, shared servers, demos, or cautious users.

Allowed:
- Chat, memory recall, memory inspection, model selection, read-only files, read-only browser fetches to public URLs, and Round Table discussion.

Requires confirmation:
- Memory writes/corrections, task/reminder writes, any connector reply, any browser click/fill, and any terminal/server command.

Blocked:
- Terminal writes, service management, Vault reveal/write, real robotics, private network browser targets, unsupported tools, and custom blocker matches unless the user enters a temporary break-glass flow.

### Custom Mode

User-owned profile built from one of the above profiles plus explicit rules.

Allowed:
- Everything the base profile allows, minus custom blocker matches.

Requires confirmation:
- Everything the base profile confirms, plus custom "confirm" rules when implemented.

Blocked:
- Exact tool blockers such as `tool:gmail_send`, regex blockers such as `regex:rm\s+-rf`, and plain text blocker phrases. Current implementation only supports block-style custom rules while Security is on.

## Surface Matrix

| Surface | Personal | Balanced | Locked | Custom |
|---|---|---|---|---|
| Chat | Allow reasoning, memory, safe tools. Confirm risky tools. | Same, with more writes confirmed. | Reasoning and read-only tools by default. | Base profile plus user rules. |
| Workstation | Allow navigation, setup, model seats, Round Table. Confirm risky desks/tools. | Hide or confirm terminal/browser/server tools. | Show core desks only; advanced tools disabled until approved. | Base profile plus user rules. |
| Round Table | Allow manager-led discussion and memory recall. Confirm risky tool calls. | Same; stricter on participant tool use. | Discussion-only unless approved. | Base profile plus meeting-specific user rules later. |
| Telegram | Read/reply in linked private context when configured. Confirm external sends outside context. | Confirm sends and write-like actions. | Confirm every reply/action. | Base profile plus channel rules. |
| Discord | Same as Telegram. | Same as Telegram. | Same as Telegram. | Base profile plus channel rules. |
| Slack | Read/reply in linked workspace context when configured. Confirm external or high-impact sends/actions. | Confirm sends and write-like actions. | Confirm every reply/action. | Base profile plus workspace/channel rules. |
| Terminal | Available by default for diagnostics; writes confirm. | Reads allowed; writes confirm; service control confirm/PIN. | Disabled or PIN-required. | Base profile plus command regex blockers. |
| Browser | Available by default for open/read; writes/clicks/fills confirm. | Reads allowed; clicks/fills confirm. | Read-only unless approved. | Base profile plus URL/action blockers. |
| Files | Read allowed; ordinary writes confirm when outside safe workspace. | Reads allowed; all writes confirm. | Read-only by default. | Base profile plus path blockers. |
| Server/PC tools | Diagnostics allowed in Personal; service changes confirm. | Diagnostics allowed; gated writes confirm/PIN. | PIN-required or blocked by default. | Base profile plus host/service allowlists. |

## Public MVP Recommendation

Ship with Personal, Balanced, Locked, and Custom profile names in Command Center, but implement them as clear policy presets over the existing policy engine before adding a full custom-rule DSL. The first safe step is to rename the current binary "Security on/off" into a profile selector while preserving the existing env contract:

- Personal maps to `SPARKBOT_GUARDIAN_POLICY_ENABLED=false`.
- Balanced maps to `SPARKBOT_GUARDIAN_POLICY_ENABLED=true` with default confirmations but fewer hard denies.
- Locked maps to `SPARKBOT_GUARDIAN_POLICY_ENABLED=true` with terminal/server/browser writes off unless break-glass is active.
- Custom stores user blockers added through Command Center Security and later supports typed user confirmation/block rules.

P0 principle: every `deny` or `privileged` outcome must give the user an understandable reason and one useful safe alternative.

## Safe Patch Applied In This Phase

Confirmed approval executors now refuse to run re-decided `privileged` or `privileged_reveal` outcomes. This preserves the "risky actions require the right permission" rule while keeping normal `confirm` approvals capable.

Remaining profile work is product-facing: turn the current binary Security toggle into named Personal/Balanced/Locked/Custom profiles with clear explanations.

## P0 Stabilization Update - 2026-05-17

Branch: `public-release-p0-memory-guardrails-roundtable`

Implemented:

- Command Center model config now has persisted `security_profile` and `security_profiles` fields.
- Free / Personal is the capable-by-default public profile. It leaves terminal/browser capability available when configured and relies on existing confirmation gates for risky actions.
- Balanced, Locked, and Custom are now named/persisted profiles instead of only conceptual docs.
- Custom guardrails remain user-owned blocker text in Command Center Security. The UI marks typed custom allow/confirm rules as draft rather than claiming full enforcement.
- DM privileged/elevated flow no longer starts breakglass silently.
- Slack is documented and partially wired as the public baseline connector pattern: shared memory, same LLM route, and same permission context concepts.
- Robo remains visible but public default backend/tool behavior is teaser-only: dry-run contracts can exist, but live robotics control is blocked unless a private env flag disables teaser mode.

Still true:

- This phase does not wire LIMA AI OS, Arc Bot, LIMA Office, LIMA IT, or real robotics/IoT.
- The profile contract is reusable design learning for Arc Bot/custom bots/LIMA runtime policy later, not runtime coupling now.
- `Sparkbot_shell` remains untouched.

## Surface UX Update - 2026-05-17

Branch: `public-release-surface-nav-room-ux`

Implemented public truthfulness changes:

- Workstation Computer Control copy now frames terminal/browser as configured capabilities with confirmations for risky actions, not as unrestricted machine control.
- Live terminal UI now checks backend security status and disables the live terminal desk/CTA unless `features.live_terminal.enabled` is true.
- Free / Personal still remains capable by default for configured tools, but raw PTY terminal access is visibly setup-required until an operator explicitly enables `WORKSTATION_LIVE_TERMINAL_ENABLED`.
- Robo remains visible as a public teaser, but the default UI is static preview copy and does not imply real robot, drone, humanoid, or IoT control.
- The operational Robo/MCP registry panel is dev/private-flag only through `VITE_SPARKBOT_ROBO_MCP_PANEL=true`.

Remaining policy work:

- Balanced and Locked now have first-pass backend behavior separation; browser QA should verify the pending-confirm and elevated-confirm UI labels match.
- Browser, shell, files, and connector writes should show profile-specific confirmation/block labels in the UI.
- Custom guardrails need typed user-owned allow/confirm/block records before Custom mode can claim full enforcement.

## Artifact / Guardrail Cleanup Update - 2026-05-18

Branch: `public-release-artifact-guardrail-robo-cleanup`

Profile behavior now implemented in backend policy:

- Free / Personal: capable by default when tools are configured; risky writes, deletes, sends, credential access, service control, and critical changes still ask confirmation.
- Balanced: configured high-risk shell, browser, external send, file/delete/install, server/PC, and Robo Preview actions ask confirmation even when capability is enabled.
- Locked: high-risk write/execute actions require elevated approval or break-glass; non-operators get a blocker explanation and next safe step.
- Custom: uses the same high-risk posture as Balanced plus user-owned blocker text. Typed allow/confirm/block records remain future work and should not be claimed as fully enforced.

Robo remains preview-only in public/default mode. Private Robo bridge execution requires an explicit private env gate and is not part of public core.

## Invite Wing Update - 2026-05-17

Branch: `public-release-invite-wing-model-seats`

Implemented:

- Invite Wing model seats are backend-owned public MVP configuration.
- Codex/OpenAI, Claude/Anthropic, and Grok/xAI seats remain as editable defaults.
- Seat metadata is sanitized before it reaches the frontend.
- Credentials submitted from Invite Wing are saved in Guardian Vault and are not persisted in browser `localStorage`.
- Round Table invite-seat route registration now sends a `modelSeatId` and resolves Vault credentials backend-side.
- Specialty Wing model selectors include model-seat model IDs.

Remaining policy work:

- Specialty Wing per-agent routing still needs a seat-specific credential binding when a model seat is configured only through Vault and not through a global provider/CLI auth path.

## Task Guardian Health Check Update - 2026-05-17

Branch: `public-release-task-guardian-health-checks`

Implemented public capability behavior:

- PC Health Check and Server Health Check are built-in Task Guardian templates, not hidden system mutations.
- Health collection is read-only and safe by default: no package updates, no service restarts, no destructive commands, and no credential reveal.
- Templates default to `daily-local:06:00`, disabled/app-only until the owner adds them.
- Optional Telegram/Discord/Slack report delivery requires configured connectors and explicit task settings.
- Reports use source-labeled memory summaries through `task_guardian.health.pc` and `task_guardian.health.server`.

Profile implication:

- Personal and Balanced can run read-only health checks when Task Guardian is enabled.
- Locked should still allow owner-approved read-only health checks, while write-like remediation stays blocked or elevated.
- Custom guardrails may later add user-owned blockers for specific health checks, delivery channels, or host paths.

## Final Cleanup Update - 2026-05-18

Branch: `public-release-final-cleanup-assessment`

Capability model updates:

- Public/default Robo remains preview-only. Real robotics/IoT bridge execution requires a private R&D flag and is excluded from public core behavior.
- Command Center Security reports `private_robo_bridge` through `SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED`, avoiding stale LIMA-labelled feature status in the public UI.
- Public package generation replaces the private R&D Robo bridge implementation with a non-executing Robo Preview stub.
- Balanced and Locked are now behaviorally different in backend policy for high-risk configured actions.
- Task Guardian health checks expose app, Telegram, Discord, and Slack delivery choices, but app/in-room delivery remains default and external sends remain owner opt-in.
- Public Docker/server defaults keep `BACKEND_WORKERS=1` until recurring schedulers have a leader lock or dedicated singleton worker.

## Connector PIN Verification Update - 2026-05-21

- Added connector-scoped, time-limited PIN verification sessions for private meeting recall.
- Reused existing Guardian operator PIN hashing, verification, failed-attempt tracking, and lockout behavior; no raw PIN is stored in connector sessions.
- Private meeting recall now fails closed unless the external connector has a linked/authorized operator identity or a valid connector PIN session.
- Telegram private recall requires `TELEGRAM_ALLOWED_CHAT_IDS`; Telegram `/breakglass` now requires explicit `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS` mapping.
- Discord shared guild channels are blocked from private meeting recall; use DM plus `/pin <PIN>` for test/private recall.
- Slack still requires signed request, allowed channel, allowed sender, and linked owner before private context is considered.
- WhatsApp inbound now requires explicit `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_ALLOWED_PHONES`; the predictable runtime verify-token default was removed.
- SMS/text remains future/unsupported.
- Live connector QA remains required with test-only identities/channels.
