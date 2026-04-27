# Sparkbot Security Architecture

> **tl;dr** — Sparkbot is built on a "policy before autonomy" principle. Every tool the LLM can call is classified, gated, audited, and logged before it touches anything external. The LLM cannot email, post to Slack, create GitHub issues, or run server commands without explicit human confirmation. This is architecture, not a config flag.

---

## The Guardian Stack

Sparkbot wraps the LLM inside five layers of guardrails. Each layer has a single, auditable job.

```
User message
     │
     ▼
┌─────────────────────────────────────────┐
│  Token Guardian (shadow)                │  ← classify prompt, route to right model
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│  Memory Guardian                        │  ← inject relevant packed memory into prompt
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│  LLM (litellm)                          │  ← model call, tool selection
└─────────────────────────────────────────┘
     │  tool_calls
     ▼
┌─────────────────────────────────────────┐
│  Agent Shield / Policy                  │  ← allow / confirm / deny per tool + scope
└─────────────────────────────────────────┘
     │  allowed or confirmed
     ▼
┌─────────────────────────────────────────┐
│  Executive Guardian                     │  ← decision journal for high-risk actions
└─────────────────────────────────────────┘
     │
     ▼
 Tool executes → result logged in audit trail
```

---

## What Each Layer Does

### Agent Shield (Policy Layer)

Every tool is classified into one of four scopes before it can run:

| Scope | Default action | Examples |
|-------|---------------|----------|
| `read` | allow | web search, list tasks, read calendar, fetch inbox |
| `write` (internal) | allow | create task, set reminder, store memory |
| `write` (external) | **confirm** | send email, post to Slack, create GitHub issue, create calendar event |
| `execute` | confirm + execution gate | server commands, SSH, service control |

The policy decision is recorded as a `policy_decision` audit entry on every tool call — allow, confirm, or deny — regardless of outcome.

### Write-Tool Confirmation Gate

Any action that touches an external system (email, Slack, GitHub, Notion, Confluence, Google Calendar, Google Drive) triggers a **confirmation modal in the UI before execution**. The LLM cannot bypass this. It is not optional. There is no config flag to disable it per-tool — the entire `write_external` class requires user confirmation.

### Execution Gate

Server commands and SSH operations require the room's `execution_allowed` flag to be explicitly enabled by the room owner. The flag defaults to `false` on every room. Even with the flag enabled, individual actions still go through the policy layer and confirmation modal.

### Executive Guardian

High-risk executions (external writes, service control, server/SSH) are wrapped in a decision journal. Every action writes a structured log entry under `data/guardian/executive/decisions/` before and after execution. This provides a non-repudiable record that is separate from the main audit trail.

### Audit Trail + Redaction

Every tool call — its name, arguments, policy decision, and result — is written to the audit log. Before writing, a redaction pass strips:
- Values whose keys match secret-pattern names (`token`, `key`, `secret`, `password`, `credential`, etc.)
- Values whose format matches token patterns (Bearer tokens, API keys, etc.)

The audit log is room-scoped and accessible to room members via the `/audit` slash command.

Communication bridges also redact credentials before logging transport failures. Telegram Bot API errors are normalized so the token-bearing `/bot<TOKEN>/...` URL is never returned in logs, status responses, or Telegram-visible error text.

### Memory Guardian

Message content and tool events are stored in a packed, retrievable memory ledger per user and room. The ledger is injected selectively into prompts — only the most relevant context is retrieved, not the full history. Memory is always user-scoped and never shared across users without explicit room-sharing configuration.

---

## Session Security

| Control | Implementation |
|---------|----------------|
| Session tokens | HttpOnly `Secure SameSite=Strict` cookie — never exposed to JavaScript |
| Bearer fallback | Accepted for backward compat only; HttpOnly cookie is the canonical session |
| Login rate limiting | 10 attempts / 15 min per IP |
| Logout | `DELETE /api/v1/chat/users/session` clears the cookie server-side |

---

## Transport and Headers

All production traffic runs over HTTPS (nginx TLS termination). The backend sets the following headers on every response:

| Header | Value |
|--------|-------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | `default-src 'self'` (tightened per route) |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Permissions-Policy` | camera, microphone, geolocation off |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

---

## Supply Chain

- `pip-audit` + `npm audit` run on every push and PR via GitHub Actions (`.github/workflows/dep-scan.yml`)
- `gitleaks` pre-commit hook blocks accidental secret commits
- `.env` files are `.gitignore`d; git history has been purged of any prior leaks via `git filter-repo`
- See `ROTATION_RUNBOOK.md` for the key rotation procedure

---

## Security Audit Status

Sparkbot v2 has completed a full internal security audit across five phases:

| Phase | Scope | Status |
|-------|-------|--------|
| A | Access control, secret hygiene, repo history | ✅ Complete |
| B | Authentication, session hardening, cookie security | ✅ Complete |
| C | Runtime correctness, input validation | ✅ Complete |
| D | Write-tool gate, audit redaction, HttpOnly cookies, security headers | ✅ Complete |
| E | Dependency scanning CI workflow | ✅ Complete |

---

## Design Principles

1. **Policy before autonomy.** No tool runs until the policy layer has classified and approved it.
2. **Confirm before mutation.** Any action that changes state in an external system requires human confirmation.
3. **Audit everything.** Every tool call — allowed or denied — is logged with a redacted record.
4. **Default deny.** Unknown tools are denied, not allowed. Unknown scopes resolve to `admin/deny`.
5. **Execution gate defaults off.** Server and SSH access must be explicitly enabled per room by the room owner.
6. **Least privilege.** Read-only access is always preferred. The Task Guardian only schedules read-only tools.
7. **Secrets never in logs.** Audit redaction runs before every log write, not as a post-processing step.

---

## Audit History

| Date | Version | Scope | Report |
|------|---------|-------|--------|
| 2026-04-27 | v1.6.37 | Telegram token redaction + security once-over | [SECURITY-AUDIT.md](./SECURITY-AUDIT.md) |
| 2026-04-18 | v1.3.0 | Full codebase — auth, SSRF, tools, WebSocket, deps | [SECURITY-AUDIT.md](./SECURITY-AUDIT.md) |

---

## Reporting a Vulnerability

Please report security issues privately to **security@sparkpitlabs.com** rather than opening a public issue. Include reproduction steps and any relevant code or logs. We will respond within 48 hours.

Do not discuss potential vulnerabilities publicly until a fix is available.
