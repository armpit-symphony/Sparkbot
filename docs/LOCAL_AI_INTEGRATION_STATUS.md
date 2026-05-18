# Local AI Integration Status

Date: 2026-05-17
Branch: `public-release-local-ai-integration`

## Product Target

Sparkbot Public should make local AI feel native, not like an Ollama-only side path. A non-technical user should be able to start with Ollama, while a technical user can point Sparkbot at LM Studio, llama.cpp / llama-server, or another OpenAI-compatible local endpoint.

This pass keeps the layer public-safe:

- No code was copied to `Sparkbot_shell`.
- No LIMA AI OS, Arc Bot, LIMA Office, or LIMA IT runtime was wired.
- No robotics or IoT control was implemented.
- No proprietary Guardian Suite internals were exposed.
- No local endpoint secrets are stored in browser storage.

## Implemented

| Area | Status | Notes |
|---|---|---|
| Local provider abstraction | Implemented small pass | Added a backend local provider helper with `provider_type=local`, `local_runtime`, `base_url`, `model_id`, `display_name`, `enabled`, `auth_mode`, chat capability, and safe status fields. |
| Ollama | Improved | Ollama remains first-class, keeps `http://localhost:11434` as the default, and AI Setup now saves the editable Ollama base URL through the existing model config route. |
| LM Studio | Implemented via Local AI endpoint | Users can configure LM Studio as a local OpenAI-compatible endpoint, defaulting to `http://localhost:1234/v1`. |
| llama.cpp / llama-server | Implemented via Local AI endpoint | Users can configure llama.cpp / llama-server as a local OpenAI-compatible endpoint, defaulting to `http://localhost:8080/v1` when selected. |
| Generic local endpoint | Implemented | Users can set any OpenAI-compatible local or LAN/server endpoint with a `local/<model-id>` model id. |
| Custom local endpoint | Implemented | Custom runtime uses the same OpenAI-compatible adapter and editable base URL/model id. |
| Endpoint status | Implemented small pass | Backend status endpoint reports configured/reachable/model-list state without requiring a dependency or crashing when the endpoint is not running. |
| Model seats | Implemented | Invite Wing now includes a default `invite-local` Local AI seat, supports no-key local auth, and preserves `local_runtime` plus `base_url` as non-secret seat metadata. |
| Round Table | Implemented small pass | Enabled local model seats can be selected for Round Table invite participants. Route prep now reports setup errors instead of silently ignoring failed backend route registration. |
| Specialty Wing | Implemented small pass | Specialty Wing agent overrides can select local model seats; backend route context resolves local endpoint settings server-side and does not require a Vault secret for no-key local seats. |
| Chat / DM | Implemented backend path | `local/<model-id>` routes through the local OpenAI-compatible adapter when local AI is enabled/configured. |
| Context spine | Aligned | Local model and model-seat metadata use the same model/provider labels as other chat, Round Table, and Specialty Wing runs, so responses follow existing shared memory/context paths. |

## Public Configuration

Environment values supported by this pass:

```env
SPARKBOT_LOCAL_AI_ENABLED=true
SPARKBOT_LOCAL_AI_RUNTIME=lmstudio
SPARKBOT_LOCAL_AI_BASE_URL=http://localhost:1234/v1
SPARKBOT_LOCAL_AI_MODEL=local/my-model
SPARKBOT_LOCAL_AI_DISPLAY_NAME=Local AI
SPARKBOT_LOCAL_AI_AUTH_MODE=none
SPARKBOT_LOCAL_AI_API_KEY=...
```

`SPARKBOT_LOCAL_AI_RUNTIME` accepts `ollama`, `lmstudio`, `llamacpp`, `openai_compatible`, or `custom`. `SPARKBOT_LOCAL_AI_AUTH_MODE` accepts `none` or `api_key`.

Localhost providers require no API key by default. If a user protects a local/LAN endpoint with a key, the key is backend-owned and must not be stored in browser localStorage.

## Still Deferred

1. Full dynamic model discovery for every local runtime in every UI surface.
2. A complete Command Center model-seat editor for local seats.
3. User-visible setup-needed badges everywhere a local Specialty Wing or Round Table seat is selected but unreachable.
4. Browser QA for the Local AI setup panel against a live Ollama and a live OpenAI-compatible server.
5. Embedded/local runtime runner work. This phase only supports external local servers.

## Validation

- Python compile for changed backend modules: passed.
- Focused backend tests for local model config, no-secret local seats, invite-route setup, and OpenAI-compatible local completion routing: passed.
- Full targeted model route suite: passed.
- Frontend production build: passed.
