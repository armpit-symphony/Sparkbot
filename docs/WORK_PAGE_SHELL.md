# Work Page Shell

This slice adds a static Work Page preview to the public Sparkbot Workstation shell.

The preview mirrors the public-safe shape of the private shell work surface: work-program planning, workspace-file slots, and remote-index direction. It is intentionally read-only and does not implement file reads, file uploads, file writes, connector calls, worker scheduling, model calls, or backend mutation.

## Preview work areas

- Program queue
- Workspace files
- Remote index

## Current behavior

- Work cards render with `preview` status labels.
- The preview includes no upload controls.
- The preview includes no document editor.
- The preview includes no network search action.
- The preview includes no filesystem write behavior.
- Existing backend `GET /health` and `GET /capabilities` checks remain unchanged as the only frontend network calls.

## Excluded from this baseline

- File ingestion
- File mutation
- Local document persistence
- Connector-backed network-drive search
- Worker assignment execution
- Model calls or routing
- Chat integration
- Tool execution
- Guardian runtime controls

## Follow-up direction

A later slice should define public-safe local workspace contracts before any file handling, connector indexing, worker assignment, or sensitive local action workflow is enabled.
