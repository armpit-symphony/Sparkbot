# Release Readiness

This document tracks public shell readiness for review and phased release decisions.

## Current baseline

- Backend: local read-only health and capabilities endpoints are present and validated.
- Frontend: static shell previews are present and can display backend capability statuses with local fallback.
- Workstation, Chat, Work Page, Round Table, Provider Setup, Local AI Settings, and Guardian Controls are preview or skeleton surfaces.

## Not yet in scope

- Provider credential workflows
- Local model endpoint checks
- File ingestion or file mutation workflows
- Model execution and routing
- Approval token workflows
- Policy enforcement runtime
- Sensitive action execution
- Desktop packaging and install artifacts
- Desktop binaries, installers, auto-update, and code signing
- Deployment workflows

## Readiness position

This repository is suitable for professional public review as an early shell baseline.

This repository does not claim production readiness or complete product functionality.

## Dependency hygiene checkpoint

The `public-v1-frontend-audit-fix-0` tag records a lockfile-only frontend audit advisory fix.

- Purpose: restore npm audit clean state after high-severity advisories.
- Scope: `frontend/package-lock.json` only.
- Runtime behavior: unchanged.
- Resolved packages: `form-data` to `4.0.6`, `vite` to `8.0.16`.
- Validation: npm audit, frontend tests/build, backend compile/tests, public safety scan, and full public shell validation passed.
- Known non-blocking warnings: Starlette/FastAPI `httpx` deprecation warning during backend tests; `whatwg-encoding` npm deprecation warning during frontend install.

This checkpoint does not broaden release readiness beyond the early public shell review baseline.

## Capabilities status checkpoint

The `public-v1-capabilities-status-0` checkpoint adds a read-only `GET /capabilities` backend endpoint and frontend capability status display with local fallback. It does not add model calls, provider credential handling, chat runtime, Guardian enforcement, connector sends, or desktop installer behavior.

## Capability safety contracts checkpoint

The public capability safety contracts define review gates for future runtime work. They do not add runtime behavior. The backend capabilities endpoint and frontend fallback status model are expected to use the same contract statuses. Future branches that introduce provider setup, model calls, credential handling, connector actions, tool execution, persistence, or Guardian enforcement must satisfy these contracts before public merge:

- `docs/PUBLIC_CAPABILITY_CONTRACTS.md`
- `docs/CONNECTOR_SAFETY_CONTRACT.md`
- `docs/PROVIDER_CONFIG_CONTRACT.md`
- `docs/GUARDIAN_POLICY_CONTRACT.md`

## Desktop packaging status

Desktop packaging is planned but not implemented. The current repository contains planning notes and release gates only. No installer, desktop binary, auto-update path, or code signing configuration is present.

## Contribution and security posture

The repository includes lightweight contribution and security reporting guidance for quiet public review. The current baseline does not provide a production support guarantee.
