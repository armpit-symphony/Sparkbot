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
| Local AI | Ollama, LM Studio, llama.cpp, or OpenAI-compatible local endpoint | `local/local-model` | Keep |

## Implementation Status

| Area | Status | Notes |
|---|---|---|
| Seat defaults | Implemented | Backend returns sanitized `model_seats` from `/api/v1/chat/models/config`. |
| Seat customization | Implemented | Invite Wing modal saves label, provider, auth mode, model id, enabled state, Round Table visibility, Specialty Wing visibility, and notes through backend config. |
| Credential storage | Implemented for Invite Wing | Credentials submitted from Invite Wing are stored in Guardian Vault under backend-owned aliases. Raw credentials are not returned to the frontend. |
| Browser storage | Implemented cleanup | Workstation no longer reads/writes credential-bearing `sparkbot_invite_configs`; it removes the legacy key on load. |
| Round Table seats | Implemented | Meeting seat metadata carries `modelSeatId`, model id, and auth mode only. Route registration resolves Vault credentials backend-side. |
| Specialty Wing model choices | Implemented small pass | Model-seat model IDs appear in agent model selectors. Agent overrides can now persist `model_seat_id`, and backend route context resolves Vault credentials server-side for selected seats. |
| Command Center agents | Implemented small pass | Custom agents can be created and edited from Command Center. Built-in agents remain locked for public MVP. |

## Storage Rules

- Sparkbot must not store subscription passwords or browser cookies.
- Frontend may store non-sensitive layout preferences.
- Model-seat credentials must be backend-owned and stored in Guardian Vault or another approved secure local store.
- Sanitized seat metadata may include ids, labels, providers, auth modes, model ids, enabled flags, and configured booleans.

## Unified Context Spine Update - 2026-05-17

Branch: `public-release-unified-context-spine`

Implemented:

- Added shared public model-seat helper logic in `backend/app/services/model_seats.py`.
- Preserved `model_seat_id` in backend `agent_overrides`.
- Resolved selected model-seat credentials server-side in `get_agent_route_context(...)`.
- Explicit Vault-backed model-seat routes now report setup-needed when the selected seat credential is missing instead of silently falling back to global provider credentials.
- Updated Command Center, Workstation Specialty Wing, and legacy DM Controls model override saves to include only non-secret seat ids.
- Updated Round Table meeting override prep to keep `model_seat_id` with the participant route metadata.
- Added backend tests for model-seat override persistence and backend-side credential resolution.

## Remaining Blockers

1. Add a full model-seat editor in Command Center instead of only Workstation Invite Wing.
2. Add clearer setup-needed UI when a Specialty Wing agent selects an unconfigured or disabled model seat.
3. Decide whether Claude subscription mode should use only CLI/session auth for public MVP or allow OAuth access-token entry.
4. Add broader frontend regression coverage when the project has a stable test harness for Command Center/Workstation controls.

## Package Cleanup Note - 2026-05-17

The package/prompt cleanup pass did not change Invite Wing behavior. It did keep the public positioning: Codex/OpenAI, Claude/Anthropic, and Grok/xAI remain editable default model seats, credentials stay backend/Vault-owned, and public package exclusions now remove internal readiness/status docs from generated source bundles.

## Local AI Update - 2026-05-17

Branch: `public-release-local-ai-integration`

Implemented:

- Added `invite-local` as the default Local AI model seat.
- Local seats can use `auth_mode=none` for localhost or user-owned local/LAN endpoints.
- Local seats preserve non-secret `local_runtime`, `base_url`, `model_id`, enabled state, and Round Table/Specialty Wing visibility.
- Round Table invite route setup now accepts local model seats without requiring a Vault credential.
- Specialty Wing overrides can select local model seats while keeping any optional API key backend-only.

Remaining:

1. Add a full Command Center model-seat editor for all default seats, including Local AI. `DONE_FIRST_PASS_2026-05-18`
2. Add setup-needed badges when a local model seat is selected but the endpoint is not reachable. `DONE_FIRST_PASS_2026-05-18`
3. Browser-test Local AI setup against live Ollama, LM Studio, and llama.cpp endpoints.

## Round Table Model-Seat UI Update - 2026-05-18

Branch: `public-release-roundtable-modelseat-ui-polish`

Implemented:

- Command Center AI Setup now lists model seats and supports create/edit for cloud, subscription, and local seats.
- Credential fields are write-only; raw values are not returned to frontend config.
- Backend model-seat payloads include public-safe `setup_status` and `setup_message`.
- Vault-backed seats require their own Vault credential and show setup-needed when missing.
- Local AI seats show ready only when the configured endpoint/model status is reachable; otherwise they show setup-needed/unreachable.
- Workstation chair picker, Meeting Room seats, and model groups surface model-seat labels and setup-needed state.
- Round Table meeting metadata preserves non-secret `modelSeatId`, model id, route, auth mode, and setup status on manifest save/reload.

Remaining:

1. Browser QA model-seat creation/editing and Vault-backed setup with a real provider key.
2. Harden selectors if multiple configured seats intentionally share the same model id.
