# Sparkbot Public Release Live QA Plan

Date: 2026-05-20
Branch: `public-release-connector-identity-live-qa`
Scope: live/manual validation plan only. Do not run destructive checks, do not send surprise external messages, and do not connect private production systems.

## Local AI

| Target | Setup | Safe test | Expected result | Stop condition |
|---|---|---|---|---|
| Ollama | Start Ollama locally; configure `ollama`, base URL `http://localhost:11434`, and an installed model. | Send a short DM prompt and launch one Round Table seat using Local AI. | Status shows reachable/ready; responses use the local route; missing model reports setup-needed. | Endpoint unreachable, UI hides error, or cloud fallback occurs for explicit local seat. |
| LM Studio | Start local server on `http://localhost:1234/v1`; choose OpenAI-compatible local runtime. | Save model seat, send one DM prompt, and test one Meeting Room seat. | Base URL/model persist; response routes through local endpoint; no browser-stored secret. | Secret appears in frontend config or explicit local seat falls back to cloud. |
| llama.cpp / llama-server | Start server on `http://localhost:8080/v1`; configure runtime `llamacpp`. | Send a short prompt and refresh setup status. | Reachability/model status updates clearly; failures are setup-needed/unreachable. | UI claims ready when server is stopped. |
| Generic OpenAI-compatible endpoint | Use a local/test endpoint only; optional API key goes through backend model-seat editor. | Save endpoint and run one harmless prompt. | Credential is write-only; backend reports ready only when endpoint responds. | Credential is returned to browser or stored in localStorage. |

## Connectors

| Connector | Prerequisite | Safe test | Expected result |
|---|---|---|---|
| Telegram health report delivery | Test bot and linked test chat only; use allowlist if configured. | Add PC Health Check with app + Telegram delivery; run once. | In-app report appears; Telegram receives a concise report; missing setup or send failure is a nonfatal delivery warning. |
| Discord health report delivery | Test bot/channel or DM only; use allowed channel IDs if configured. | Add PC Health Check with app + Discord delivery; run once. | Discord receives the report in the test target only; no broad guild broadcast; missing setup is a warning. |
| Slack health report delivery | Test workspace/channel only; set `SPARKBOT_HEALTH_SLACK_ALLOWED_CHANNELS` for the test channel where possible. | Add PC or Server Health Check with app + Slack delivery; run once. | Slack receives report in configured test channel; missing token/channel or allowlist mismatch is a nonfatal delivery error. |
| WhatsApp health report delivery | Test linked number only. | Add PC Health Check with app + WhatsApp delivery; run once. | WhatsApp receives the report only for the linked test number; missing setup is a nonfatal warning. |
| SMS/text unsupported behavior | No live provider in this phase. | Request/select SMS/text delivery for a health report without configuring a provider. | Task records setup-needed/future warning, keeps app report, and sends no external SMS. |

## Task Guardian Schedule Setup

| Scenario | Safe test | Expected result |
|---|---|---|
| Natural-language Telegram setup | In Main Chat, ask: "Send me a server health report every day at 6 AM on Telegram." Use a test connector only. | Sparkbot schedules or offers a confirmable Task Guardian job with Telegram selected; no external send occurs until the job runs or is manually run. |
| Natural-language SMS setup | Ask: "Text me a PC health report every morning." | Sparkbot records SMS/text as unsupported/setup-needed or asks for setup; it does not claim SMS delivery is live. |
| Inspect scheduled destination | Ask where daily health reports are being delivered. | Sparkbot can summarize app/default plus selected channels and last delivery warning/status. |

## Meeting Memory Continuity

| Scenario | Safe test | Expected result |
|---|---|---|
| Main Chat meeting recall | Generate or edit notes in a Round Table, then ask Main Chat what was decided. | Response cites relevant saved notes/action items through shared memory. |
| Telegram meeting recall | Use a linked test Telegram chat and ask what happened in the last Round Table. | Response uses meeting notes only for the linked/authorized room/user identity. |
| Discord meeting recall | Use a linked test Discord channel/DM and ask for meeting action items. | Response uses saved notes without broad guild exposure. |
| WhatsApp meeting recall | Use a linked test WhatsApp number and ask what the meeting decided. | Response uses saved notes only for that linked identity. |
| Slack meeting recall | Use test Slack route with signing, channel allowlist, sender allowlist, and linked owner configured if available. | If identity is not linked, Sparkbot reports setup limitation rather than exposing notes. |
| Unauthorized connector request | Ask from an unlinked test account/number/channel. | No private meeting notes are returned. |

## Connector Identity Live QA

| Scenario | Safe test | Expected result |
|---|---|---|
| Slack missing signature | Send a signed/unsigned test request in a local Slack test setup only. | Unsigned or invalid requests return 403 and no memory context is built. |
| Slack unallowed channel/user | Use a test channel not in `SLACK_ALLOWED_CHANNEL_IDS` and a test sender not in `SLACK_ALLOWED_USER_IDS`. | Sparkbot posts setup/linking guidance and no meeting-note content. |
| Slack allowed linked owner | Configure `SLACK_SIGNING_SECRET`, `SLACK_ALLOWED_CHANNEL_IDS`, `SLACK_ALLOWED_USER_IDS`, and existing `SPARKBOT_SLACK_OWNER_USERNAME`; ask about a saved meeting. | Sparkbot can use the linked owner's meeting notes. |
| Telegram linked operator | Configure test bot plus `TELEGRAM_ALLOWED_CHAT_IDS` and, for operator recall, `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS`. | Only the linked/operator test chat can retrieve meeting notes. |
| Discord linked identity | Configure test bot plus test guild/channel restrictions. | Linked Discord identity can retrieve only its authorized context. |
| WhatsApp linked identity | Configure test sandbox number plus `WHATSAPP_ALLOWED_PHONES`. | Linked test number can retrieve only its authorized context. |

## Risky-Action Guardrails

| Scenario | Safe test | Expected result |
|---|---|---|
| Terminal command confirmation | Ask for a harmless command such as `pwd` or `date`; do not approve destructive commands. | Personal/Balanced confirm write/execute as configured; Locked requires elevated approval or blocks with next step. |
| Browser/form confirmation | Use a local test page if available; request a harmless click/fill. | Read/open is allowed where profile permits; click/fill asks confirmation. |
| File deletion block/confirmation | Request deletion of a disposable temp file only. | Confirmation/elevation appears before delete; cancellation leaves file intact. |
| External send confirmation | Use test connector/channel only. | Send action requires confirmation; no message is sent before approval. |
| Locked mode blocking | Repeat a high-risk terminal/send/delete request in Locked. | Locked does not run it as normal approval; it requires elevated/break-glass or blocks non-operator. |
| Balanced mode confirmation | Repeat a high-risk configured action in Balanced. | Balanced produces normal confirmation with clear summary. |

## Packaging

| Environment | Steps | Expected result |
|---|---|---|
| Windows/Git Bash package run | Run `bash scripts/package-public-download.sh --output-dir dist/public-download/windows-smoke --artifact-prefix sparkbot-windows-smoke`; temporarily test without `zip` if feasible to exercise Python `zipfile`. | `.tar.gz`, `.zip`, `sparkbot-cli.py`, `SHA256SUMS`, and `RELEASE-NOTES.txt` are created. |
| Linux clean-clone package run | Fresh clone/checkout, run package script from repo root with relative output dir. | Relative output path resolves under repo root and zip creation succeeds. |
| Package artifact inspection | List tar/zip contents and inspect `backend/app/services/lima_robotics_bridge.py`. | No `.venv-ci`, dotenv, logs, DBs, keys/certs, proposal scripts, private readiness docs, LIMA private docs; Robo bridge is public preview stub. |
| Checksum/release notes verification | Run `sha256sum -c SHA256SUMS` in output dir and open `RELEASE-NOTES.txt`. | Checksums verify; release notes include version/ref/commit and no private paths. |

## Explicit Non-Goals

- No real robotics, drone, humanoid, IoT, or private Robo bridge execution.
- No LIMA AI OS, Arc Bot, LIMA Office, or LIMA IT wiring.
- No production connector channels.
- No destructive file, server, shell, or browser actions.
