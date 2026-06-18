# Public Capability Contracts

This document defines how public Sparkbot capabilities are described, promoted, and gated. It is a contract for future implementation branches, not a claim that guarded runtime features are implemented today.

## Status Definitions

| Status | Meaning |
| --- | --- |
| `available` | Implemented in the public repo, covered by validation, documented, and safe by default. |
| `preview` | Visible as an inert shell or read-only surface. It must not execute sensitive actions. |
| `planned` | Documented direction with no active runtime behavior. |
| `disabled-by-default` | Implemented only behind a default-off control with tests proving the disabled state. |
| `guarded-future` | Not implemented. Future work requires a safety contract, explicit tests, and review before runtime behavior is added. |

## Promotion Rules

A capability may move to a more active status only when all of the following are true:

- The behavior is covered by focused backend, frontend, or integration tests.
- Public documentation describes what the capability does and does not do.
- `bash scripts/check-public-safety.sh` passes.
- `bash scripts/validate-public-shell.sh` passes.
- The implementation avoids secrets in source files, logs, fixtures, and browser output.
- The default state is safe for a fresh clone.
- The backend `GET /capabilities` response uses only these status values and represents the status before frontend UI claims are made.
- Any sensitive action has an applicable connector, provider, or Guardian contract before runtime work is merged.

## Current Public Capabilities

| Capability | Current status | Contract notes |
| --- | --- | --- |
| Backend health endpoint | `available` | Local read-only `GET /health`. |
| Backend capabilities endpoint | `available` | Local read-only `GET /capabilities`. |
| Frontend shell | `available` | Buildable React/Vite shell with local status display. |
| Workstation shell | `preview` | Product shell preview only. |
| Chat shell | `preview` | No send action, model call, or message persistence. |
| Work Page shell | `preview` | No file reads, file writes, connector calls, or worker execution. |
| Round Table shell | `preview` | No meeting engine or agent orchestration. |
| Provider Setup shell | `preview` | No credential entry, storage, test call, or provider call. |
| Local AI Settings shell | `preview` | No credentials, endpoint checks, provider calls, or model routing. |
| Guardian Controls shell | `preview` | No runtime approval or enforcement path. |
| Desktop packaging | `planned` | No installer, desktop binary, signing, or auto-update path. |
| Connectors | `guarded-future` | Must satisfy `CONNECTOR_SAFETY_CONTRACT.md` before any runtime behavior. |
| Model calls | `guarded-future` | Must satisfy provider configuration and Guardian policy contracts before runtime behavior. |
| Credential storage | `guarded-future` | Must satisfy provider configuration and secret handling gates before any storage path. |
| Tool execution | `guarded-future` | Must satisfy Guardian policy gates before any execution path. |

## Review Checklist

Future branches that change capability status must include:

- The `GET /capabilities` status change.
- Tests proving the new status and default behavior.
- Documentation updates matching the implemented behavior.
- A self-audit showing no unsupported runtime claims were introduced.
- A clear rollback path if validation fails.
