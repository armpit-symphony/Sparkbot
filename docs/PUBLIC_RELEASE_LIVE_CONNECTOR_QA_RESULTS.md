# Public Release Live Connector QA Results

Date: 2026-05-21
Branch: `public-release-live-connector-qa`
Base commit: `05e59f691d0cd292059632d2813e67106b04d8b6`

## Safety Rule

No live connector messages were sent in this pass. Test-only identities/channels could not be confirmed from the current process environment or local env-file shape. Connector credentials, PINs, tokens, phone numbers, chat IDs, and secrets were not printed.

## Non-Secret Configuration Presence

| Connector | Process env configured? | Local env-file configured? | Test-only target confirmed? | Live send allowed? | Notes |
|---|---:|---:|---:|---:|---|
| Telegram | No | No | No | No | Missing `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`, and `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS`. Do not run polling without a fresh test bot and explicit allowed test chat. |
| Discord | No | Disabled | No | No | `.env.local` contains `DISCORD_ENABLED=false`; missing token, DM-only setting, and test channel/user allowlists. |
| Slack | No | No | No | No | Missing `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_ALLOWED_CHANNEL_IDS`, `SLACK_ALLOWED_USER_IDS`, and `SPARKBOT_SLACK_OWNER_USERNAME`. |
| WhatsApp | No | No | No | No | Missing `WHATSAPP_ENABLED`, `WHATSAPP_PHONE_ID`, `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, and `WHATSAPP_ALLOWED_PHONES`. |
| SMS/text | No connector | No connector | No | No | No SMS/text connector exists; Task Guardian records SMS/text as future/setup-needed only. |
| Task Guardian external delivery | No live connector target | No live connector target | No | No | App/task-history path can be tested locally; external channel delivery requires configured test targets. |

## Connector Results

| Connector | Configured? | Test identity/channel available? | Tests run | Result | Evidence summary | Failures/blockers | Readiness |
|---|---|---|---|---|---|---|---|
| Telegram | No | No | Non-secret config inspection only | Not run live | Required process env values are absent; local env-file values are not usable for test-only live QA. | Need fresh test bot/token, `TELEGRAM_ALLOWED_CHAT_IDS`, `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS` if testing linked operator recall, and safe polling posture. | UNKNOWN |
| Discord | Partial/disabled | No | Non-secret config inspection only | Not run live | `DISCORD_ENABLED` is present locally but false; token/channel/DM test setup missing. | Need test bot, `DISCORD_ENABLED=true`, preferably `DISCORD_DM_ONLY=true`, and test-only target restrictions. | UNKNOWN |
| Slack | No | No | Non-secret config inspection only | Not run live | No Slack signing/token/allowed channel/user/linked owner config detected. | Need test Slack app with signing secret, allowed test channel, allowed test user, and linked owner. | UNKNOWN |
| WhatsApp | No | No | Non-secret config inspection only | Not run live | WhatsApp public-safe required config is absent. | Need sandbox phone, explicit verify token, token/phone id, and `WHATSAPP_ALLOWED_PHONES` for a test phone only. | UNKNOWN |
| SMS/text | Unsupported | No | Code/docs inspection | Future only | No inbound/outbound SMS provider exists; UI/docs mark it future/setup-needed. | Choose provider and identity/PIN/session pattern later. | FUTURE_UNSUPPORTED |

## Required Live QA Matrix

| Area | Required safe setup | Expected pass condition |
|---|---|---|
| Telegram private recall | Test bot, test chat only, explicit allowlist, operator mapping if testing linked identity. | Unverified recall fails closed; `/pin <PIN>` opens a short session; recall uses meeting notes only after verification. |
| Discord private recall | Test bot with DM-only or isolated test guild/channel. | Shared guild channel recall is blocked; DM `/pin <PIN>` opens session; private recall works only after verification. |
| Slack private recall | Test app with signing, allowed channel, allowed sender, linked owner. | Unsigned/unallowed requests fail closed; allowed linked/PIN-verified request can recall notes. |
| WhatsApp private recall | Sandbox test phone only with explicit verify token and allowed phone. | Unallowed phone is denied; allowed `/pin <PIN>` opens session; recall works only after gates pass. |
| Task Guardian delivery | Test connector targets only. | App history always records report; external send succeeds only to configured test target or records nonfatal setup warning. |

## Main Chat / Meeting Notes

Browser QA was not run in this pass. Existing focused backend validation remains the evidence for meeting-note memory behavior. Manual browser QA still needs to verify Meeting Manager save/edit, edited-note dedupe, Main Chat meeting-note recall, and per-turn note suppression.

## Decision

Private external meeting recall and Task Guardian external delivery cannot be promised as GREEN until live QA is run against configured test-only identities/channels. The code-level fail-closed and PIN/session behavior remains the current readiness evidence.
