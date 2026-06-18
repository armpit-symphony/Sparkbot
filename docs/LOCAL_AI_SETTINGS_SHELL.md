# Local AI Settings Shell

This slice adds a static Local AI Settings preview to the public Sparkbot Workstation shell.

The preview mirrors the public-safe shape of the private shell settings surface: local model setup direction, model-seat planning, and readiness-check placement. It is intentionally read-only and does not implement credential entry, credential storage, endpoint checks, provider calls, model calls, model routing, or backend mutation.

## Preview settings areas

- Local runtime setup
- Model seats
- Readiness checks

## Current behavior

- Local AI settings cards render with `preview` status labels.
- The preview includes no credential fields.
- The preview includes no editable provider fields.
- The preview includes no save actions.
- The preview includes no endpoint checks.
- The preview includes no provider calls or model routing.
- Existing backend `GET /health` and `GET /capabilities` checks remain unchanged as the only frontend network calls.

## Excluded from this baseline

- Real provider configuration
- Credential entry or persistence
- Vault or secret management
- Provider authentication
- Endpoint reachability checks
- Model calls or routing
- Chat integration
- Tool execution
- Guardian runtime controls

## Follow-up direction

A later slice should extend the public provider configuration contract before any endpoint check, credential workflow, provider call, or model routing behavior is enabled.
