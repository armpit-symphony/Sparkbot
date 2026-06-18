# Provider Setup Shell

This slice adds a static Provider Setup shell preview to the public Sparkbot Workstation shell.

The preview is intentionally read-only and does not implement credential storage, provider calls, model routing, or backend secret handling.

## Preview provider cards

- Local model provider
- OpenAI-compatible provider
- Anthropic-compatible provider
- Google-compatible provider
- Custom endpoint

## Current behavior

- Provider cards render with `skeleton` or `planned` status labels.
- The preview includes no API key input fields.
- The preview includes no save actions.
- The preview includes no test connection actions.
- Existing backend `GET /health` and `GET /capabilities` checks remain unchanged as the only frontend network calls.

## Excluded from this baseline

- Real provider configuration
- Credential entry or persistence
- Vault or secret management
- Provider authentication
- Model calls or routing
- Chat integration
- Tool execution
- Guardian runtime controls

## Follow-up direction

A later slice should define a public-safe provider configuration contract before any runtime behavior or credential workflow is enabled.
