# Sparkbot Privacy And Data Retention

Sparkbot is local-first. The desktop app and self-hosted server keep app data on the machine or server you control unless you connect an external provider.

## What Stays Local

- Chat rooms, messages, tasks, reminders, meeting artifacts, audit logs, Guardian memory, pending approvals, and Guardian Vault metadata are stored in Sparkbot's local data directory or configured database.
- Guardian Vault stores secret values encrypted. Use-only secrets are not revealed to chat output.
- Audit logs redact secret-looking keys and token-looking values before storage.

## What Leaves The Machine

Data leaves Sparkbot only when a configured provider or connector needs it:

- Cloud LLM providers receive the prompt context needed to answer.
- Gmail, Calendar, Drive, Slack, GitHub, Discord, Telegram, WhatsApp, Notion, Confluence, Jira, Linear, and similar connectors receive the API calls needed for the requested action.
- Web search and URL fetch tools contact the requested search or web service.

Local models can run without sending prompts to a cloud LLM provider.

## Retention

Sparkbot keeps local records until you delete them, rotate the local database, or remove the data directory. Pending approvals expire automatically. Break-glass sessions are short-lived and expire by TTL.

Recommended operator practice:

1. Back up `.env` and Guardian Vault keys separately from normal chat data.
2. Rotate any connector token that may have appeared in external logs.
3. Periodically export or prune audit logs according to your team's retention policy.
4. Delete unused rooms, custom agents, and scheduled jobs when a project ends.

## User Control

- Use `/memory` and memory tools to inspect or remove user memory.
- Use the dashboard approval inbox to approve or deny pending actions.
- Use Computer Control and break-glass settings to decide when Sparkbot can touch the local machine, browser, terminal, services, Vault, or comms sends.
- Use agent identity metadata and kill switches to disable agents that should not run.
