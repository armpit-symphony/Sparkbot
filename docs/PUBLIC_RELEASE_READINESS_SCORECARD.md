# Sparkbot Public Release Readiness Scorecard

Date: 2026-05-20
Branch: `public-release-qa-assessment`
Legend: GREEN = ready enough, YELLOW = needs QA/polish, RED = blocker, UNKNOWN = needs live/manual test.

| Area | Rating | Evidence | Blocker if any | Recommended next action |
|---|---|---|---|---|
| Product identity clarity | YELLOW | README/status docs now describe Sparkbot Public and Round Table, but public clone/download copy still points at the R&D repo in places. | Public source path can bypass package sanitation. | Point public source installs at sanitized package or `Sparkbot_shell`; keep R&D clone docs private. |
| Workstation UX | YELLOW | Sticky nav, public surfaces, terminal gating, and Robo Preview are implemented. | Browser QA still required across desktop/mobile. | Run manual Workstation QA checklist. |
| Chat/DM | YELLOW | `/chat` redirects to `/dm`; backend tests pass. | Browser streaming/login QA still required. | Run DM smoke with configured cloud/local model. |
| Round Table | YELLOW | Manager default, per-seat models, structured assignments, and no per-turn notes are implemented. | Main hero flow not browser-verified this pass. | Browser QA Round Table launch and Meeting Room flow. |
| Meeting Manager flow | YELLOW | Seat 1 manager and assignment artifacts exist; heartbeat continuation may need polish. | Live meeting behavior unknown. | Test 3+ participant meeting and heartbeat. |
| Model seats / Invite Wing | YELLOW | Backend/Vault storage, write-only credentials, setup status, and stable seat selectors are implemented. | Live provider and duplicate-seat browser QA remain. | Test create/edit/use cloud and local seats. |
| Local AI | UNKNOWN | Unit/focused tests pass and local provider layer exists. | Live Ollama/LM Studio/llama.cpp not tested. | Execute live local endpoint QA. |
| Specialty Wing/custom agents | YELLOW | Built-ins locked, custom edit and model-seat binding implemented. | Browser flow and live response QA remain. | Test custom agent with model seat. |
| Command Center AI Setup | YELLOW | Model-seat editor and local config exist. | Browser QA required. | Test save/reload/error states. |
| Command Center Security | YELLOW | Personal/Balanced/Locked/Custom are persisted; backend policy tests pass. | Browser pending/elevated confirmation UX not verified. | Run profile matrix QA with safe actions. |
| Unified memory/context | GREEN | Focused memory/context tests pass; source-labeled adapter exists; secrets are redacted. | Richer UI memory inspection is later polish. | Keep as extraction candidate after browser QA. |
| Task Guardian health checks | YELLOW | Unit tests pass; PC/server templates and app delivery exist. | Live connector delivery not tested; scheduler leadership remains later. | Test app-only and configured test connector delivery. |
| Robo Preview boundary | GREEN | Backend tests pass; package tar contains non-executing preview stub. | Full R&D bridge remains tracked and must not be blindly extracted. | Extract only package stub/public boundary. |
| Packaging/downloads | RED | Package dry-run passes after relative-path fix; key exclusions and stub verified. Auditor found tests and `.github` workflows still included. | Public source bundle still includes tests/workflows with private/internal references and stale deploy workflows. | Sanitize/exclude tests/workflows and fix public source docs before public source release. |
| Documentation | YELLOW | New QA/status docs exist and public status is clearer. | Some public docs still point at R&D repo and use stale Controls/template naming. | Update install/download copy and naming in a focused docs pass. |
| Security/privacy posture | YELLOW | Focused tests pass; secrets not stored in frontend model seats; package excludes dotenv/log/DB/key examples checked. | Root `.dockerignore` missing for repo-root Compose contexts; browser guardrail QA pending. | Add root `.dockerignore`; run guardrail profile QA. |
| Public/private separation | RED | Package replaces Robo bridge and excludes many private docs. | R&D repo source still contains private bridge and public package includes tests/workflows; blind extraction unsafe. | Refresh extraction map from sanitized package, not raw repo. |
| Sparkbot_shell readiness | YELLOW | Product shell is much closer and Layer 1 candidates are clear. | Extraction should wait until packaging/docs blockers and browser/live QA complete. | Run packaging sanitation pass, browser QA, then extraction map refresh. |

## Summary

GREEN: unified memory/context, Robo Preview runtime/package stub boundary.

YELLOW: most product surfaces are implementation-ready but require browser/live QA and polish.

RED: public packaging/download boundary and public/private separation are not ready for source-public release or blind `Sparkbot_shell` import.

UNKNOWN: live Local AI and connector delivery until tested against real test endpoints/channels.
