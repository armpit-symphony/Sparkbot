# Command Center Security Audit

Date: 2026-05-17
Branch: `public-release-capability-memory-roundtable`
Scope: Audit and safe planning only.

## Current UI State

Command Center has two Security surfaces:

- Setup-era security panel in `frontend/src/components/CommandCenter/SetupPanels.tsx`.
- Operational Command Center security card in `frontend/src/components/CommandCenter/OperationalPanels.tsx`.

Current UI capabilities:

- Shows Security on/off state from model config or Guardian status (`frontend/src/components/CommandCenter/SetupPanels.tsx:190`, `frontend/src/components/CommandCenter/OperationalPanels.tsx:252`).
- Saves the Security toggle through `/api/v1/chat/models/config` (`frontend/src/hooks/useControlsState.ts:651`, `frontend/src/components/CommandCenter/OperationalPanels.tsx:305`).
- Saves custom guardrails as text (`frontend/src/hooks/useControlsState.ts:679`, `frontend/src/components/CommandCenter/OperationalPanels.tsx:327`).
- Lets the operator set/change PIN and manage break-glass state (`frontend/src/components/CommandCenter/OperationalPanels.tsx:766`, `frontend/src/components/CommandCenter/OperationalPanels.tsx:909`).
- Shows backend security posture: passphrase, operators, frontend bind, headers, CORS, env permissions, risky feature flags, provider-key hints (`frontend/src/components/CommandCenter/OperationalPanels.tsx:752`, `frontend/src/components/CommandCenter/OperationalPanels.tsx:994`).

Public issue: the UI is binary, not profile-based. It says "Security on/off" instead of Free/Personal, Balanced, Locked, Custom. This risks making Sparkbot feel either too loose or randomly blocked.

Phil decision: Custom guardrails should be added through the Security section in Command Center. The public UX should make these feel user-owned and editable, not like hidden hard-coded refusals.

## Current Backend/API State

Wired backend paths:

- Security status API: `backend/app/api/routes/chat/security.py:286`.
- Security posture includes feature toggles and environment checks: `backend/app/api/routes/chat/security.py:318`.
- Passphrase rotation requires privileged operator state: `backend/app/api/routes/chat/security.py:354`.
- Operator users require privileged operator state: `backend/app/api/routes/chat/security.py:369`.
- Operator PIN can be created by an operator and changed under privileged state: `backend/app/api/routes/chat/security.py:388`.
- Risky feature toggles require privileged state: `backend/app/api/routes/chat/security.py:413`.
- Model config exposes guardrail status and custom rules: `backend/app/api/routes/chat/model.py:466`, `backend/app/api/routes/chat/model.py:467`.
- Security toggle writes `SPARKBOT_GUARDIAN_POLICY_ENABLED`: `backend/app/api/routes/chat/model.py:1059`.
- Custom guardrails write `SPARKBOT_CUSTOM_GUARDRAILS`: `backend/app/api/routes/chat/model.py:1086`.

The policy engine is real, not fake:

- Personal mode when policy is off allows routine work and confirms dangerous classes (`backend/app/services/guardian/policy.py:594`).
- Strict mode handles room execution, global Computer Control, privileged actions, confirms, and denies (`backend/app/services/guardian/policy.py:580`, `backend/app/services/guardian/policy.py:635`, `backend/app/services/guardian/policy.py:661`).
- Custom guardrails match exact tool, regex, or phrase while Security is on (`backend/app/services/guardian/policy.py:46`).
- Tool guardrails reject secret-like arguments and malformed risky payloads (`backend/app/services/guardian/tool_guardrails.py:45`, `backend/app/services/guardian/tool_guardrails.py:75`).

## What Is Wired

- Binary Security toggle.
- Owner-authored custom blockers, stored as env JSON.
- Intended public entry point for custom guardrails/blockers in Command Center Security.
- PIN/break-glass operator flow.
- Vault and provider-secret posture.
- Risky feature status for terminal, robotics bridge, global computer control, and bridges.
- Confirmation-required events from tool policy into chat UI (`backend/app/api/routes/chat/rooms.py:1673`, `frontend/src/pages/SparkbotDmPage.tsx:4569`).
- Telegram/Discord approval flows for pending confirmations (`backend/app/services/telegram_bridge.py:762`, `backend/app/services/discord_bridge.py:556`).

## What Is Stubbed Or Incomplete

- No first-class profile selector for Personal/Balanced/Locked/Custom.
- `security_status` includes `prototype`, `private_lan`, and `public_internet` modes (`backend/app/api/routes/chat/security.py:336`), but these are guidance labels, not executable policy profiles.
- Custom guardrails are blocker-only. There is no typed custom rule model with `allow`, `confirm`, `block`, scope, explanation, owner, or expiry.
- No per-surface profile overrides yet. Chat, Workstation, Round Table, terminal, browser, files, and bridges all flow through shared policy decisions but are not separately represented as user-facing profile rows.
- The UI has duplicate Security editing surfaces, which raises drift risk.

## Buggy Or Product-Risky Behavior

| Area | Finding | Public impact | Priority |
|---|---|---|---|
| Approval executors | Dashboard, Telegram, Discord, and confirmed stream paths re-decided policy before execution but previously executed anything except `deny`. | A `privileged` or `privileged_reveal` decision could run through an approval path without the intended PIN/break-glass state. | `P0` |
| Binary Security | Current "on/off" copy hides the product model. | Users may think Sparkbot is either unsafe or randomly blocked. | `P0` |
| Strict Security + Computer Control off | Gated read/execute tools can require PIN even for useful diagnostics (`backend/app/services/guardian/policy.py:661`). | Feels like a locked machine instead of a permissioned assistant. | `P0` |
| Deny wording | Denies return policy text but do not always propose a next safe step (`backend/app/services/guardian/policy.py:650`). | Dead-end blocker experience. | `P0` |
| Auto break-glass | DM auto-triggers `/breakglass` after privileged events (`frontend/src/pages/SparkbotDmPage.tsx:4575`). | Trust boundary is unclear. | `P1` |
| Custom blockers | User rules are env-backed text, not structured owned policy records. | Hard to explain, audit, edit, export, or reuse. | `P1` |
| Tool guardrail rejection | Secret-like args are rejected before execution (`backend/app/services/guardian/tool_guardrails.py:45`). | Correct safety behavior, but UX should redirect to Vault rather than only reject. | `P1` |

## Evolution Into Guardrail Profiles

Recommended staged plan:

1. Rename binary Security state into a profile selector.
2. Keep existing policy engine underneath to avoid a broad rewrite.
3. Add `profile_id` to the returned model/security config.
4. Implement `Personal`, `Balanced`, and `Locked` as policy presets.
5. Keep `Custom` as profile plus owner-authored blockers initially, edited from Command Center Security.
6. Convert custom blockers from env text into structured records:

```json
{
  "id": "rule_...",
  "owner_user_id": "...",
  "name": "No live trading",
  "surface": "all",
  "match": {"type": "regex", "value": "kalshi|live trading"},
  "action": "block",
  "explanation": "Owner does not want Sparkbot to perform trading actions.",
  "enabled": true,
  "created_at": "..."
}
```

## Future Platform Alignment

The reusable design learning for Arc Bot/custom bots/LIMA runtime policy is the profile contract, not Sparkbot's current env implementation. Keep these concepts portable:

- `capability_surface`
- `risk_class`
- `decision`: allow, confirm, privileged, deny
- `explanation`
- `next_safe_step`
- `owner_rule_id`
- `audit_event_id`

Do not move Sparkbot Guardian internals into LIMA in this phase. Sparkbot should first prove the user-owned profile UX.

## Safe Patch Applied In This Phase

Approval execution paths now execute only `allow` or already-confirmed `confirm` decisions. Re-decided `privileged`, `privileged_reveal`, and `deny` decisions return policy text instead of executing the tool.

Changed paths:

- `backend/app/api/routes/chat/rooms.py`
- `backend/app/api/routes/chat/dashboard.py`
- `backend/app/services/telegram_bridge.py`
- `backend/app/services/discord_bridge.py`

Remaining work: make the UI for these blocked approval results tell the user exactly how to proceed, for example "activate break-glass, then retry the action" or "use a read-only alternative".
