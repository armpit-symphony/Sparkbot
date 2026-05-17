# Public Shell Layer Plan

Date: 2026-05-17
Branch: `public-release-capability-memory-roundtable`
Goal: Define a layer-by-layer path before extracting `Sparkbot_shell`.

## Layer 1 - Clean App Frame

Goal: A polished public shell with no template/debug residue.

Public features included:
- Login/first-run
- Chat
- Workstation
- Round Table
- Command Center / Controls
- Memory/files/tasks entry points

Private/proprietary excluded:
- internal R&D docs
- private deployment paths
- template Admin/Items surfaces
- devtools in production

Readiness dependencies:
- Prior P0 public-release audit items.
- Public nav definition for local/server mode.

Extraction risk:
- Pulling duplicate routes and debug surfaces into the shell.

Validation required:
- Build
- route smoke test
- first-run smoke test

## Layer 2 - Core Brain / Model Stack / Chat

Goal: One reliable chat surface with model routing and setup.

Public features included:
- `/dm` as primary chat
- model selector
- model stack
- local Ollama/cloud provider setup
- custom/basic agents

Private/proprietary excluded:
- internal service prompts
- private provider assumptions
- R&D-only agent roles

Readiness dependencies:
- Provider allowlist consistency.
- Remove or redirect debug `/chat`.

Extraction risk:
- Splitting model config contracts between shell and full repo.

Validation required:
- chat send/receive
- model config save/load
- agent route override smoke test

## Layer 3 - Persistent Memory Spine

Goal: One memory substrate across surfaces.

Public features included:
- user-visible memory list/correct/delete
- Guardian memory ledger
- Shared Work Memory
- meeting wrap-up rollups
- bridge continuity

Private/proprietary excluded:
- internal runtime memory plans
- client-specific memory pipelines

Readiness dependencies:
- Slack bridge memory parity.
- Backend meeting manifest load in Meeting Room UI.
- Source labels for task/reminder/workstation events.

Extraction risk:
- Creating duplicate memory stores.

Validation required:
- main chat remembers fact
- Round Table recalls main chat memory
- manager wrap-up appears in later main chat context
- bridge memory smoke tests

## Layer 4 - Round Table MVP

Goal: Make "Round Table meetings for your AI agents" the public hook.

Public features included:
- eight-seat Workstation launcher
- manager/Seat 1 flow
- assignments
- manual and manager-checkpoint notes
- shared memory rollup

Private/proprietary excluded:
- internal R&D meeting automations
- proprietary project orchestration

Readiness dependencies:
- Backend manifest source of truth.
- Heartbeat best-effort launch.
- Manager phase/status UI.

Extraction risk:
- LocalStorage-only seats and hidden backend assumptions.

Validation required:
- launch meeting
- first pass
- manager assessment
- assignments
- assigned work
- manager summary
- no per-turn generated notes

## Layer 5 - Files / Tools / Terminal / Browser Behind Permissions

Goal: Capable-by-default tools with owner-controlled permissions.

Public features included:
- file upload/read
- safe browser reads
- terminal/server diagnostics
- confirmed file/browser/terminal writes

Private/proprietary excluded:
- raw public shell access by default
- real robotics/IoT control
- private server adapters

Readiness dependencies:
- Permission profile model.
- Clear confirmation modal.
- Terminal hidden/disabled unless local operator enables it.

Extraction risk:
- Shipping dangerous tool access as casual public UI.

Validation required:
- read tool runs
- write tool confirmation
- deny/blocked path explains next safe step

## Layer 6 - Guardrail Profiles / Custom Blockers

Goal: Security feels user-owned, explainable, and editable.

Public features included:
- Personal
- Balanced
- Locked
- Custom
- custom blocker text initially
- later structured custom rules

Private/proprietary excluded:
- advanced Guardian internals
- internal policy queues
- private runtime policy code

Readiness dependencies:
- Profile selector over existing env/policy engine.
- Better deny/privileged UX copy.
- Custom rule storage plan.

Extraction risk:
- Binary Security on/off makes public Sparkbot feel unreliable.

Validation required:
- profile save/load
- custom blocker deny
- Personal mode allows capable work
- Locked mode blocks/asks correctly

## Layer 7 - Public Polish / Install / Docs

Goal: Installable, understandable, desirable public beta.

Public features included:
- README
- public downloads
- desktop/server install
- local-first docs
- Workstation and Round Table onboarding

Private/proprietary excluded:
- `/home/sparky`
- private publish paths
- internal workload history
- private deployment workflows

Readiness dependencies:
- Source-bundle excludes.
- Version consistency.
- Product copy pass.

Extraction risk:
- Public repo looks like internal R&D instead of a product shell.

Validation required:
- package build
- fresh install checklist
- download links

## Layer 8 - Teasers / Private Upgrade Paths

Goal: Show future power without shipping private core.

Public features included:
- Robo/PC/server teaser cards
- disabled manifests
- "local operator only" labels
- future integration notes

Private/proprietary excluded:
- full LIMA AI OS
- Arc Bot
- LIMA Office
- LIMA IT
- real robot/drone/humanoid adapters
- paid orchestration

Readiness dependencies:
- Feature flags or public/private build modes.
- Robo tab reduced to teaser-only.

Extraction risk:
- Accidentally publishing robotics/control-plane internals.

Validation required:
- public build has no executable robotics path
- teaser links/copy reviewed by Phil

## Extraction Rule

Do not copy code to `Sparkbot_shell` until Layers 1-4 P0 blockers are closed and Layer 5/6 boundaries are defined enough to prevent accidental unsafe public defaults.
