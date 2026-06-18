# Guardian Controls Shell

This slice adds a static Guardian Controls preview to the public Sparkbot Workstation shell.

The preview is intentionally read-only and does not implement approvals, policy enforcement, tokens, vault behavior, sensitive action execution, or backend mutation.

## Preview control categories

- Local actions
- Provider access
- Files and workspace
- External connections
- Approval checkpoints
- Audit trail

## Current behavior

- Control cards render with `skeleton` or `planned` status labels.
- The preview includes no approval actions.
- The preview includes no execute actions.
- The preview includes no save actions.
- The preview includes no policy enforcement behavior.
- Existing backend `GET /health` and `GET /capabilities` checks remain unchanged as the only frontend network calls.

## Excluded from this baseline

- Real Guardian implementation
- Approval token implementation
- Policy enforcement engine
- Vault or credential storage
- Shell or terminal execution
- Tool execution
- Browser automation
- File mutation controls
- External sends or connector calls
- Model calls or routing
- Backend mutation beyond the existing health endpoint

## Follow-up direction

A later slice should define public Guardian control contracts before any approval, enforcement, or sensitive action workflow is enabled.
