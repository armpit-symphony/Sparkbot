# Chat Shell

The current public shell baseline includes a static Chat Shell preview in the public Sparkbot Workstation shell.

The preview is intentionally read-only. It does not implement chat runtime behavior, message sending, message persistence, model calls, model routing, provider credential handling, or backend chat endpoints.

## Current behavior

- The Chat Shell preview renders inside the existing Workstation shell.
- Placeholder conversation cards show the intended future operator and Sparkbot surfaces.
- The planned composer is disabled and read-only.
- There is no send button.
- Existing backend `GET /health` and `GET /capabilities` checks remain unchanged as the only frontend network calls.

## Excluded from this baseline

- Real chat runtime
- User-entered message handling
- Message persistence
- Local storage
- Model calls or routing
- Provider credentials or credential storage
- Streaming
- Guardian runtime controls
- Approval tokens or policy enforcement
- Terminal or tool execution
- External sends or connector calls
- File mutation

## Follow-up direction

A later slice should define public chat interaction contracts before enabling active message handling, provider calls, persistence, or runtime safety gates.
