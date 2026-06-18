# Sparkbot Documentation

This index groups the public Sparkbot documentation for first-time visitors, local developers, and release reviewers.

## Getting started

- [Contributing](../CONTRIBUTING.md): contribution scope, pull request expectations, and validation commands.
- [Security](../SECURITY.md): supported status, security report scope, and reporting guidance.
- [Development](DEVELOPMENT.md): prerequisites, backend workflow, frontend workflow, and current limitations.
- [Local Development](LOCAL_DEVELOPMENT.md): local runner scripts and what they do not enable.
- [Local Smoke Test](LOCAL_SMOKE_TEST.md): alternate-port local smoke testing without touching existing services.
- [Validation](VALIDATION.md): full validation, safety scans, backend checks, and frontend checks.

## Product shell previews

- [Workstation Shell](WORKSTATION_SHELL.md): current read-only workstation layout and status model.
- [Chat Shell](CHAT_SHELL.md): static chat preview and excluded runtime behavior.
- [Work Page Shell](WORK_PAGE_SHELL.md): static work-program and workspace preview with no file actions.
- [Round Table Shell](ROUND_TABLE_SHELL.md): inert planned seats for future multi-agent collaboration.
- [Provider Setup Shell](PROVIDER_SETUP_SHELL.md): provider setup preview with no credential handling.
- [Local AI Settings Shell](LOCAL_AI_SETTINGS_SHELL.md): static local model setup preview with no endpoint checks.
- [Guardian Controls Shell](GUARDIAN_CONTROLS_SHELL.md): planned control categories with no active enforcement.

## Release and readiness

- [Release Readiness](RELEASE_READINESS.md): current readiness position and out-of-scope runtime features.
- [Public Artifact Manifest](PUBLIC_ARTIFACT_MANIFEST.md): files included in the public baseline and excluded artifact types.
- [Release Standards](RELEASE_STANDARDS.md): public publishing identity and release standards.
- [Public v1 Clean Baseline Release Notes](RELEASE_NOTES_PUBLIC_V1_CLEAN_BASELINE.md): first published shell baseline notes.

## Public contracts

- [Public Capability Contracts](PUBLIC_CAPABILITY_CONTRACTS.md): capability status definitions and promotion gates.
- [Connector Safety Contract](CONNECTOR_SAFETY_CONTRACT.md): disabled-by-default connector rules and future live-action gates.
- [Provider Configuration Contract](PROVIDER_CONFIG_CONTRACT.md): provider setup, credential boundary, and model-call gates.
- [Guardian Policy Contract](GUARDIAN_POLICY_CONTRACT.md): future sensitive-action policy and approval gates.

## Roadmap and plans

- [Roadmap](ROADMAP.md): staged public v1.0.0 direction.
- [Desktop Packaging Plan](DESKTOP_PACKAGING_PLAN.md): planning-only desktop packaging direction and release gates.
- [Open Questions](OPEN_QUESTIONS.md): unresolved decisions for future public work.

## Current boundary

The current public shell baseline is safe for review and local validation. It does not include model calls, provider credentials, credential storage, endpoint checks, chat runtime, Round Table meeting runtime, Guardian policy enforcement, file mutation, tool execution, connector calls, desktop packaging, or deployment workflows. The public contracts define the gates future branches must satisfy before any of those behaviors can be promoted.
