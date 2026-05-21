# Connector Identity Linking Status

Date: 2026-05-21
Branch: `public-release-connector-identity-live-qa`
Previous meeting-memory commit: `7f327b2e45011facef7bb751166adac6e5c223cc`

## Rule

External channels must fail closed for private meeting memory. If Sparkbot cannot verify the external sender/channel identity and map it to an authorized Sparkbot user/room, it must not reveal meeting notes. It should ask the user to link/authorize the connector or use Main Chat.

## Connector Matrix

| Connector | Inbound exists? | Sender identity | Sparkbot user link | Private memory retrieval | Meeting-note retrieval | Fail-closed status | Permission storage | Remaining blocker/unknown |
|---|---|---|---|---|---|---|---|---|
| Telegram | Yes | Telegram `chat_id` plus `from.id`/username/display name. | Operator mapping only when `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS` is configured; otherwise it creates an isolated `telegram_<id>` Sparkbot user and private bridge room. | Allowed for the linked bridge user/room. Does not reach the web operator's meeting memory unless explicitly operator-mapped. | Possible for the linked identity through `build_unified_context`; cross-surface operator recall requires operator chat mapping. | Partial fail-closed: disallowed chat IDs are blocked when `TELEGRAM_ALLOWED_CHAT_IDS` is set; empty allowlist permits isolated auto-linking. | SQLite `telegram_links`; env `TELEGRAM_ALLOWED_CHAT_IDS`, `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS`, `TELEGRAM_REQUIRE_PRIVATE_CHAT`. | Live test required; public docs should recommend allowlist/operator mapping before promising mobile meeting recall. |
| Discord | Yes | Discord channel ID plus author ID/name/display name. | Creates an isolated `discord_<id>` Sparkbot user and bridge room per channel when first used. No explicit web-operator mapping in this pass. | Allowed for the linked bridge user/room only. | Possible for notes created under the same Discord-linked identity; not guaranteed for web operator meetings. | Partial fail-closed: guild restriction can block non-approved guilds; outgoing delivery has allowed-channel checks. Empty guild/channel allowlists permit isolated auto-linking. | SQLite `discord_links`; env `DISCORD_GUILD_IDS`, `DISCORD_ALLOWED_CHANNEL_IDS`, `DISCORD_DM_ONLY`. | Needs explicit operator identity linking before GREEN cross-surface meeting recall. |
| WhatsApp | Yes | WhatsApp `wa_phone` and display name. | Creates an isolated `whatsapp_<phone>` Sparkbot user and bridge room unless the number already exists in bridge links. | Allowed for the linked phone identity/room only. | Possible for notes created under that linked identity; not guaranteed for web operator meetings. | Partial fail-closed: numbers outside `WHATSAPP_ALLOWED_PHONES` are rejected when the allowlist is set. Empty allowlist permits isolated auto-linking. | SQLite `whatsapp_links`; env `WHATSAPP_ALLOWED_PHONES`. | Needs explicit operator identity linking before GREEN cross-surface meeting recall. |
| Slack | Yes | Slack event channel plus Slack `user` ID and thread/DM metadata. | Hardened this phase: requires an existing Sparkbot user named by `SPARKBOT_SLACK_OWNER_USERNAME`; no default synthetic owner creation. | Allowed only when request signature verifies, channel is in `SLACK_ALLOWED_CHANNEL_IDS`, Slack sender is in `SLACK_ALLOWED_USER_IDS`, and linked owner user exists. | Setup-needed unless signed + allowed channel + allowed Slack user + linked owner. This prevents loose access to shared meeting memory. | Fail-closed for missing signing secret, missing channel allowlist, missing user allowlist, unauthorized channel, unauthorized Slack sender, or missing linked owner. | Env `SLACK_SIGNING_SECRET`, `SLACK_ALLOWED_CHANNEL_IDS`, `SLACK_ALLOWED_USER_IDS`, `SPARKBOT_SLACK_OWNER_USERNAME`; Slack Bridge room is created only after linked owner exists. | Live Slack QA not run because test env is not configured; shared channels require both channel and sender allowlists. |
| SMS/text | No | None. | None. | Not available. | Not available. | Fails closed by absence of connector; Task Guardian SMS delivery remains future/setup-needed only. | None yet. | Select provider and identity model later. |

## Live QA Readiness In This Environment

Boolean process-environment check showed no configured test connector secrets/allowlists in this shell. Auditor review also found `.env.local` contains Telegram/Discord connector keys, with Discord disabled and token values not printed; Compose/live QA must account for file-loaded config separately:

- Telegram process env token/allowlist/operator chat mapping: not configured; `.env.local` contains a Telegram token key, so do not start connector polling without `TELEGRAM_POLL_ENABLED=false` or a test bot.
- Discord token/enabled/guild/channel allowlist: not configured.
- WhatsApp enabled/token/phone/allowlist: not configured.
- Slack process env token/signing secret/allowed channel/allowed user/linked owner: not configured.

No live connector messages were sent. Live connector QA remains UNKNOWN until test identities/channels are configured.

## Hardening Completed This Phase

- Slack request signing now fails closed when `SLACK_SIGNING_SECRET` is missing.
- Slack meeting-memory context retrieval requires `SLACK_ALLOWED_CHANNEL_IDS`, `SLACK_ALLOWED_USER_IDS`, and both inbound channel and sender must match.
- Slack no longer creates or uses a default synthetic `sparkbot-user` for shared memory recall.
- Slack requires an allowed Slack sender and `SPARKBOT_SLACK_OWNER_USERNAME` to point at an existing Sparkbot user before unified context is built.
- Slack returns a setup/linking message instead of private meeting context when identity is missing.

## Recommended Next Step

Before marking connector memory continuity GREEN, configure test identities only and run live QA for Telegram, Discord, WhatsApp, and Slack. Then decide whether Telegram/Discord/WhatsApp should also require fail-closed allowlists for public server deployments or keep isolated auto-linking as acceptable public behavior.
