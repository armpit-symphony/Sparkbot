# Sparkbot Public Roadmap

This roadmap describes the staged path toward Sparkbot public v1.0.0.

## Phase 0: Public repo foundation

Establish the clean public repository, documentation standards, release standards, and initial project direction.

## Phase 1: Sanitized source inventory

Review candidate ideas and implementation approaches, then rewrite or import only material that meets public release standards.

## Phase 2: Minimal buildable shell

Create a minimal buildable Sparkbot shell with a clear project structure and repeatable local development commands.

## Phase 3: Local-first backend and frontend

Add the initial local-first backend and frontend surfaces with safe defaults and clear setup documentation.

## Phase 4: Workstation shell skeleton and Round Table preview

Establish a read-only Workstation shell skeleton and static Round Table preview seats. Active collaboration behavior remains planned until public interaction contracts and validation gates are documented.

## Phase 4a: Chat shell preview

Add a read-only Chat Shell preview with no message handling, persistence, model calls, provider credentials, or send actions.

## Phase 5: Provider setup shell preview

Add a read-only Provider Setup preview with planned provider profiles and no credential, save, test, or runtime behavior.

## Phase 6: Guardian-gated controls shell preview

Add a read-only Guardian Controls preview with planned control categories and no approval, enforcement, execution, connector, or mutation behavior.

## Phase 6a: Work Page and Local AI Settings previews

Add read-only Work Page and Local AI Settings previews with no file reads, file writes, endpoint checks, provider calls, model routing, or connector actions.

## Phase 7: Desktop packaging and release testing

Define the Windows/local desktop path, smoke tests, release artifacts, and fresh clone validation. Desktop packaging is planned only; no installer or desktop binary exists in the current baseline.

## Phase 8: Plugins and future runtime integration

Expand toward plugins, skills, and deeper runtime integration after the public v1.0.0 foundation is stable.

## Contract gate before runtime expansion

Future runtime branches must satisfy the public capability, connector, provider configuration, and Guardian policy contracts before they can move beyond preview or planned status. This applies to model calls, credential handling, connector calls, external sends, message persistence, tool execution, and sensitive local mutations.
