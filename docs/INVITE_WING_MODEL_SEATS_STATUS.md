# Invite Wing Model Seats Status

Date: 2026-05-17
Branch: `public-release-invite-wing-model-seats`

## Public Product Decision

Invite Wing remains part of the Sparkbot Public MVP. It is the place for customizable model seats: external or premium bring-your-own models that can participate in Round Table meetings and appear in Specialty Wing model choices.

Default public seats:

| Seat | Provider | Default model | Public status |
|---|---|---|---|
| Codex / OpenAI | OpenAI Codex subscription | `openai-codex/gpt-5.3-codex` | Keep |
| Claude / Anthropic | Anthropic | `claude-sonnet-4-6` | Keep |
| Grok / xAI | xAI | `xai/grok-4.20-multi-agent-0309` | Keep |

## Implementation Status

| Area | Status | Notes |
|---|---|---|
| Seat defaults | Implemented | Backend returns sanitized `model_seats` from `/api/v1/chat/models/config`. |
| Seat customization | Implemented | Invite Wing modal saves label, provider, auth mode, model id, enabled state, Round Table visibility, Specialty Wing visibility, and notes through backend config. |
| Credential storage | Implemented for Invite Wing | Credentials submitted from Invite Wing are stored in Guardian Vault under backend-owned aliases. Raw credentials are not returned to the frontend. |
| Browser storage | Implemented cleanup | Workstation no longer reads/writes credential-bearing `sparkbot_invite_configs`; it removes the legacy key on load. |
| Round Table seats | Implemented | Meeting seat metadata carries `modelSeatId`, model id, and auth mode only. Route registration resolves Vault credentials backend-side. |
| Specialty Wing model choices | Partial | Model-seat model IDs appear in agent model selectors. Existing provider/model routing still requires the relevant provider or CLI auth path to be available. Seat-specific Vault credential routing for arbitrary Specialty Wing agents remains a follow-up. |
| Command Center agents | Implemented small pass | Custom agents can be created and edited from Command Center. Built-in agents remain locked for public MVP. |

## Storage Rules

- Sparkbot must not store subscription passwords or browser cookies.
- Frontend may store non-sensitive layout preferences.
- Model-seat credentials must be backend-owned and stored in Guardian Vault or another approved secure local store.
- Sanitized seat metadata may include ids, labels, providers, auth modes, model ids, enabled flags, and configured booleans.

## Remaining Blockers

1. Wire Specialty Wing per-agent routing to a selected `modelSeatId` when a seat has Vault-only credentials and no global provider key.
2. Add a full model-seat editor in Command Center instead of only Workstation Invite Wing.
3. Add backend tests around `model_seats` save/load and Vault secret non-disclosure.
4. Decide whether Claude subscription mode should use only CLI/session auth for public MVP or allow OAuth access-token entry.
