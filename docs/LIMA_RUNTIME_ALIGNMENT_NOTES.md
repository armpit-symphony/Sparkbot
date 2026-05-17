# LIMA Runtime Alignment Notes

Date: 2026-05-17
Branch: `public-release-capability-memory-roundtable`
Scope: Documentation only. No LIMA AI OS/runtime code was modified or wired.

## Boundary

Sparkbot Public is the product shell. It should prove the user experience for:

- Workstation UI
- Round Table meetings
- persistent memory
- permissioned capability behavior
- Command Center Security profiles
- user-owned custom blockers
- Slack bridge continuity as a baseline connector pattern

LIMA AI OS/runtime should not be wired in this phase. These notes are only design cross-references for future review.

## Concepts That Should Stay Sparkbot Public

- Public Workstation UX and spatial desk/table metaphors.
- Round Table meeting room UI and public product language.
- Local-first install flow and self-hosted packaging.
- Provider/model setup UX and Invite Wing public model-seat flow.
- Public docs/download/install polish.
- Robo/PC/server capability teaser copy.

## Concepts That Can Inform Future LIMA Runtime

| Sparkbot concept | Future runtime learning |
|---|---|
| Permission actions: allow/confirm/privileged/deny | Runtime policy should return explainable decisions, not opaque failures. |
| Security profiles | Runtime policy should support named owner-selectable profiles, not only environment flags. |
| Custom blockers | Runtime should represent owner-authored rules as structured policy records. |
| Guardrail redirect behavior | A block should include reason, owner rule, and next safe step. |
| Shared Work Memory | Runtime memory should support source-labeled cross-surface events. |
| Slack bridge memory | Connector bridges should use the same memory and permission contract across products. |
| Meeting manager flow | Multi-agent runtime should support chaired phases, assignment state, and summary checkpoints. |

## Concepts That Can Inform Arc Bot And Custom Bots

- Bot-specific capability profiles derived from the same permission model.
- Custom blockers scoped to bot, workspace, surface, channel, or tool family.
- Memory scopes: user profile, room/project, shared work, connector channel.
- Slack as a safe base connector pattern for Sparkbot Public, Arc Bot, and custom bots.
- Explainable refusals with editable owner rules.
- Agent meeting manager pattern for multi-agent coordination.

## Places Sparkbot May Reveal Future Runtime Tweaks

| Sparkbot behavior | Future tweak candidate |
|---|---|
| Binary Security on/off feels too blunt. | Runtime should expose named profiles and profile diffs. |
| Strict mode can require PIN for useful diagnostics. | Runtime should distinguish read diagnostics from write/control actions more clearly. |
| Custom blockers are text/env-backed. | Runtime needs durable structured policy objects. |
| Meeting artifacts roll into shared memory. | Runtime memory needs artifact-aware rollups and dedupe. |
| Tool guardrails reject secret-like arguments. | Runtime should redirect to Vault/secret-safe flow. |
| Chat, bridges, and meetings share memory unevenly. | Runtime should enforce a common memory interface per surface. |

## Do Not Move Public Boundaries

Do not move these into public core or LIMA wiring during this phase:

- full LIMA AI OS internals
- proprietary Guardian Suite internals
- LIMA Office logic
- LIMA IT logic
- Arc Bot shell logic
- real robotics/IoT adapters
- real robot/drone/humanoid control
- paid orchestration
- client-specific automation
- private server paths or deployment assumptions

## Future Review Questions

1. Should LIMA runtime policy use the same profile names as Sparkbot Public?
2. Should custom blocker records be portable between Sparkbot, Arc Bot, custom bots, and LIMA runtime?
3. Should runtime memory store meeting artifacts as first-class events or consume Sparkbot rollups?
4. Should PC/server/robot capabilities be one policy family or separate capability surfaces?
5. Should "teaser/demo only" capabilities have a formal disabled-manifest state?

## Recommendation

Use Sparkbot Public as the UX proving ground. Once users can understand, edit, and trust Sparkbot's profiles and memory continuity, extract the policy and memory contract as design input for LIMA runtime review.

## P0 Stabilization Update - 2026-05-17

Branch: `public-release-p0-memory-guardrails-roundtable`

Observed reusable design learning:

- Slack bridge continuity is now a concrete public baseline pattern: connector event -> source-labeled memory -> shared work memory when enabled -> LLM context. This should inform Arc Bot/custom bot connector bridges later.
- Security profiles are now persisted in Sparkbot config, but Balanced/Locked still need deeper behavior separation before they become a reusable runtime contract.
- Custom guardrails remain owner blocker text, not structured records. The future LIMA/runtime-facing lesson is the desired record shape, not this env-backed storage.
- Round Table assignment persistence proves a lightweight chaired-meeting contract: chair, phase, handle, assignment, artifact metadata, and non-rollup memory flag.
- Robo teaser behavior now demonstrates a disabled-manifest state: visible product teaser, dry-run/demo contract allowed, live execution blocked by public default.

Still do not move:

- No Sparkbot code from this pass should be copied into LIMA runtime.
- No LIMA AI OS, Arc Bot, LIMA Office, LIMA IT, robotics, or IoT execution wiring was added.
- Sparkbot Public should keep proving the UX before any runtime extraction or contract hardening.
