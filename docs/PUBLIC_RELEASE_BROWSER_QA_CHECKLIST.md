# Sparkbot Public Release Browser QA Checklist

Date: 2026-05-20
Branch: `public-release-live-connector-qa`
Purpose: manual browser QA checklist before `Sparkbot_shell` extraction. This is a validation artifact only; it does not approve code copying or feature expansion.

Use this checklist against a fresh local install and, where noted, a server-style install. Record the result in the Pass/Fail and Notes columns. Do not use real customer data or private production channels.

| # | QA item | Priority | Live connector/local provider required? | Expected result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| 1 | Login / first-run | P0 | No | Desktop/local path reaches Sparkbot without exposing template/admin routes; server path requires passphrase; missing model setup leads to AI Setup/Command Center guidance. |  |  |
| 2 | DM / Chat | P0 | One configured model or local provider | `/dm` opens the main chat, sends a message, streams a response, preserves room context, and `/chat` redirects to the public DM flow. |  |  |
| 3 | Workstation | P0 | No | Workstation loads with stable top navigation, visible Sparkbot/Invite/Specialty/Round Table surfaces, no broken template/admin UI, and mobile/desktop scrolling remains usable. |  |  |
| 4 | Invite Wing model seats | P0 | Optional for metadata; required for live turn | Default Codex/OpenAI, Claude/Anthropic, Grok/xAI, and Local AI seats are visible/editable; credentials are write-only and not returned to the browser. |  |  |
| 5 | Local AI setup | P0 | Yes | Ollama/LM Studio/llama.cpp/OpenAI-compatible settings save through backend config; unreachable endpoints show setup-needed/unreachable instead of silent fallback. |  |  |
| 6 | Command Center AI Setup | P0 | Optional | AI Setup shows provider defaults, local model config, model seats, and setup status without stale Controls-only wording. |  |  |
| 7 | Command Center model-seat editor | P0 | Optional; live provider for ready state | Create/edit a seat, toggle Round Table/Specialty Wing visibility, save write-only credential, and reload without exposing the credential value. |  |  |
| 8 | Specialty Wing/custom agents | P1 | Optional; live model for response | Built-in agents stay locked; custom agents can be created/edited; model-seat binding persists as non-secret `model_seat_id`. |  |  |
| 9 | Round Table launch | P0 | At least one configured model path | Workstation launches a meeting room with 2+ participants; Seat 1 defaults to Meeting Manager when available; heartbeat scheduling failure does not block launch. |  |  |
| 10 | Meeting Room | P0 | At least one configured model path | Meeting room loads backend manifest before local cache, keeps chat and controls scrollable, and supports returning from Workstation. |  |  |
| 11 | Meeting Manager seat 1 | P0 | At least one configured model path | Seat 1 is labeled as manager/chair and drives first ideas, assessment, assignments, assigned work, and summary. |  |  |
| 12 | Per-seat model selection | P0 | Optional; live provider for response | Workstation and Meeting Room selectors preserve `seat:<modelSeatId>` choices and distinguish duplicate model IDs. |  |  |
| 13 | Structured assignments | P0 | At least one configured model path | Manager assignments persist as `meeting_assignments` artifacts and render assignment cards without manual notes generation. |  |  |
| 14 | Manager wrap-up/checkpoint memory save | P1 | At least one configured model path | Manager checkpoint/wrap-up creates bounded shared memory/context; saved notes are source-labeled; per-turn meeting notes are not auto-generated. |  |  |
| 15 | Task Guardian health checks | P0 | No for app-only | PC and Server Health Check templates appear, can be added/edited safely, and recent report output is visible in Command Center. |  |  |
| 16 | PC Health Check | P0 | No | App-only PC health run completes with read-only status, severity sections, and no raw secrets/log dumps. |  |  |
| 17 | Server Health Check | P0 | No | App-only server health run completes with read-only status and warns without mutating services/files. |  |  |
| 18 | Operator-channel health report delivery | P1 | Yes, test channels only | Delivery choices are app-only by default; configured test Telegram/Discord/Slack/WhatsApp channels can receive health reports; SMS/text shows setup-needed/future and does not fake delivery. Delivery warnings do not fail the task. |  |  |
| 19a | Security profile: Personal | P0 | Optional | Personal allows configured routine work while confirming risky writes, sends, deletes, terminal writes, service control, and credential access. |  |  |
| 19b | Security profile: Balanced | P0 | Optional | Balanced confirms high-risk configured actions and explains the action before execution. |  |  |
| 19c | Security profile: Locked | P0 | Optional | Locked requires elevated approval/break-glass for high-risk write/execute paths and offers a safe next step. |  |  |
| 19d | Security profile: Custom | P1 | Optional | Custom honestly enforces blocker text only; UI does not claim typed allow/confirm/block rules exist yet. |  |  |
| 20 | Terminal setup-gated behavior | P0 | No | Live terminal desk/CTA stays disabled unless backend reports `WORKSTATION_LIVE_TERMINAL_ENABLED`; terminal commands require confirmation/elevation by profile. |  |  |
| 21 | Robo Preview | P0 | No | Public/default UI shows teaser-only Robo Preview; no live robotics tools, emergency stop, private bridge docs, or hardware controls are exposed. |  |  |
| 22 | Public package/download behavior | P0 | No | Download/source path uses sanitized package or future shell repo, not blind R&D source; package artifacts include checksums/release notes and exclude private artifacts. |  |  |

## QA Notes

- Run browser checks with devtools console open and record uncaught errors.
- Capture screenshots for failures in Workstation, Meeting Room, Command Center AI Setup, Security, Task Guardian, and Robo Preview.
- Do not run destructive live checks. Use safe read-only commands and test connector channels only.


## Task Guardian operator-channel addendum

| QA item | Priority | Live connector/local provider required? | Expected result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| PC health delivery preference save/edit | P0 | No for app-only | App remains default; selected external channels persist as public-safe delivery preferences without connector secrets. |  |  |
| Server health delivery preference save/edit | P0 | No for app-only | Server Health Check preserves schedule, fallback-to-app, selected channels, and last delivery status. |  |  |
| Telegram delivery warning/success | P1 | Yes, test chat only | Configured test chat receives the report; missing setup records a nonfatal warning. |  |  |
| Discord delivery warning/success | P1 | Yes, test channel only | Configured test channel receives the report; missing setup records a nonfatal warning. |  |  |
| Slack delivery warning/success | P1 | Yes, test workspace/channel only | Configured test channel receives the report; missing token/channel or allowlist mismatch records a nonfatal warning. |  |  |
| WhatsApp delivery warning/success | P1 | Yes, test number only | Configured linked test number receives the report; missing setup records a nonfatal warning. |  |  |
| SMS/text unsupported behavior | P1 | No | Selecting/requesting SMS records setup-needed/future status and does not send anything. |  |  |
| Delivery memory continuity | P1 | No for app-only | Latest health report and delivery status are retrievable through shared memory/context without duplicate report spam. |  |  |
| Unauthorized connector access | P0 | Yes, test connector only | Unknown or unlinked connector users cannot retrieve or receive private Task Guardian health reports. |  |  |


## Meeting memory continuity addendum

| QA item | Priority | Live connector/local provider required? | Expected result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| Manager saves meeting notes | P0 | At least one configured model path | Generate Meeting Notes creates a `notes` artifact with source-labeled metadata and shared memory rollup. |  |  |
| Manager edits meeting notes | P0 | No | OWNER/MOD can edit the latest notes and save; updated notes replace stale active memory context. |  |  |
| Main Chat retrieves meeting notes | P0 | One configured model path | Asking Main Chat about recent Round Table decisions/action items uses the saved meeting rollup. |  |  |
| Telegram retrieves meeting notes | P1 | Yes, linked test chat only | Linked/authorized Telegram identity can ask about recent Round Table notes through unified context. |  |  |
| Discord retrieves meeting notes | P1 | Yes, linked test channel/user only | Linked/authorized Discord identity can ask about meeting decisions without broad guild exposure. |  |  |
| WhatsApp retrieves meeting notes | P1 | Yes, linked test number only | Linked/authorized WhatsApp number can ask about recent notes; unknown numbers cannot. |  |  |
| Slack retrieves meeting notes | P1 | Yes, test workspace/channel only | Slack behavior is identity-limited; no private notes leak unless request signature, channel allowlist, sender allowlist, and linked owner are all configured. |  |  |
| Draft notes do not leak | P0 | No | Draft/scaffold/failed-generation notes are not returned as final shared memory. |  |  |
| Per-turn notes remain disabled | P0 | At least one configured model path | Normal participant turns do not create notes artifacts or memory rollups. |  |  |
| Edited notes dedupe/update memory | P0 | No | Old edited decisions are absent from active context after saving updated notes. |  |  |
| Unauthorized connector user cannot retrieve notes | P0 | Yes, test connector only | Unknown/unlinked connector user receives setup/authorization handling and no meeting-note content. |  |  |


## Connector identity QA addendum

| QA item | Priority | Live connector/local provider required? | Expected result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| Slack unsigned request fails closed | P0 | Slack signing test or unit test | Missing/invalid `SLACK_SIGNING_SECRET` prevents event processing and meeting-memory recall. | Automated PASS | Covered by focused backend test; live not configured. |
| Slack unallowed channel/user fails closed | P0 | Slack test workspace/channel/user | Channel not in `SLACK_ALLOWED_CHANNEL_IDS` or sender not in `SLACK_ALLOWED_USER_IDS` receives setup/linking message and no meeting notes. | Automated PASS for helper; live not run | Requires test Slack app/channel/user. |
| Slack linked owner recall | P1 | Slack test app/channel | Signed allowed Slack event with `SLACK_ALLOWED_CHANNEL_IDS`, `SLACK_ALLOWED_USER_IDS`, and `SPARKBOT_SLACK_OWNER_USERNAME` can use linked owner context. | Not run | Requires test Slack app/channel. |
| Telegram unlinked identity isolation | P0 | Telegram test bot/chat | Unknown chat cannot retrieve web-operator meeting notes; allowlisted/operator-mapped chat can be tested separately. | Not run | Connector not configured in this shell. |
| Discord unlinked identity isolation | P0 | Discord test bot/channel | Unknown channel/user cannot retrieve web-operator meeting notes. | Not run | Connector not configured in this shell. |
| WhatsApp unlinked identity isolation | P0 | WhatsApp test number | Unknown number cannot retrieve web-operator meeting notes. | Not run | Connector not configured in this shell. |

## Connector PIN Verification QA Addendum

| QA item | Priority | Live connector/local provider required? | Expected result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| Valid connector PIN session | P0 | No for unit test; yes for live connector | `/pin <PIN>` creates a short connector-scoped session without storing the PIN plaintext. | Automated PASS | Unit tests cover session creation and no raw PIN in session dump. |
| Invalid connector PIN | P0 | No | Invalid PIN does not create a session and private meeting recall remains locked. | Automated PASS | Unit test covered. |
| Expired connector session | P0 | No | Expired connector session fails closed and asks for verification again. | Automated PASS | Unit test covered. |
| Telegram private recall gate | P0 | Telegram test bot/chat | Unallowlisted chat is denied; allowlisted chat requires operator mapping or `/pin <PIN>`. | Not run | Requires test bot; do not use production token. |
| Discord shared channel recall block | P0 | Discord test bot/channel | Guild/shared channel request for meeting notes is told to use DM/Main Chat; no notes are returned. | Not run | Live test required. |
| Slack signed allowed user recall | P0 | Slack test app/channel/user | Signature, channel allowlist, sender allowlist, and linked owner are required before recall. | Not run | Existing Slack helper tests still pass. |
| WhatsApp public setup fail closed | P0 | No for unit test; yes for live sandbox | Missing verify token or empty allowed-phone list disables inbound bridge; unlisted phone is denied. | Automated PASS for defaults | Live sandbox required. |

## Live Connector QA Result Pointer

Live connector QA was not run on 2026-05-21 because no safe test-only connector identities/channels were configured in the current process environment. See `docs/PUBLIC_RELEASE_LIVE_CONNECTOR_QA_RESULTS.md` for exact non-secret missing configuration names and readiness ratings.
