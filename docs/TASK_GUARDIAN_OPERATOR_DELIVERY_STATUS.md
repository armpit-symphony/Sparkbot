# Task Guardian Operator Delivery Status

Date: 2026-05-21
Branch: `public-release-task-delivery-operator-channels`
Base: `public-release-source-boundary-cleanup` at `ce9b07da4bac7ab49e6a72e160a3f926a2eb1692`

## Product Model

Sparkbot owns this work first. Workstation is the operator floor, Main Chat is the middle-person command channel, Task Guardian is the scheduled work manager, external connectors are operator communication channels, and unified memory/context is the shared company memory. This phase does not wire LIMA AI OS, Arc Bot, LIMA Office, LIMA IT, Sparkbot_shell, or real robotics/IoT control.

## Current Delivery Capability

| Channel | Status | Current behavior | Notes/gaps |
|---|---|---|---|
| App / in-room | IMPLEMENTED | Default for every PC/server health report. The report is saved to Task Guardian run history and posted in the room. | Always on; no external connector required. |
| Telegram | IMPLEMENTED_IF_CONFIGURED | Health reports can be sent to linked Telegram chats when the bot token and linked chats exist. | Outbound send now respects the optional allowed-chat list. Live test still required. |
| Discord | IMPLEMENTED_IF_CONFIGURED | Health reports can be sent to linked Discord channels when the connector is enabled and linked channels exist. | Outbound send now respects optional allowed-channel IDs. Guild-level re-check is still limited by stored link shape. Live test still required. |
| Slack | IMPLEMENTED_IF_CONFIGURED | Health reports can be sent to `slack_channel`, `delivery_slack_channel`, or `SPARKBOT_HEALTH_SLACK_CHANNEL` when `SLACK_BOT_TOKEN` is configured. | Optional `SPARKBOT_HEALTH_SLACK_ALLOWED_CHANNELS` can restrict delivery. Live test still required. |
| WhatsApp | IMPLEMENTED_IF_CONFIGURED | Backend delivery preference and Task Guardian send path support WhatsApp when the connector is enabled and a linked number exists. | Command Center now shows the channel, but live WhatsApp QA is required. |
| SMS/text | FUTURE_UNSUPPORTED | Task Guardian can record the operator preference and reports a setup warning. It does not fake a send. | Needs a real SMS provider integration before it can be marked operational. |

## Delivery Preference Model

Health jobs store delivery preference state in `guardian_tasks.tool_args_json` with:

- `delivery_channels`: sanitized list including `app` plus selected external channels.
- `fallback_to_app`: defaults to true.
- `delivery.channels[]`: public-safe channel status objects with `channel`, `enabled`, `configured`, `status`, `target_label`, and `setup_message`.
- `last_delivery_status`: `app_only`, `sent`, or `warning`.
- `last_delivery_error`: bounded warning summary.

No connector tokens or secrets are stored in frontend payloads or Task Guardian job config by this model. External delivery remains opt-in; app/in-room history remains the default fallback.

## Execution And Memory

PC and Server Health Check runs still write the health report to app/task history first. External delivery failures are recorded as delivery warnings and do not destroy the report or fail the whole task. Delivery status is appended to Task Guardian run evidence and written to unified memory/context as a source-labeled delivery event next to the existing `task_guardian.health.pc` or `task_guardian.health.server` report memory.

Main Chat/DM can inspect scheduled Task Guardian jobs through existing Guardian task tooling and can use the shared memory/context path for latest health report summaries. Natural-language setup is readiness-level through tool schemas and model/tool routing: requests such as "Send me a server health report every day at 6 AM on Telegram" have the backend fields needed for scheduling, but deterministic parsing still needs browser/live QA before it is called fully fluent.

## Safety Notes

- Unsupported SMS/text requests record a warning instead of sending.
- Missing connector configuration records a warning and keeps app history.
- External sends require explicit delivery selection/configuration.
- Connector allowlists are respected where current bridge state provides enough target identity.
- No surprise messages should be sent during QA; use test channels only.

## Remaining Gaps

| Priority | Gap | Recommended next action |
|---|---|---|
| P0 | Live connector delivery is untested for Telegram, Discord, Slack, and WhatsApp. | Run the live QA plan with test channels only. |
| P1 | SMS/text provider does not exist. | Keep SMS as setup-needed/future until a public-safe provider is selected. |
| P1 | Deterministic natural-language schedule parser is not complete. | Validate LLM/tool-driven setup first; then add a conservative parser if needed. |
| P1 | Discord stored room links do not currently carry guild ID for outbound guild allowlist re-check. | Extend link metadata later if Discord becomes core public delivery. |
| P2 | Dedicated delivery inspector/audit UI is minimal. | Add only after browser QA confirms the basic Task Guardian flow. |

## LIMA Runtime Alignment Note

This implementation belongs in Sparkbot Public first. A later LIMA AI OS runtime can generalize the pattern as: scheduled task -> execution result -> delivery route -> memory/context event -> audit/Guardian decision. No LIMA runtime wiring is included in this phase.
