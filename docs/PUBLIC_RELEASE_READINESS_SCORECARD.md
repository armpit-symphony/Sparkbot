# Sparkbot Public Release Readiness Scorecard

Date: 2026-05-21
Branch: `public-release-connector-pin-verification`
Legend: GREEN = ready enough, YELLOW = needs QA/polish, RED = blocker, UNKNOWN = needs live/manual test.

| Area | Rating | Evidence | Blocker if any | Recommended next action |
|---|---|---|---|---|
| Product identity clarity | YELLOW | README and public download docs now distinguish the R&D/source-reference repo, sanitized public release bundle, and future `Sparkbot_shell` repo. | Browser/download-page copy still needs a final release-site review. | Keep public install CTA on sanitized bundles; refresh `Sparkbot_shell` map after QA. |
| Workstation UX | YELLOW | Sticky nav, public surfaces, terminal gating, and Robo Preview are implemented. | Browser QA still required across desktop/mobile. | Run manual Workstation QA checklist. |
| Chat/DM | YELLOW | `/chat` redirects to `/dm`; backend tests pass. | Browser streaming/login QA still required. | Run DM smoke with configured cloud/local model. |
| Round Table | YELLOW | Manager default, per-seat models, structured assignments, and no per-turn notes are implemented. | Main hero flow not browser-verified this pass. | Browser QA Round Table launch and Meeting Room flow. |
| Meeting Manager flow | YELLOW | Seat 1 manager, assignment artifacts, source-labeled notes, and owner/mod note editing now exist. | Live meeting and browser edit-permission behavior unknown. | Test 3+ participant meeting, notes save/edit, and heartbeat. |
| Model seats / Invite Wing | YELLOW | Backend/Vault storage, write-only credentials, setup status, and stable seat selectors are implemented. | Live provider and duplicate-seat browser QA remain. | Test create/edit/use cloud and local seats. |
| Local AI | UNKNOWN | Unit/focused tests pass and local provider layer exists. | Live Ollama/LM Studio/llama.cpp not tested. | Execute live local endpoint QA. |
| Specialty Wing/custom agents | YELLOW | Built-ins locked, custom edit and model-seat binding implemented. | Browser flow and live response QA remain. | Test custom agent with model seat. |
| Command Center AI Setup | YELLOW | Model-seat editor and local config exist. | Browser QA required. | Test save/reload/error states. |
| Command Center Security | YELLOW | Personal/Balanced/Locked/Custom are persisted; backend policy tests pass. | Browser pending/elevated confirmation UX not verified. | Run profile matrix QA with safe actions. |
| Unified memory/context | GREEN | Meeting notes roll into shared work memory, edits supersede stale rollups, drafts/scaffolds are skipped, and Main Chat uses the same context adapter. Slack now fails closed unless signed, channel-allowed, sender-allowed, and linked to an existing owner; connector PIN sessions add time-limited step-up verification for private recall. | Live connector PIN and identity QA remains required for Telegram/Discord/WhatsApp/Slack before cross-channel recall is GREEN. | Run live connector PIN and identity QA with test accounts only. |
| Task Guardian health checks | YELLOW | PC/server templates now store public-safe delivery preferences, preserve app history, record delivery warnings, write source-labeled memory, and expose app/Telegram/Discord/Slack/WhatsApp/SMS status in Command Center. | Live connector delivery and mobile-first NL setup still need QA; SMS is explicitly future/unsupported. | Run app-only, configured connector, missing-setup, and SMS unsupported QA. |
| Robo Preview boundary | GREEN | Backend tests pass; package tar contains non-executing preview stub. | Full R&D bridge remains tracked and must not be blindly extracted. | Extract only package stub/public boundary. |
| Packaging/downloads | YELLOW | Package script now excludes `.github`, `.agents`, backend/frontend tests, Playwright config, test scripts, virtualenvs, dotenv/example/log/DB/key artifacts, private docs, and replaces the Robo bridge with the preview stub. | Needs final package inspection on the generated artifacts plus Windows/Git Bash and clean-clone smoke. | Run package dry-run/inspection on release candidate and publish only sanitized bundles. |
| Documentation | YELLOW | Public install/download copy now points source installs at sanitized release bundles and documents raw repo as R&D/source reference. | Final release-site/download copy and browser QA notes still need review. | Keep docs aligned with release artifact names, checksums, and future `Sparkbot_shell` handoff. |
| Security/privacy posture | YELLOW | Root `.dockerignore` now excludes local env/example files, keys/certs, DBs, logs, caches, tests, CI metadata, package outputs, and private docs from repo-root Docker contexts. | Browser guardrail QA and live connector/local-provider checks remain. | Run Personal/Balanced/Locked/Custom guardrail matrix with safe actions. |
| Public/private separation | YELLOW | Sanitized package boundary now excludes tests/workflows/internal agent instructions and keeps the public Robo Preview stub while the R&D repo remains intact. | Raw R&D repo still is not the public install target; blind `Sparkbot_shell` import remains unsafe. | Refresh extraction map from the sanitized artifact after package and browser/live QA. |
| Sparkbot_shell readiness | YELLOW | Product shell is much closer and Layer 1 candidates are clear. | Extraction should wait until packaging/docs blockers and browser/live QA complete. | Run packaging sanitation pass, browser QA, then extraction map refresh. |

## Summary

GREEN: unified memory/context, Robo Preview runtime/package stub boundary.

YELLOW: most product surfaces, packaging/downloads, and public/private separation are implementation-ready but require browser/live QA, clean artifact inspection, and release-site review.

RED: no current scorecard area remains RED after the source-boundary cleanup, assuming package inspection stays clean. Blind `Sparkbot_shell` import is still not approved.

UNKNOWN: live Local AI plus Telegram/Discord/WhatsApp connector recall/delivery until tested against real test endpoints/channels. Connector PIN hardening is automated, but live Telegram/Discord/WhatsApp/Slack recall remains UNKNOWN until test-only identities are configured. SMS/text remains future/unsupported.
