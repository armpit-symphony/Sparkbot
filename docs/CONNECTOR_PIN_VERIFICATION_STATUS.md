# Connector PIN Verification Status

Date: 2026-05-21
Branch: `public-release-live-connector-qa`
Base commit: `da8af1fe9570d89d0c60907b2b2f3b37f1252355`

## Security Model

Connector identity and operator PIN verification are separate controls.

- Connector identity answers where the request came from: Telegram chat, Discord user/channel, Slack user/channel, WhatsApp phone, or future SMS sender.
- PIN verification answers whether that external requester can act as the operator for private recall during a short session.
- PIN verification does not replace Slack request signing, connector allowlists, allowed phones/users/channels, or connector authenticity checks.
- Private meeting memory fails closed unless the connector request has a linked operator identity or a valid time-limited connector PIN session.

## Existing PIN Reuse

| Item | Status | Evidence / behavior |
|---|---|---|
| PIN source | Reused | Existing Guardian auth stores `SPARKBOT_OPERATOR_PIN_HASH` or `data/guardian/operator_pin.hash`. |
| PIN storage | Hashed | PBKDF2-HMAC-SHA256 via `guardian.auth.create_pin_hash`; no plaintext PIN is stored in connector sessions. |
| Verification | Reused | Connector sessions call `guardian.auth.verify_pin` and inherit failed-attempt tracking. |
| Lockout | Reused | `SPARKBOT_PIN_MAX_ATTEMPTS` and `SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS` apply to connector session keys. |
| Session TTL | Added | Connector sessions default to 30 minutes via `SPARKBOT_CONNECTOR_PIN_TTL_SECONDS`; in-memory only. |
| Failed attempts | Logged safely | Guardian auth logs failed attempts by connector-scoped key, not by raw PIN. |

## Connector Status

| Connector | PIN command | Private recall gate | Fail-closed behavior | Remaining live QA |
|---|---|---|---|---|
| Telegram | `/pin 123456`, `/verify 123456`, `/logout` | Requires `TELEGRAM_ALLOWED_CHAT_IDS`; explicit operator chat mapping can skip PIN, otherwise valid connector PIN session is required. `/breakglass` now requires `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS`. | Unknown/unallowlisted chats cannot use private recall; PIN failure does not create a session. | Test bot/chat with `TELEGRAM_POLL_ENABLED=false` until intentionally running a test bot. |
| Discord | `/pin 123456`, `/verify 123456`, `/logout` in DM only | Guild/shared channel private recall is blocked; DM private recall requires valid connector PIN session. | Shared channel alone is not enough for private recall. | Test DM-only recall and confirm guild-channel prompt. |
| Slack | `/pin 123456`, `/verify 123456`, `/logout` | Still requires signed request, allowed channel, allowed Slack user, and existing linked owner. Linked owner can recall; PIN session is available as step-up. | Missing signature/channel/user/owner fails closed before context retrieval. | Signed test app with `SLACK_ALLOWED_CHANNEL_IDS`, `SLACK_ALLOWED_USER_IDS`, and linked owner. |
| WhatsApp | `/pin 123456`, `/verify 123456`, `/logout` | Inbound bridge now requires explicit verify token and `WHATSAPP_ALLOWED_PHONES`; private recall requires valid connector PIN session. | Missing verify token or empty allowed-phone list disables inbound bridge; unlisted phones are denied. | Test sandbox number only. |
| SMS/text | Not implemented | Not available. | Fails closed by absence of connector. | Future provider/identity design. |

## Implementation Notes

- Connector sessions are in-memory and keyed by connector plus external identity and channel where applicable.
- Sessions store connector, external identity, channel id, linked Sparkbot operator user id, scope, verified time, and expiration time.
- Sessions do not store raw PINs or PIN hashes.
- Private recall detection is intentionally conservative and gates meeting/decision/action-item style requests.
- Main Chat/web operator recall is unchanged and continues through normal logged-in auth.

## Remaining Risks

| Priority | Item | Next action |
|---|---|---|
| P0_BLOCKER | Live connector verification has not been run. | Configure test-only Telegram/Discord/Slack/WhatsApp identities and run live QA without production channels. |
| P1_POLISH | Discord pending approvals are still channel-scoped for non-private flows. | Prefer `DISCORD_DM_ONLY=true` for public QA or later key approvals by channel plus author id. |
| P1_POLISH | PIN sessions are process-local. | Accept for public MVP; document that restart clears connector verification. |

## Live Connector QA Update - 2026-05-21

- Created `docs/PUBLIC_RELEASE_LIVE_CONNECTOR_QA_RESULTS.md` for non-secret live QA evidence.
- Current process environment does not expose usable Telegram, Discord, Slack, WhatsApp, SMS/text, Task Guardian external-delivery, or operator PIN test configuration.
- Local env-file inspection did not confirm any safe test-only target; `DISCORD_ENABLED` is present but disabled.
- No live connector messages were sent and no secrets/PINs/tokens/IDs were printed.
- Telegram, Discord, Slack, WhatsApp, and Task Guardian external delivery remain UNKNOWN for live QA.
- SMS/text remains FUTURE_UNSUPPORTED.
- Sparkbot_shell extraction map refresh is reasonable for classification/planning, but public external recall should stay YELLOW/UNKNOWN until live connector QA passes.
