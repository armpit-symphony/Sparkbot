# Codex runner pilot notes

Owner: Atlas. Signed: Atlas | 2026-11-04.

## Existing implementation reviewed

`backend/app/api/routes/chat/llm.py` already invokes `codex exec` using stdin,
read-only sandboxing, an ephemeral session, a final-response file and a timeout.
The standalone connector follows that subprocess pattern without importing the
backend or changing its model router. No new memory store or scheduler is added.
Backend job policy and auditing remain Meridian's responsibility.

The pilot adapter answers from bounded room context only. It runs from a fresh
temporary directory with user configuration, command tools, hooks, plugins,
apps, browser tools and subagents disabled. It requires the CLI's
`--ignore-user-config` flag (present in the locally inspected 0.147.0 CLI), keeps
read-only sandboxing, and never enables approval bypasses. Managed restrictions
still apply. Provider authentication stays in the user's existing Codex home;
seat keys and claim tokens never enter the prompt or subprocess environment.
This is not an OS-level isolation boundary for the trusted CLI itself.

The model cannot publish to the room. Only the runner submits its final text to
the backend completion endpoint. Even a room message saying "approve" cannot
upgrade this adapter to file-writing or tool-executing mode. Future repository
access requires a separately reviewed Guardian/tool permission contract.

## Official documentation and commercial-use findings

Reviewed 2026-11-04:

- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
  documents scripted `codex exec`, final-response output, and reuse of saved CLI
  authentication. It also describes account-auth automation as an advanced
  path and cautions against using its CI credential-seeding workflow for public
  repositories. This pilot does not seed, copy or share authentication files.
- [Authentication](https://learn.chatgpt.com/docs/auth?surface=cli)
  documents ChatGPT subscription sign-in and API-key sign-in as separate modes.
  This adapter requests ChatGPT login and excludes API-key environment variables
  to avoid silently changing billing modes.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
  documents command-tool controls, app controls and hook configuration. A
  read-only filesystem sandbox alone does not establish safe connector access.
- [Terms of Use](https://openai.com/policies/terms-of-use/)
  prohibit sharing credentials/account access, circumventing limits, and selling
  the service itself; they also contain a general automated-output extraction
  restriction. Technical CLI documentation is not blanket commercial clearance.
- [App-server authentication](https://learn.chatgpt.com/docs/app-server#auth-endpoints)
  explicitly says its authentication has not been permitted for commercial or
  hosted services, and directs those integrations toward Sign in with ChatGPT.
  This adapter uses the CLI, not app-server auth; that distinction is not a
  commercial-use exemption. Do not switch to app-server OAuth as a shortcut.
- [Service Terms, section 15](https://openai.com/policies/service-terms/)
  identify separate Sign in with ChatGPT terms for developer integrations.

Conclusion: official docs establish a supported technical path for personal
scripted Codex use with saved authentication. They do **not** conclusively approve
every paid third-party multi-user room integration. Before sale, confirm the
app's specific commercial integration and guest-triggered account usage with
OpenAI, including applicable account/workspace terms. Do not sell shared
subscription access, bundle credentials, or promise unlimited use. Installation
and sign-in remain the user's responsibility. This finding leaves commercial
clearance open; it is not a claim that the proposed product is prohibited.

## Validation scope

Offline tests use a fake child process, never a model or live seat. They check
context bounds, secret exclusion, configuration, Windows native executable
resolution, final-text extraction, nonzero exits, timeout termination and claim
cancellation. Real CLI authentication, model execution and live room delivery
still require the explicitly started pilot acceptance run.
