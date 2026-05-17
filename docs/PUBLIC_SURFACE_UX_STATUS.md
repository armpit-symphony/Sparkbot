# Sparkbot Public Surface UX Status

Date: 2026-05-17
Branch: `public-release-surface-nav-room-ux`
Base: `public-release-p0-memory-guardrails-roundtable` at `93eb39d9bd0534c59140a84ddab4124bd911c325`

Scope: public shell navigation, room layout, route cleanup, terminal truthfulness, and Robo teaser UI. This pass does not modify `Sparkbot_shell`, wire LIMA AI OS, wire Arc Bot/LIMA Office/LIMA IT, or add real robotics/IoT control.

## Baseline Findings

| Area | Current state before this pass | Public issue | Status after this pass |
|---|---|---|---|
| Global app shell | `/dm`, `/workstation`, `/meeting/:roomId`, and `/spine` use product-specific shells rather than one shared wrapper. | Top navigation was inconsistent by surface. | `SparkbotSurfaceTabs` now stays available on chat, Workstation, Meeting Room, and Command Center. Meeting Room includes Chat, Workstation, Robo, Command Center, and Info handlers. |
| Workstation | Header was part of the scrollable workstation surface. | Users could lose the main tabs while scrolling. | Header is sticky at the top of the workstation shell. |
| Meeting Room | Whole page could scroll; sidebar controls could become painful to reach during long meetings. | Room options, manager controls, and page navigation could scroll away. | Page root is fixed-height, header is sticky, desktop main area keeps the sidebar and chat pane in separate scroll regions, and chat history uses a `min-h-0` flex pane. |
| `/chat` route | Legacy route imported `ChatPage` and only redirected in V1 local mode. | Legacy debug/tap UI could be bundled into the public route. | `/chat` always redirects to `/dm` and no longer imports `ChatPage`; `ChatPage` no longer exports a route. |
| Devtools/template routes | Router/Query devtools mounted from root; Admin and Items were normal route surfaces. | Public builds exposed development/template residue. | Devtools are dynamically loaded only in dev mode; Admin and Items redirect to `/dm` outside dev; sidebar nav no longer exposes Dashboard, legacy Chat, Settings, or Admin as public tabs. |
| Template titles | Signup/recovery/settings/admin/items titles still said FastAPI Template. | Public polish/brand leak. | Titles were renamed to Sparkbot. |
| Terminal | Workstation terminal desk and live terminal CTA looked like normal public features even when backend live terminal is disabled. | Public user could see a raw shell affordance without clear setup/permission gating. | Workstation marks the terminal desk as setup-required unless `/api/v1/chat/security/status` confirms `live_terminal` is enabled; the terminal CTA is disabled until explicitly enabled by an operator. |
| Robo | Robo tab/panel linked to a private runtime README and showed operational MCP controls by default. | Public surface implied real robotics/runtime control. | Robo tab stays visible, but default panel is a static teaser. Operational MCP registry panel is dev/private-flag only via `VITE_SPARKBOT_ROBO_MCP_PANEL=true`. |

## Global Nav Persistence

Implemented:

- `/dm`: already had sticky header and `SparkbotSurfaceTabs`.
- `/workstation`: header is now sticky with the same top tabs.
- `/meeting/:roomId`: sticky header now exposes Chat, Workstation, Robo, Command Center, and Info.
- `/spine`: already has the product top tabs and remains the Command Center surface.
- `/controls` and `/command-center`: both remain aliases into `/spine`.

Deferred:

- A single shared public shell component still needs a later consolidation pass. This phase avoided a broad layout rewrite and kept existing surface-specific shells.

## Meeting Room Sticky Controls

Implemented:

- Meeting Room root uses `height: 100dvh` and `overflow: hidden`.
- Header uses sticky/top `0` and can wrap tabs on narrower widths.
- Desktop `main` uses an internal scroll model instead of page scroll.
- Sidebar controls, participant/meeting tabs, meeting notes button, and back navigation stay reachable while chat history scrolls.
- Chat pane uses `min-h-0 flex-1` so the message log can own the scroll region.

Not changed:

- Per-turn generated notes remain disabled.
- Manager wrap-up/checkpoint/manual notes behavior remains intact.
- Structured assignment persistence remains intact.
- Assignment display cards are still a remaining polish task.

## Route Cleanup

Public-visible cleanup:

- `/chat` redirects to `/dm`.
- Admin and Items are dev-gated.
- Devtools are dev-only dynamic imports.
- Sidebar navigation exposes public workstation surfaces only: Workstation, Sparkbot, and Command Center when a chat session exists.
- Template page titles were renamed to Sparkbot.

Known remaining cleanup:

- `ChatPage.tsx` still exists as legacy code, but it is no longer imported by the public route.
- The dashboard route still exists but is not exposed in public nav.
- Some internal component labels still use "Controls"; the product naming should converge on "AI setup" for provider/model setup and "Command Center" for security/operations.

## Terminal Public Status

Public behavior now matches the current backend gate:

- Live terminal is disabled by default unless `WORKSTATION_LIVE_TERMINAL_ENABLED=true`.
- Workstation checks `/api/v1/chat/security/status` for `features.live_terminal.enabled`.
- If the security status cannot be read or the feature is off, the terminal desk shows setup-required and opening it routes to Security & Computer Control rather than a live PTY panel.
- The Computer Control panel explains that Personal mode can use configured terminal/browser capability, but live terminal still requires explicit operator setup.

Remaining terminal blocker:

- Browser/shell/chat tool actions still need deeper Balanced vs Locked behavior tuning. This pass only made the visible live terminal surface truthful.

## Robo Teaser Status

Default public behavior:

- Robo remains visible as a top tab and Workstation card.
- The default Robo panel is a static preview explaining that public Sparkbot does not expose real robot, drone, humanoid, or IoT control.
- The operational MCP registry panel is not shown by default outside dev/private flag.

Remaining Robo blocker:

- Public package/source-bundle cleanup should still exclude private runtime docs and LIMA/Robo internals before extraction.

## Remaining UX Blockers

- Invite Wing credential backend/Vault storage.
- Built-in public agent prompt rewrite.
- Public package exclusions and private path cleanup.
- Deeper Balanced vs Locked behavior.
- Final Round Table assignment UI polish.
- Naming pass for old "Controls" copy versus AI setup/Command Center.
