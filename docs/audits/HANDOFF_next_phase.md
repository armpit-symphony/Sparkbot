# Handoff: Guardian/Spine LIMA Extraction — Next Phase

**Date:** 2026-05-01
**Previous session result:** v1.6.48 committed and pushed (commit bff8421, tag v1.6.48)
**GitHub Pages:** https://armpit-symphony.github.io/Sparkbot/ — updated

---

## What Was Done (Complete)

### Phase 0: Inventory & Preservation
- Created `docs/audits/sparkbot_guardian_spine_extraction_audit.md` — full inventory of all 22 Guardian/Spine modules, 50+ API routes, 10 SQLite tables, 7 background jobs, 40+ env vars, LIMA comparison table, dependency map, and phased extraction plan with recommended first 3 PRs.
- Created `docs/audits/guardian_spine_current_state.md` — preservation record marking Sparkbot as source of truth. LIMA standalone `guardian/` modules marked incomplete.

### Phase 1-2: Security Audit & Fix Plan
- Created `docs/audits/guardian_spine_security_fix_plan.md` — 9 risks documented (RISK-1 through RISK-9), each with exact files, severity, fix, tests, rollback plan.

### Phase 3: Security Fixes (v1.6.48)
- **RISK-1 FIX:** `pending_approvals.py` — added `_redact_tool_args_for_event()` that strips secret-like keys (password, token, api_key, etc.) from tool_args before Spine event emission. Applied to all 3 Spine event sites (store, consume, discard).
- **RISK-2 FIX:** `executive.py` — added `_redact_metadata()` and `_redact_text()` that strip secret key-value pairs from metadata dicts and result excerpts before JSONL write and Spine emission. Also redacts exception messages in validation_note.
- **21 new tests** in `tests/services/test_guardian_security.py` covering all MEDIUM+ risks.
- **All 181 tests pass** (21 new + 140 existing service + 41 breakglass route).

### All Extraction Gate Criteria: PASSED
Every checkbox in `guardian_spine_security_fix_plan.md` is checked. Extraction may proceed.

---

## What Comes Next

### Extraction Phase: Move Generic Guardian Core to LIMA-Guardian-Suite

The LIMA repo is at `github.com/armpit-symphony/LIMA-Guardian-Suite`. It currently has two parallel implementations:
- `app/services/guardian/` — direct copy of 10 Sparkbot modules (still imports `app.models`, `app.crud` — NOT standalone)
- `guardian/` — simplified standalone with 5 modules (weaker: base64 vault, no FTS memory, no policy engine)

#### Recommended PR Sequence

**PR 1: Extract Vault + Auth to Standalone LIMA Module**
- Copy `vault.py` and `auth.py` from Sparkbot to LIMA
- Replace `SPARKBOT_*` env prefix with configurable (default `LIMA_GUARDIAN_*`)
- Replace hardcoded `data/guardian/` with configurable `data_dir`
- Add `GuardianConfig(env_prefix=..., data_dir=...)` to LIMA
- Write standalone tests (no Sparkbot DB needed)
- **Key:** Fernet encryption must be preserved — do NOT downgrade to base64
- **Key:** Break-glass sessions must stay in-memory (security choice)
- Files: `lima_guardian/vault.py`, `lima_guardian/auth.py`, `lima_guardian/config.py`, tests
- Deps: `cryptography>=41.0.0`

**PR 2: Extract Pending Approvals + Policy Engine Core**
- Copy `pending_approvals.py` to LIMA (include the new redaction code from v1.6.48)
- Copy `policy.py` core engine (split out Sparkbot's 50+ tool registry into a separate configurable file)
- Key types to extract: `PolicyAction`, `PolicyDecision`, `ToolPolicy`, `PolicyScope`
- Key function: `decide_tool_use()` — make tool registry injectable
- Files: `lima_guardian/pending_approvals.py`, `lima_guardian/policy.py`, `lima_guardian/registries/default_tools.py`, tests

**PR 3: Extract Token Guardian + Verifier + Improvement Loop**
- Copy `token_guardian.py` + vendored `tokenguardian/` submodule
- Copy `verifier.py` (extract tool-specific patterns to configurable registry)
- Copy `improvement.py` (configurable data_dir)
- Files: `lima_guardian/token_guardian.py`, `lima_guardian/tokenguardian/`, `lima_guardian/verifier.py`, `lima_guardian/improvement.py`, tests

### After PR 1-3: Larger Extraction

**PR 4+: Guardian Spine** (the biggest module — 3870 lines, 8 tables)
- Extract core state catalog (event/task/project/approval tables)
- `sync_chat_task_created()` and `sync_chat_task_mirror()` must become adapter hooks (they depend on SQLModel ChatTask)
- Task Master Adapter and Project Executive stay as Sparkbot adapters initially

**PR 5+: Sparkbot Shim Adapters**
- `sparkbot_tool_registry.py` — Sparkbot's 50+ tool policy entries
- `sparkbot_spine_sync.py` — ChatTask ↔ Spine mirror sync
- `sparkbot_notification_sink.py` — bridge notifications
- `sparkbot_memory_adapter.py` — Sparkbot-specific memory event types

**PR 6+: Sparkbot Consumes LIMA as Dependency**
- Add `lima-guardian-suite` to `pyproject.toml`
- Replace inline imports with LIMA imports
- Wire Sparkbot adapters to LIMA protocols

---

## Critical Context for Next Session

### How to Run Tests
```bash
cd /home/sparky/Sparkbot/backend
PROJECT_NAME=sparkbot-test ENVIRONMENT=local SECRET_KEY=test-secret-key-for-testing \
  FIRST_SUPERUSER=admin@example.com FIRST_SUPERUSER_PASSWORD=testpassword \
  ../.venv/bin/python -m pytest tests/services/ -v
```

### Files Modified in v1.6.48
- `backend/app/services/guardian/pending_approvals.py` — added `_redact_tool_args_for_event()`
- `backend/app/services/guardian/executive.py` — added `_redact_metadata()`, `_redact_text()`
- `backend/tests/services/test_guardian_security.py` — 21 new tests (NEW FILE)
- `docs/audits/sparkbot_guardian_spine_extraction_audit.md` (NEW FILE)
- `docs/audits/guardian_spine_current_state.md` (NEW FILE)
- `docs/audits/guardian_spine_security_fix_plan.md` (NEW FILE)
- `docs/release-notes/v1.6.48.txt` (NEW FILE)
- Version bumped in: `pyproject.toml`, `package.json`, `tauri.conf.json`, `index.html`, `service-worker.js`, `capabilities.md`, `public-downloads.md`, `README.md`, `release-notes.md`

### Policy Behavior Gotchas (discovered during testing)
- `vault_delete_secret` returns `privileged_reveal` (not `privileged`) from policy
- `vault_reveal_secret` with `is_privileged=True` returns `confirm` (still needs explicit confirmation even when privileged)
- `global_bypass_enabled()` returns `False` when `SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT` is unset (no TTL = no bypass)

### Repos
- **Sparkbot (public):** `/home/sparky/Sparkbot/` → `github.com/armpit-symphony/Sparkbot`
- **Sparkbot (private live):** `/home/sparky/sparkbot-v2/` → `remote.sparkpitlabs.com`
- **LIMA-Guardian-Suite:** `github.com/armpit-symphony/LIMA-Guardian-Suite` (clone to `/tmp/lima-guardian-suite/` for work)

### Rules (carry forward)
- Do NOT delete Sparkbot Guardian/Spine code
- Do NOT replace working Sparkbot modules with weaker LIMA modules
- Do NOT print secrets or token values
- Sparkbot is source of truth until LIMA passes standalone tests
- Small guarded PRs only

---

*Ready for next session. All gates passed. Begin PR 1: Vault + Auth extraction to LIMA.*
