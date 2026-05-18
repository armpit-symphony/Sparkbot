# Round Table Model-Seat UI Status

Date: 2026-05-18
Branch: `public-release-roundtable-modelseat-ui-polish`
Base: `public-release-local-ai-integration` at `ac46e3f1d3b5252159214cd613aa6054c4f1c94d`

## Scope

This pass polishes the public model-seat flow across Workstation, Round Table, Meeting Room, Specialty Wing, and Command Center. It does not copy code to `Sparkbot_shell`, wire LIMA AI OS, Arc Bot, LIMA Office, or LIMA IT, expose Guardian Suite internals, or implement robotics/IoT control.

## Current Status

| Area | Status | Notes |
|---|---|---|
| Seat 1 Meeting Manager default | Implemented | New Workstation Round Table drafts, stack autofill, task meetings, and post-launch resets prefer the `meetings_manager` Specialty Wing office for seat 1 when available. |
| Round Table launch setup model choice | Implemented | Chair picker now exposes a seat model selector for assigned agents and shows setup-needed status for Invite Wing/model-seat chairs. |
| Meeting Room model choice | Implemented | Meeting Room seated participant controls now include agent selection, per-seat model selection, model-seat setup status, and manager labeling. |
| Structured assignment display | Implemented | Meeting Room reads latest `meeting_assignments` artifacts and renders assignment cards in the sticky control rail. |
| Meeting phase display | Implemented | Meeting Room shows current phase in the room header and assignment panel from SSE phase metadata or persisted assignment artifacts. |
| Command Center model-seat editor | Implemented small pass | AI Setup now lists model seats and supports create/edit, provider, company, model id, local runtime/base URL, auth mode, enabled state, Round Table/Specialty Wing visibility, notes, and write-only credential entry. |
| Setup-needed status | Implemented small pass | Backend returns `setup_status` and `setup_message` for model seats. UI shows ready/setup-needed/unreachable/disabled status in Command Center, Workstation Invite Wing, Round Table chair picker, and Meeting Room seats. |
| Local AI unreachable state | Implemented small pass | Local model seats are `ready` only when configured endpoint status is reachable and the selected model is available. Otherwise they show setup-needed or unreachable. |
| Vault-backed missing credentials | Implemented | API-key/OAuth model seats require their own backend Vault secret and report setup-needed when missing instead of falling back to unrelated global provider keys. |
| Specialty Wing model binding | Implemented | Custom Specialty Wing agent overrides preserve `model_seat_id` where a selected model matches an enabled Specialty Wing seat; credentials remain backend-only. |

## Model Seat Surfaces

| Surface | Model selector/status behavior |
|---|---|
| Command Center | Full model-seat editor is in AI Setup. Specialty Wing agent route selector includes Local AI. |
| Workstation desk detail | Specialty Wing agents can choose model overrides from configured model groups, including model seats. Invite desks show setup status. |
| Workstation chair picker | Assigned agent chairs can change model before launch. Invite/model-seat chairs show setup guidance and link to seat editing. |
| Round Table launch | Seat metadata includes `modelSeatId`, model id, route, setup status, and auth mode where available. |
| Meeting Room | Seats show manager status, assigned agent, selected model, setup-needed status, and allow model changes for future turns. |
| Specialty Wing | Custom agent overrides store route/model/model-seat id only; no raw credentials are stored in frontend config. |

## Public-Safe Boundaries

- Credentials remain backend/Vault-owned and are never returned to frontend config.
- Frontend sends optional credential values only through the Command Center model-seat save call as write-only input.
- Meeting manifests carry non-secret `modelSeatId`, provider route, model id, configured/setup status, and auth mode metadata.
- Per-turn meeting notes remain disabled. Manager wrap-up/checkpoint/manual notes remain the memory paths.
- Robo remains unchanged as teaser-only; no real robotics or IoT control was wired.

## Remaining Blockers

1. Browser QA the model-seat editor and Round Table chair picker with live local endpoints and Vault-backed cloud seats.
2. Add a uniqueness-safe model-seat selector value if Phil expects multiple seats with the same provider/model id.
3. Tune Balanced vs Locked guardrail behavior separation.
4. Run the approved artifact/.venv/Robo public-stub cleanup branch.
5. Refresh the Sparkbot_shell extraction map after the remaining cleanup branches land.
